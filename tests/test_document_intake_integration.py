from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app import document_intake
from models import db
from models.schema import Candidate, CandidateComment, User


def test_populated_sqlite_startup_preserves_comments_and_adds_intake(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'existing.db'}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setenv("AUTO_ALEMBIC_ON_STARTUP", "0")
    try:
        new_tables = {"document_intake_files", "document_upload_links", "document_upload_submissions"}
        db.Base.metadata.create_all(engine, tables=[
            table for table in db.Base.metadata.sorted_tables
            if table.name not in new_tables and table.name != "candidate_comments"
        ])
        with Session(engine) as session:
            session.add(Candidate(candidate_id=1, surname="Smith"))
            session.add(User(user_id=2, username="tester", password_hash="x"))
            session.commit()
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE candidate_comments (comment_id INTEGER PRIMARY KEY, "
                "candidate_id INTEGER NOT NULL REFERENCES candidates(candidate_id), "
                "comment_text TEXT NOT NULL, created_at DATETIME NOT NULL)"
            )
            conn.exec_driver_sql(
                "INSERT INTO candidate_comments VALUES (7, 1, 'Existing comment', '2025-01-02 03:04:05')"
            )
        db.init_db()
        with Session(engine) as session:
            comment = session.get(CandidateComment, 7)
            assert comment.comment_text == "Existing comment" and comment.reminder_at is None
            comment.reminder_at = datetime(2027, 1, 1)
            comment.reminder_user_id = 2
            session.commit()
        db.init_db()
        with Session(engine) as session:
            comment = session.get(Candidate, 1).comments[0]
            assert comment.reminder_at == datetime(2027, 1, 1) and comment.reminder_user_id == 2
            assert comment.reminder_dismissed_at is None
        inspector = inspect(engine)
        assert new_tables <= set(inspector.get_table_names())
        assert {"ix_candidate_comments_reminder_at", "ix_candidate_comments_reminder_user_id"} <= {
            index["name"] for index in inspector.get_indexes("candidate_comments")
        }
        assert any(fk["constrained_columns"] == ["reminder_user_id"] and fk["referred_table"] == "users"
                   for fk in inspector.get_foreign_keys("candidate_comments"))
    finally:
        engine.dispose()


def test_lifespan_resolves_storage_late_and_joins_worker(tmp_path, monkeypatch):
    workers = []
    start = document_intake._RecognitionWorker.start

    def track(worker):
        workers.append(worker)
        start(worker)

    monkeypatch.setattr(document_intake._RecognitionWorker, "start", track)
    root = tmp_path / "unset"
    app = FastAPI()
    app.include_router(document_intake.intake_router(
        lambda: None, lambda: None, lambda: root, lambda *a: None, lambda *a: None, sessions=lambda: None,
    ))
    root = tmp_path
    with TestClient(app) as client:
        url = "/candidates/1/document-intake/status"
        assert not client.get(url).json()["enabled"]
        (root / document_intake.SWITCH_FILE).touch()
        assert client.get(url).json()["enabled"]
        assert len(workers) == 1 and workers[0].thread.is_alive()
    assert not workers[0].thread.is_alive()
