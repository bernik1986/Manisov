"""Exercise real PostgreSQL migrations and competing scan approvals on an EMPTY test DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from unittest.mock import patch
import os
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


def main():
    from sqlalchemy import create_engine, inspect, MetaData, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    url = make_url(os.environ["DATABASE_URL"])
    if (os.environ.get("MANISOV_ISOLATED_DATABASE") != "1"
            or url.database != "manisov_hardening_test"
            or url.get_backend_name() != "postgresql"):
        raise RuntimeError("Use only an explicitly isolated manisov_hardening_test PostgreSQL DB")
    engine = create_engine(url)
    if inspect(engine).get_table_names():
        raise RuntimeError("Refusing to operate on a nonempty database")

    from alembic import command
    from alembic.config import Config
    from models.db import Base
    from models.schema import Candidate, CandidateComment, User, Document, Attachment, DocumentIntakeFile
    Base.metadata.create_all(engine)
    config = Config(str(ROOT_DIR / "alembic.ini"))
    command.stamp(config, "head")
    command.downgrade(config, "a4b5c6d7e8f9")
    legacy = MetaData()
    legacy.reflect(engine)
    now = datetime.utcnow()
    with engine.begin() as db:
        db.execute(legacy.tables["users"].insert().values(
            user_id=1, username="synthetic-reviewer", password_hash="not-a-login", is_active=True, created_at=now))
        db.execute(legacy.tables["candidates"].insert().values(
            candidate_id=1, first_name="DEMO", surname="SAILOR", cv_imported=False, created_at=now, updated_at=now))
        db.execute(legacy.tables["candidate_comments"].insert().values(
            candidate_id=1, comment_text="Synthetic retained comment", created_at=now))
    command.upgrade(config, "head")
    sessions = sessionmaker(engine, autoflush=False)
    with sessions() as db:
        assert len(db.get(User, 1).auth_version) == 32
        assert db.get(Candidate, 1).surname == "SAILOR"
        assert db.scalars(select(CandidateComment)).one().comment_text == "Synthetic retained comment"
    print("PASS: PostgreSQL downgrade/upgrade preserves candidate, user and comment; auth version populated", flush=True)

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from app import document_intake
    from tests.test_document_intake import ROOT, _approval, _save, _upload, _recognize

    def get_db():
        with sessions() as db:
            yield db

    def writer(db=Depends(get_db)):
        return db.get(User, 1)

    with TemporaryDirectory(prefix="manisov-pg-integration-") as folder:
        uploads = Path(folder)
        (uploads / document_intake.SWITCH_FILE).touch()
        app = FastAPI()
        app.include_router(document_intake.intake_router(
            get_db, writer, uploads, lambda *a, **kw: None, lambda *a: None,
            sessions=sessions, recognize=_recognize,
        ))
        with TestClient(app) as client:
            first = _upload(client, (255, 0, 0))
            assert _save(client, first, _approval(first["items"]))[0]["status"] == "saved"
            existing = client.get(ROOT).json()["existing"][0]
            batches = [_upload(client, color) for color in ((254, 0, 0), (253, 0, 0))]
            approvals = [_approval(batch["items"], action="update", existing_id=existing["id"],
                                   existing_version=existing["version"], fields={"authority": f"Reviewer {index}"})
                         for index, batch in enumerate(batches)]
            barrier, entered, release = Barrier(2), Event(), Event()
            approve, field_updates = document_intake._approve, document_intake._field_updates

            def overlap(*args, **kwargs):
                barrier.wait(timeout=10)
                return approve(*args, **kwargs)

            def hold_writer(*args):
                changes = field_updates(*args)
                entered.set()
                assert release.wait(timeout=10)
                return changes

            with patch.object(document_intake, "_approve", overlap), patch.object(document_intake, "_field_updates", hold_writer):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(_save, client, batch, approval)
                               for batch, approval in zip(batches, approvals)]
                    try:
                        assert entered.wait(timeout=10)
                    finally:
                        release.set()
                    results = [future.result(timeout=15)[0] for future in futures]
            assert sorted(result["status"] for result in results) == ["error", "saved"], results
            loser = next(index for index, result in enumerate(results) if result["status"] == "error")
            assert results[loser]["error"] == "record_changed", results
            with sessions() as db:
                assert db.scalars(select(Document)).one().issuing_authority == f"Reviewer {1-loser}"
                assert all(Path(row.file_path).is_file() for row in db.scalars(select(Attachment)))
                draft = db.get(DocumentIntakeFile, batches[loser]["items"][0]["file_id"])
                assert draft.content and not draft.saved_key
            print("PASS: concurrent PostgreSQL approvals reject stale version and preserve losing scan", flush=True)
    engine.dispose()


if __name__ == "__main__":
    main()
