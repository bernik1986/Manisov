"""Synthetic release checks: no production connection, Docker engine, or credentials."""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from deployment_ci import verified
from deployment_data import extract_files, validate_database


class ReminderRollback(unittest.TestCase):
    def test_existing_foreign_key_shapes_and_missing_indexes(self):
        spec = importlib.util.spec_from_file_location("reminders", ROOT / "migrations/versions/b5c6d7e8f9a0_add_comment_reminders.py")
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        for fk_name in (None, "fk_candidate_comments_reminder_user_id_users", "legacy_custom_fk", False):
            for indexes in (True, False):
                with self.subTest(fk_name=fk_name, indexes=indexes):
                    engine = sa.create_engine("sqlite://")
                    meta = sa.MetaData()
                    users = sa.Table("users", meta, sa.Column("user_id", sa.Integer, primary_key=True))
                    extra = [] if fk_name is False else [sa.ForeignKey("users.user_id", name=fk_name, ondelete="SET NULL")]
                    comments = sa.Table("candidate_comments", meta,
                        sa.Column("id", sa.Integer, primary_key=True),
                        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.user_id")),
                        sa.Column("body", sa.String),
                        sa.Column("reminder_at", sa.DateTime, index=indexes),
                        sa.Column("reminder_user_id", sa.Integer, *extra, index=indexes),
                        sa.Column("reminder_dismissed_at", sa.DateTime))
                    meta.create_all(engine)
                    with engine.begin() as conn:
                        conn.execute(users.insert().values(user_id=1))
                        conn.execute(comments.insert().values(id=1, author_id=1, body="keep", reminder_user_id=1))
                        with Operations.context(MigrationContext.configure(conn)):
                            migration.downgrade()
                            migration.downgrade()  # Missing columns/indexes are a supported no-op.
                            self.assertEqual(conn.execute(sa.text("select body from candidate_comments")).scalar(), "keep")
                            fks = sa.inspect(conn).get_foreign_keys("candidate_comments")
                            self.assertEqual([f["constrained_columns"] for f in fks], [["author_id"]])
                            migration.upgrade()
                            migration.downgrade()
                    engine.dispose()

    def test_sqlite_inline_startup_foreign_key(self):
        spec = importlib.util.spec_from_file_location("reminders", ROOT / "migrations/versions/b5c6d7e8f9a0_add_comment_reminders.py")
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with sa.create_engine("sqlite://").begin() as conn:
            conn.exec_driver_sql("CREATE TABLE users (user_id INTEGER PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE candidate_comments (id INTEGER PRIMARY KEY)")
            conn.exec_driver_sql("ALTER TABLE candidate_comments ADD COLUMN reminder_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL")
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
            self.assertEqual([c["name"] for c in sa.inspect(conn).get_columns("candidate_comments")], ["id"])


class CIAdmission(unittest.TestCase):
    def test_exact_commit_and_latest_attempt(self):
        sha = "a" * 40
        run = dict(head_sha=sha, head_branch="main", event="push", path=".github/workflows/deploy.yml", repository={"full_name": "org/repo"}, run_number=5, run_attempt=2, id=42)
        def check(runs, jobs):
            def get(url):
                if "/workflows/" in url:
                    return {"workflow_runs": runs}
                self.assertIn("/attempts/2/jobs", url)
                return {"jobs": jobs}
            return verified(sha, "org/repo", get)
        success = [dict(name="verify", status="completed", conclusion="success")]
        self.assertTrue(check([run], success))
        self.assertFalse(check([run], [dict(name="verify", status="completed", conclusion="failure")]))
        self.assertFalse(check([run], [dict(name="verify", status="in_progress", conclusion=None)]))
        for field, bad in (("head_sha", "b" * 40), ("head_branch", "other"), ("event", "pull_request"), ("path", "other.yml")):
            self.assertFalse(check([{**run, field: bad}], success))
        self.assertFalse(check([], success))


class RestoreSafety(unittest.TestCase):
    def test_rejects_escape_links_and_nonempty_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            destination = temp / "new"
            destination.mkdir()
            for name, kind in (("../escape", tarfile.REGTYPE), ("uploads/link", tarfile.SYMTYPE), ("/absolute", tarfile.REGTYPE)):
                with tarfile.open(temp / "files.tgz", "w:gz") as tar:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
                    tar.addfile(member)
                with self.assertRaises(ValueError):
                    extract_files(temp / "files.tgz", destination)
                self.assertFalse(any(destination.iterdir()))
            with tarfile.open(temp / "files.tgz", "w:gz") as tar:
                member = tarfile.TarInfo("uploads/example.txt")
                member.size = 4
                tar.addfile(member, io.BytesIO(b"safe"))
            extract_files(temp / "files.tgz", destination)
            self.assertEqual((destination / "uploads/example.txt").read_bytes(), b"safe")
            with self.assertRaises(ValueError):
                extract_files(temp / "files.tgz", destination)


class ExistingDataIdentity(unittest.TestCase):
    def test_live_bind_and_database_must_match_proposed_backup(self):
        config = {"name": "test", "volumes": {"postgres_data": {"name": "test-db"}}, "services": {
            "db": {"environment": {"POSTGRES_DB": "db", "POSTGRES_USER": "user", "POSTGRES_PASSWORD": "secret"}},
            "backend": {"environment": {"DATABASE_URL": "postgresql+psycopg2://user:secret@db/db"},
                "volumes": [{"source": "/live/"+name, "target": "/app/"+name} for name in ("uploads", "templates", "generated")]}}}
        db = {"Mounts": [{"Destination": "/var/lib/postgresql/data", "Name": "test-db"}],
            "Config": {"Labels": {"com.docker.compose.project": "test"}, "Env": [f"{k}={v}" for k,v in config["services"]["db"]["environment"].items()]}}
        backend = {"Mounts": [{"Destination": v["target"], "Type": "bind", "Source": v["source"]} for v in config["services"]["backend"]["volumes"]],
            "Config": {"Labels": {"com.docker.compose.project": "test"}, "Env": ["DATABASE_URL="+config["services"]["backend"]["environment"]["DATABASE_URL"]]}}
        def inspect(args):
            return json.dumps([db if args[-1] == "db-id" else backend]).encode()
        with patch("deployment_data.subprocess.check_output", side_effect=inspect):
            validate_database(config, "db-id", "backend-id")
            for mount in backend["Mounts"]:
                source = mount["Source"]
                mount["Source"] = "/wrong-but-existing"
                with self.assertRaisesRegex(ValueError, "data bind differs"):
                    validate_database(config, "db-id", "backend-id")
                mount["Source"] = source
            for index, value in enumerate(db["Config"]["Env"]):
                db["Config"]["Env"][index] = value.split("=", 1)[0] + "=other"
                with self.assertRaisesRegex(ValueError, "Existing database POSTGRES"):
                    validate_database(config, "db-id", "backend-id")
                db["Config"]["Env"][index] = value
            backend["Config"]["Env"] = ["DATABASE_URL=postgresql+psycopg2://user:secret@db/other"]
            with self.assertRaisesRegex(ValueError, "DATABASE_URL differs"):
                validate_database(config, "db-id", "backend-id")


FAKE_DOCKER = r'''#!/usr/bin/env python3
import io, json, os, sys, tarfile
from pathlib import Path
a=sys.argv[1:]
root=Path(os.environ['TEST_ROOT'])
with (root/'calls').open('a') as f: f.write('docker '+' '.join(a)+'\n')
failure=os.environ.get('FAIL_AT', '')
if a[0]=='build':
    if failure=='build' and 'frontend' in a[2]: sys.exit(1)
elif a[:2]==['image','inspect']:
    print('sha256:'+'1'*64)
elif a[0]=='update' and '--restart=unless-stopped' in a and failure=='finalize':
    sys.exit(1)
elif a[0]=='inspect':
    if '--format' in a: print('healthy')
    else:
        c=json.loads((root/'config.json').read_text())
        isdb=a[-1]=='db-id'
        service=c['services']['db' if isdb else 'backend']
        mounts=[{'Destination':'/var/lib/postgresql/data','Name':'synthetic_db'}] if isdb else [{'Destination':v['target'],'Source':v['source'],'Type':'bind'} for v in service['volumes']]
        print(json.dumps([{'Mounts':mounts,'Config':{'Labels':{'com.docker.compose.project':'synthetic'},'Env':[k+'='+v for k,v in service['environment'].items()]}}]))
elif a[0]=='compose':
    a=a[a.index('-f')+2:]
    if a[0]=='config': print((root/'config.json').read_text())
    elif a[:3]==['ps','-q','db']: print('db-id')
    elif a[:4]==['ps','-a','-q','backend']: print('backend-id')
    elif a[0]=='ps': print('backend-id\nfrontend-id')
    elif a[0]=='exec':
        if 'pg_dump' in ' '.join(a):
            if failure=='backup': sys.exit(1)
            sys.stdout.buffer.write(b'synthetic database')
        elif 'psql' in ' '.join(a): print('0')
    elif a[0]=='run':
        if 'tar' in a:
            with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as t:
                m=tarfile.TarInfo('uploads/example.txt'); m.size=4; t.addfile(m,io.BytesIO(b'test'))
        if 'alembic' in a and failure=='migration': sys.exit(1)
    elif a[0]=='up' and failure=='health': sys.exit(1)
'''

FAKE_GIT = r'''#!/usr/bin/env python3
import os, sys, tarfile
from pathlib import Path
a=sys.argv[1:]
with open(Path(os.environ['TEST_ROOT'])/'calls','a') as f: f.write('git '+' '.join(a)+'\n')
if 'archive' in a:
    with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
        for name in ['Dockerfile','docker-compose.yml','app/frontend/Dockerfile','scripts/deployment_data.py']:
            t.add(Path(os.environ['TEST_SOURCE'])/name,arcname=name)
elif 'rev-parse' in a: print('a'*40)
'''


@unittest.skipUnless(sys.platform == "linux" and shutil.which("flock"), "Linux shell release contract")
class DeploymentSequence(unittest.TestCase):
    def run_deploy(self, failure="", timer=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "bin"
            binary.mkdir()
            data = root / "data"
            for folder in ("uploads", "templates", "generated"):
                (data / folder).mkdir(parents=True)
            config = {"name": "synthetic", "volumes": {"postgres_data": {"name": "synthetic_db"}}, "services": {
                "db": {"environment": {"POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test", "POSTGRES_DB": "test"}},
                "backend": {"environment": {"DATABASE_URL": "postgresql+psycopg2://test:test@db/test", "JWT_SECRET_KEY": "a"*32, "DEFAULT_ADMIN_USERNAME": "test", "DEFAULT_ADMIN_PASSWORD": "test-password", "MANISOV_ENV": "production", "AUTO_ALEMBIC_ON_STARTUP": "0"},
                    "volumes": [{"source": str(data / f), "target": "/app/"+f} for f in ("uploads", "templates", "generated")]}}}
            (root / "config.json").write_text(json.dumps(config))
            for name, source in (("docker", FAKE_DOCKER), ("git", FAKE_GIT)):
                (binary / name).write_text(source)
                (binary / name).chmod(0o755)
            (binary / "python3").write_text(f'''#!/bin/bash
if [[ "$1" == */deployment_ci.py ]]; then
  echo "ci-admission" >> "$TEST_ROOT/calls"
  [[ "$FAIL_AT" != ci ]]
else
  exec "{sys.executable}" "$@"
fi
''')
            (binary / "python3").chmod(0o755)
            env = {**os.environ, "PATH": str(binary)+":"+os.environ["PATH"], "APP_DIR": str(root), "STATE_DIR": str(root/"state"), "ENV_FILE": str(root/"env"), "LOCK_FILE": str(root/"lock"), "DEPLOY_SHA": "a"*40, "QUIESCENCE_CONFIRMED": "yes", "TEST_ROOT": str(root), "TEST_SOURCE": str(ROOT), "FAIL_AT": failure}
            args = ["bash", str(ROOT / "deploy.sh")] + (["--timer"] if timer else [])
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=30)
            calls = (root / "calls").read_text()
            marker = (root / "state/maintenance").exists()
            complete = list((root / "state/backups").glob("*/COMPLETE"))
            self.assertNotIn("reset --hard", calls)
            self.assertTrue(all(line.endswith("pg_restore --list") for line in calls.splitlines() if "pg_restore" in line))
            if not failure:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(marker)
                self.assertTrue(complete)
                self.assertLess(calls.index("docker build"), calls.index(" stop "))
                self.assertLess(calls.index("pg_dump"), calls.index("alembic upgrade"))
                self.assertLess(calls.index("-czf"), calls.index("alembic upgrade"))
                self.assertIn("--wait --wait-timeout", calls)
                self.assertTrue((root / "state/current").exists())
            else:
                self.assertNotEqual(result.returncode, 0, calls)
                if failure in {"build", "ci"}:
                    self.assertNotIn(" stop ", calls)
                    self.assertNotIn("alembic", calls)
                elif failure == "backup":
                    self.assertNotIn("alembic", calls)
                    self.assertIn("docker start backend-id frontend-id", calls)
                    self.assertFalse(marker)
                else:
                    self.assertTrue(marker)
                    self.assertTrue(complete)
                    self.assertNotIn("docker start", calls)
                    blocked = subprocess.run(args, env=env, capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(blocked.returncode, 0)
                    self.assertIn("Unresolved maintenance", blocked.stderr)

    def test_success_and_timer(self):
        self.run_deploy()
        self.run_deploy(timer=True)

    def test_failure_boundaries(self):
        for failure in ("ci", "build", "backup", "migration", "health", "finalize"):
            with self.subTest(failure=failure):
                self.run_deploy(failure)

    def test_external_flock_blocks_all_work(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp)/"lock"
            with lock.open("w") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                env = {**os.environ, "LOCK_FILE": str(lock), "LOCK_TIMEOUT": "0", "QUIESCENCE_CONFIRMED": "yes", "DEPLOY_SHA": "a"*40, "APP_DIR": str(Path(temp)/"missing"), "STATE_DIR": str(Path(temp)/"state")}
                result = subprocess.run(["bash", str(ROOT/"deploy.sh")], env=env, capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((Path(temp)/"state").exists())


if __name__ == "__main__":
    unittest.main()
