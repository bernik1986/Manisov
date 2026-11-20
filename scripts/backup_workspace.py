"""Create a verified local rollback archive, including uncommitted work and SQLite data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from zipfile import ZipFile, ZIP_DEFLATED


def backup_workspace(root: Path) -> Path:
    destination = root / "backups" / ("before-seafarer-intake-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    destination.mkdir(parents=True, exist_ok=False)
    excluded = {".git", "backups", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".playwright", "dist", "test-results", "playwright-report", "runtime_logs", ".agents", ".codex"}
    manifest = {}
    archive_path = destination / "workspace.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for directory, directories, files in os.walk(root):
            relative = Path(directory).relative_to(root)
            verification_copies = {"upstream-cv-reference", "intake-baseline", "rollback-verified", "restored-before-intake"}
            directories[:] = [name for name in directories if name not in excluded and not (relative == Path("generated") and (name.startswith(("pytest", "audit-", "hardening-")) or name in verification_copies))]
            for name in files:
                path = Path(directory) / name
                if path.suffix in {".log", ".pyc"} or name.endswith(("-wal", "-shm")):
                    continue
                if path.suffix in {".db", ".sqlite3"}:
                    with tempfile.TemporaryDirectory(dir=destination) as tmp:
                        snapshot = Path(tmp) / name
                        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source, closing(sqlite3.connect(snapshot)) as target:
                            source.backup(target)
                            assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                        content = snapshot.read_bytes()
                else:
                    content = path.read_bytes()
                entry = path.relative_to(root).as_posix()
                archive.writestr(entry, content)
                manifest[entry] = hashlib.sha256(content).hexdigest()
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for entry, digest in manifest.items():
            assert hashlib.sha256(archive.read(entry)).hexdigest() == digest
    for name, args in {"working-tree.patch": ["diff", "--binary", "HEAD"], "status.txt": ["status", "--short"], "head.txt": ["rev-parse", "HEAD"]}.items():
        (destination / name).write_bytes(subprocess.check_output(["git", *args], cwd=root))
    subprocess.run(["git", "bundle", "create", str(destination / "history.bundle"), "--all"], cwd=root, check=True)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"backup": str(destination), "files": len(manifest), "archive_bytes": archive_path.stat().st_size, "verified": True}))
    return destination


if __name__ == "__main__":
    backup_workspace(Path(__file__).resolve().parents[1])
