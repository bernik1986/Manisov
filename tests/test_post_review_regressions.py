"""Regression cases discovered by the independent post-fix review."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import subprocess
import sys
import time

from alembic.migration import MigrationContext
from alembic.operations import Operations
import bcrypt
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from fastapi import HTTPException

from app import application_runtime, document_intake_runtime, main
from models.db import Base
from models.schema import Candidate, Document, Notification


def _auth_migration():
    path = Path(__file__).resolve().parents[1] / "migrations/versions/21b8a06c7d42_add_auth_version.py"
    spec = importlib.util.spec_from_file_location("auth_migration_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("foreign_key", ["ON DELETE CASCADE", ""])
def test_sqlite_auth_migration_never_rebuilds_referenced_users(foreign_key):
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.exec_driver_sql("PRAGMA foreign_keys=ON")
        db.exec_driver_sql("CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT NOT NULL)")
        db.exec_driver_sql(f"CREATE TABLE referenced_data (owner_id INTEGER REFERENCES users(user_id) {foreign_key}, content BLOB)")
        db.exec_driver_sql("INSERT INTO users VALUES (1, 'synthetic'), (2, 'second')")
        db.exec_driver_sql("INSERT INTO referenced_data VALUES (1, X'010203')")
        with Operations.context(MigrationContext.configure(db)):
            migration = _auth_migration()
            migration.upgrade()
            original = dict(db.execute(text("SELECT user_id, auth_version FROM users")).all())
            assert len(set(original.values())) == 2
            migration.upgrade()
            assert dict(db.execute(text("SELECT user_id, auth_version FROM users")).all()) == original
            migration.downgrade()
            migration.upgrade()
        assert db.exec_driver_sql("SELECT content FROM referenced_data").scalar_one() == b"\x01\x02\x03"
        assert db.exec_driver_sql("SELECT count(*) FROM users").scalar_one() == 2
        assert not db.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()


def test_full_login_throttle_rejects_before_password_verification(monkeypatch):
    main.login_throttle_reset_for_testing()
    monkeypatch.setattr(main, "LOGIN_TRACKED_KEYS_LIMIT", 1)
    request = Request({"type": "http", "client": ("192.0.2.20", 1234), "headers": []})
    try:
        main._login_throttle_record_failure(request, "already-tracked")
        with pytest.raises(HTTPException) as error:
            main._login_throttle_check_allowed(request, "new-target")
        assert error.value.status_code == 429
        main._login_throttle_check_allowed(request, "already-tracked")
    finally:
        main.login_throttle_reset_for_testing()


@pytest.mark.parametrize("password", ["legacy-password", "x" * 90, "\u041f" * 40])
def test_legacy_bcrypt_verification_works_with_current_bcrypt(password):
    stored = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=4)).decode("ascii")
    assert main._verify_password(password, stored)
    assert not main._verify_password("wrong-password", stored)
    assert not main._verify_password(password, "$2b$invalid")


@pytest.mark.parametrize("worker", ["application", "recognition"])
def test_parser_timeout_removes_child_owned_scratch(tmp_path, monkeypatch, worker):
    source, ready = tmp_path / "synthetic.doc", tmp_path / "ready.txt"
    source.write_bytes(b"synthetic")
    popen = subprocess.Popen
    processes = []
    code = ("import tempfile,time,sys; from pathlib import Path; "
            "folder=Path(tempfile.mkdtemp()); (folder/'private.txt').write_text('synthetic'); "
            "Path(sys.argv[1]).write_text(str(folder)); time.sleep(60)")

    def launch(args, **kwargs):
        if "-m" not in args:
            return popen(args, **kwargs)
        process = popen([sys.executable, "-c", code, str(ready)], **kwargs)
        processes.append(process)
        until = time.monotonic() + 10
        while not ready.exists() and process.poll() is None and time.monotonic() < until:
            time.sleep(0.01)
        assert ready.exists()
        return process

    monkeypatch.setattr(application_runtime.subprocess, "Popen", launch)
    try:
        with pytest.raises(TimeoutError):
            if worker == "application":
                application_runtime.parse_application_bounded(source, timeout=0.01)
            else:
                document_intake_runtime.recognize_document_bounded(source, [], timeout=0.1)
        assert not Path(ready.read_text()).exists()
        assert all(process.poll() is not None for process in processes)
    finally:
        for process in processes:
            if process.poll() is None:
                application_runtime._terminate(process)


def test_stale_global_scan_does_not_retire_a_new_candidates_notification(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'notifications.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, autoflush=False)
    with sessions.begin() as db:
        db.add(Candidate(candidate_id=1, surname="OLD"))
    collect = main._collect_active_notification_keys_for_candidate
    created = False

    def create_during_scan(candidate, **kwargs):
        nonlocal created
        if not created:
            created = True
            with sessions() as other:
                other.add(Candidate(candidate_id=2, surname="NEW"))
                other.flush()
                other.add(Document(candidate_id=2, document_type="Synthetic passport",
                                   date_of_expiry=date.today() - timedelta(days=1)))
                other.commit()
                main._sync_notifications(other, only_candidate_id=2)
        return collect(candidate, **kwargs)

    monkeypatch.setattr(main, "_collect_active_notification_keys_for_candidate", create_during_scan)
    try:
        with sessions() as db:
            main._sync_notifications(db)
        with sessions() as db:
            notification = db.scalars(select(Notification).where(Notification.candidate_id == 2)).one()
            assert notification.sent is False
    finally:
        engine.dispose()
