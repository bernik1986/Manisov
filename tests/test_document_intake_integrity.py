"""Desired behavior for scan recovery and overlapping approvals; synthetic data only."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from app import document_intake
from models.schema import Attachment, AuditLog, Candidate, Document, DocumentIntakeFile
from tests.test_document_intake import ROOT, _approval, _png, _save, _upload, intake


def _saved_scan(client, sessions):
    batch = _upload(client, (255, 0, 0))
    assert _save(client, batch, _approval(batch["items"]))[0]["status"] == "saved"
    with sessions() as db:
        attachment = db.scalars(select(Attachment)).one()
        return attachment.attachment_id, Path(attachment.file_path)


def _replacement(client, *colors, fields=None):
    existing = client.get(ROOT).json()["existing"][0]
    batch = _upload(client, *colors)
    return batch, _approval(
        batch["items"], action="update", existing_id=existing["id"],
        existing_version=existing["version"], fields=fields or {},
    )


@pytest.mark.parametrize("state", ["missing", "empty", "truncated", "directory", "unreadable"])
def test_identical_reupload_repairs_unavailable_scan(intake, monkeypatch, state):
    client, sessions, uploads = intake
    attachment_id, old_path = _saved_scan(client, sessions)
    assert old_path.is_relative_to(uploads)
    original_bytes = old_path.read_bytes()
    old_path.unlink()
    if state == "empty":
        old_path.touch()
    elif state == "truncated":
        old_path.write_bytes(original_bytes[:128])
    elif state == "directory":
        old_path.mkdir()
    elif state == "unreadable":
        old_path.write_bytes(b"leave existing bytes alone")
        original_open = Path.open

        def denied(path, *args, **kwargs):
            if path == old_path:
                raise PermissionError("synthetic unreadable attachment")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", denied)
    # Repeated identical pages should still produce only one restored file.
    batch, approval = _replacement(client, (255, 0, 0), (255, 0, 0))
    assert _save(client, batch, approval)[0]["status"] == "saved"
    assert _save(client, batch, approval)[0]["status"] == "saved"
    with sessions() as db:
        attachment = db.scalars(select(Attachment)).one()
        restored = Path(attachment.file_path)
        assert attachment.attachment_id == attachment_id
        assert restored != old_path and restored.is_relative_to(uploads)
        assert restored.read_bytes().startswith(b"%PDF")
        assert restored.stat().st_size == attachment.file_size_bytes
        assert attachment.checksum == document_intake.sha256(_png((255, 0, 0))).hexdigest()
        for item in batch["items"]:
            draft = db.get(DocumentIntakeFile, item["file_id"])
            assert draft.content is None and draft.content_type is None and draft.saved_key
    assert old_path.exists() == (state != "missing")
    if state == "empty":
        assert old_path.stat().st_size == 0
    if state == "truncated":
        assert old_path.read_bytes() == original_bytes[:128]
    if state == "directory":
        assert old_path.is_dir()


@pytest.mark.parametrize("known_size", [False, True])
def test_available_identical_scan_is_not_reconverted(intake, monkeypatch, known_size):
    client, sessions, uploads = intake
    attachment_id, path = _saved_scan(client, sessions)
    original = path.read_bytes()
    if not known_size:
        with sessions.begin() as db:
            db.get(Attachment, attachment_id).file_size_bytes = None
    batch, approval = _replacement(client, (255, 0, 0))
    monkeypatch.setattr(document_intake, "prepare_attachment_bytes", Mock(side_effect=AssertionError("dedup")))
    assert _save(client, batch, approval)[0]["status"] == "saved"
    with sessions() as db:
        attachment = db.scalars(select(Attachment)).one()
        assert attachment.attachment_id == attachment_id and attachment.file_path == str(path)
    assert path.read_bytes() == original and list(uploads.glob("*.pdf")) == [path]


@pytest.mark.parametrize("failure", ["later_conversion", "exclusive_create", "flush", "commit_before", "commit_after"])
def test_failed_repair_preserves_draft_and_transaction_boundary(intake, monkeypatch, failure):
    client, sessions, uploads = intake
    attachment_id, old_path = _saved_scan(client, sessions)
    old_path.unlink()
    batch, approval = _replacement(client, (255, 0, 0), (254, 0, 0), fields={"authority": "New authority"})
    original_convert = document_intake.prepare_attachment_bytes
    original_commit, original_flush = sessions.class_.commit, sessions.class_.flush
    occupied = uploads / (("e" * 32) + ".pdf")

    def conversion(suffix, content):
        if content == _png((254, 0, 0)):
            raise HTTPException(400, "invalid_scan")
        return original_convert(suffix, content)

    def commit(db):
        if failure == "commit_after":
            original_commit(db)
        raise OperationalError("COMMIT", {}, RuntimeError("synthetic lost response"))

    def flush(db, *args, **kwargs):
        if any(isinstance(row, AuditLog) for row in db.new):
            raise RuntimeError("synthetic failure after writing both scans")
        return original_flush(db, *args, **kwargs)

    with monkeypatch.context() as patch:
        if failure == "later_conversion":
            patch.setattr(document_intake, "prepare_attachment_bytes", conversion)
        elif failure == "exclusive_create":
            occupied.write_bytes(b"%PDF-existing-synthetic-file")
            patch.setattr(document_intake, "uuid4", lambda: SimpleNamespace(hex="e" * 32))
        elif failure == "flush":
            patch.setattr(sessions.class_, "flush", flush)
        else:
            patch.setattr(sessions.class_, "commit", commit)
        result = _save(client, batch, approval)[0]
    expected_error = ("save_outcome_unknown" if failure.startswith("commit") else
                      "invalid_scan" if failure == "later_conversion" else "save_failed")
    assert result["error"] == expected_error
    with sessions() as db:
        repaired = failure == "commit_after"
        attachment = db.get(Attachment, attachment_id)
        assert (attachment.file_path != str(old_path)) == repaired
        assert db.scalars(select(Document)).one().issuing_authority == ("New authority" if repaired else None)
        assert len(db.scalars(select(Attachment)).all()) == (2 if repaired else 1)
        for item in batch["items"]:
            draft = db.get(DocumentIntakeFile, item["file_id"])
            assert (draft.content is None) == repaired
            assert bool(draft.saved_key) == repaired
        if repaired:
            assert all(Path(a.file_path).is_file() for a in db.scalars(select(Attachment)))
    if failure == "exclusive_create":
        assert occupied.read_bytes() == b"%PDF-existing-synthetic-file"
        assert list(uploads.glob("*.pdf")) == [occupied]
    elif not failure.startswith("commit"):
        assert not list(uploads.glob("*.pdf"))
    else:
        # Uncertain COMMIT outcomes retain new bytes, even when rollback worked.
        assert len(list(uploads.glob("*.pdf"))) == 2
    assert not old_path.exists()
    assert _save(client, batch, approval)[0]["status"] == "saved"
    with sessions() as db:
        assert len(db.scalars(select(Attachment)).all()) == 2
        assert all(Path(a.file_path).is_file() for a in db.scalars(select(Attachment)))


@pytest.mark.parametrize("journal", ["DELETE", "WAL"])
@pytest.mark.parametrize("explicit_reads", [False, True])
@pytest.mark.parametrize("scenario", ["fields", "scan_only", "same_draft", "create"])
def test_overlapping_sqlite_approvals_are_serialized(intake, monkeypatch, journal, explicit_reads, scenario):
    client, sessions, uploads = intake
    sessions.configure(autoflush=False)
    if scenario != "create":
        _saved_scan(client, sessions)
    existing = client.get(ROOT).json()["existing"]
    batches = [_upload(client, color) for color in ((254, 0, 0), (253, 0, 0))]
    options = {} if scenario == "create" else {
        "action": "update", "existing_id": existing[0]["id"], "existing_version": existing[0]["version"],
    }
    approvals = [_approval(batch["items"], fields={"number": "SB-432", **(
        {"authority": f"Reviewer {index}"} if scenario == "fields" else {}
    )}, **options) for index, batch in enumerate(batches)]
    if scenario == "same_draft":
        batches[1], approvals[1] = batches[0], approvals[0]
    engine = sessions.kw["bind"]
    with engine.connect() as connection:
        assert connection.exec_driver_sql(f"PRAGMA journal_mode={journal}").scalar().upper() == journal
    with sessions() as db:
        candidate_updated_at = db.get(Candidate, 1).updated_at

    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    if explicit_reads:
        event.listen(engine, "begin", begin)
    barrier, entered, release = Barrier(2), Event(), Event()
    approve, field_updates = document_intake._approve, document_intake._field_updates

    def overlap(*args, **kwargs):
        # Both authenticated sessions already read before requesting a write lock.
        barrier.wait(timeout=10)
        return approve(*args, **kwargs)

    def hold_writer(*args):
        changes = field_updates(*args)
        entered.set()
        assert release.wait(timeout=10)
        return changes

    monkeypatch.setattr(document_intake, "_approve", overlap)
    monkeypatch.setattr(document_intake, "_field_updates", hold_writer)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_save, client, batch, approval)
                       for batch, approval in zip(batches, approvals)]
            try:
                assert entered.wait(timeout=10)
            finally:
                release.set()
            results = [future.result(timeout=15)[0] for future in futures]
    finally:
        if explicit_reads:
            event.remove(engine, "begin", begin)
    if scenario == "same_draft":
        assert [result["status"] for result in results] == ["saved", "saved"]
        winner, loser = 0, None
    else:
        assert sorted(result["status"] for result in results) == ["error", "saved"], results
        winner = next(index for index, result in enumerate(results) if result["status"] == "saved")
        loser = 1 - winner
        assert results[loser]["error"] == ("existing_duplicate" if scenario == "create" else "record_changed")
    with sessions() as db:
        attachment = db.scalars(select(Attachment)).one()
        document = db.scalars(select(Document)).one()
        assert Path(attachment.file_path).is_file()
        assert len(list(uploads.glob("*.pdf"))) == 1
        assert db.get(Candidate, 1).updated_at == candidate_updated_at
        if scenario == "fields":
            assert document.issuing_authority == f"Reviewer {winner}"
        saved = db.get(DocumentIntakeFile, batches[winner]["items"][0]["file_id"])
        assert saved.saved_key and saved.content is None
        if loser is not None:
            draft = db.get(DocumentIntakeFile, batches[loser]["items"][0]["file_id"])
            assert not draft.saved_key and draft.content == _png(((254, 0, 0), (253, 0, 0))[loser])
        assert len(db.scalars(select(AuditLog).where(AuditLog.action.like("document_intake.%"))).all()) == (
            1 if scenario == "create" else 2
        )


def test_postgresql_keeps_candidate_row_lock():
    db = Mock()
    db.get_bind.return_value.dialect = postgresql.dialect()
    assert document_intake._lock_approval_candidate(db, 7) is db.scalar.return_value
    statement = db.scalar.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert statement.compile().params == {"candidate_id_1": 7}
    db.execute.assert_not_called()
    db.rollback.assert_not_called()
    db.expire_all.assert_not_called()
