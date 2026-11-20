"""Recovery and confirmation regressions using per-test SQLite databases."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app import document_intake
from models.schema import Attachment, Certificate, Document, DocumentIntakeFile, Notification
from tests.test_document_intake import (
    ROOT, _approval, _png, _queue, _recognize, _save, _upload, _wait_batch, intake,
)


def test_type_mismatch_needs_single_explicit_confirmation(intake):
    client, sessions, _ = intake
    batch = _upload(client, (255, 0, 0), (0, 255, 0))
    first, second = batch["items"]
    with sessions.begin() as db:
        row = db.get(DocumentIntakeFile, first["file_id"])
        row.result = {**row.result, "warnings": ["type_hint_mismatch"]}
    approval = _approval([first])
    assert _save(client, batch, approval)[0]["error"] == "type_hint_mismatch"
    approval["confirm_holder"] = True
    assert _save(client, batch, approval)[0]["error"] == "type_hint_mismatch"
    approval["confirm_type_mismatch"] = True
    assert _save(client, batch, approval, bulk=True)[0]["error"] == "type_hint_mismatch"
    other = _approval([second], kind="certificate:AFF")
    assert _save(client, batch, approval, other)[0]["error"] == "type_hint_mismatch"
    with sessions() as db:
        assert db.get(DocumentIntakeFile, first["file_id"]).content == _png((255, 0, 0))
    assert _save(client, batch, approval)[0]["status"] == "saved"
    assert _save(client, batch, approval)[0]["status"] == "saved"


@pytest.mark.parametrize("value", ["true", 1, None])
def test_type_confirmation_requires_json_boolean(value):
    with pytest.raises(ValueError):
        document_intake.Approval.model_validate({
            **_approval([{"file_id": "a" * 32}]), "confirm_type_mismatch": value,
        })


def test_stale_scan_only_review_cannot_replace_newer_attachment(intake):
    client, sessions, _ = intake
    original = _upload(client, (255, 0, 0))
    assert _save(client, original, _approval(original["items"]))[0]["status"] == "saved"
    existing = client.get(ROOT).json()["existing"][0]
    options = dict(action="update", existing_id=existing["id"], existing_version=existing["version"])
    first, stale = (_upload(client, color) for color in ((254, 0, 0), (253, 0, 0)))
    assert _save(client, first, _approval(first["items"], **options))[0]["status"] == "saved"
    assert _save(client, stale, _approval(stale["items"], **options))[0]["error"] == "record_changed"
    current = client.get(ROOT).json()["existing"][0]
    assert existing["fields"] == current["fields"] and existing["version"] != current["version"]
    with sessions() as db:
        [attachment] = db.scalars(select(Attachment)).all()
        assert attachment.checksum == document_intake.sha256(_png((254, 0, 0))).hexdigest()
        assert Path(attachment.file_path).exists()


@pytest.mark.parametrize("key,model,expiry_column", [
    ("document:SB", Document, "date_of_expiry"), ("certificate:AFF", Certificate, "expiry_date"),
])
def test_unlimited_renewal_clears_expiry_and_active_alert(intake, key, model, expiry_column):
    client, sessions, _ = intake
    original = _upload(client, (255, 0, 0))
    create = _approval(original["items"], kind=key, fields={"number": "A1", "expiry_date": "2020-02-01"})
    assert _save(client, original, create)[0]["status"] == "saved"
    with sessions() as db:
        assert db.scalars(select(Notification)).one().sent is False
    existing = client.get(ROOT).json()["existing"][0]
    new = _upload(client, (254, 0, 0))
    update = _approval(new["items"], kind=key, action="update", existing_id=existing["id"],
                       existing_version=existing["version"],
                       fields={"issue_date": "2024-01-01", "expiry_date": None, "unlimited_validity": True})
    assert _save(client, new, update)[0]["status"] == "saved"
    with sessions() as db:
        record = db.get(model, existing["id"])
        assert record.unlimited_validity and getattr(record, expiry_column) is None
        assert not db.scalars(select(Notification).where(Notification.sent.is_(False))).all()


def test_occupied_visa_slot_requires_update(intake):
    client, sessions, _ = intake
    key = next(spec.key for spec in document_intake.CANONICAL if spec.kind == "visa")
    first, second = (_upload(client, color) for color in ((255, 0, 0), (254, 0, 0)))
    assert _save(client, first, _approval(first["items"], kind=key, fields={"number": "ABC"}))[0]["status"] == "saved"
    assert _save(client, second, _approval(second["items"], kind=key, fields={"number": "DEF"}))[0]["error"] == "existing_duplicate"
    with sessions() as db:
        assert db.scalars(select(Document)).one().document_number == "ABC"


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_timeout_advances_queue_and_retry_preserves_hint(intake, monkeypatch):
    client, sessions, uploads = intake
    batch = _queue(client, (255, 0, 0), (0, 255, 0))
    with sessions.begin() as db:
        row = db.scalars(select(DocumentIntakeFile).order_by(DocumentIntakeFile.position)).first()
        row.result = {"pending": True, "type_hint": "document:SB"}
    calls = []

    def bounded(path, catalog, *, stop_event):
        assert stop_event is worker.stopping
        calls.append(path)
        if len(calls) == 1:
            raise TimeoutError("private native error")
        return _recognize(path, catalog)

    monkeypatch.setattr(document_intake, "recognize_document_bounded", bounded)
    worker = document_intake._RecognitionWorker(sessions, uploads)
    assert worker.process_next()
    assert worker.process_next()
    assert not worker.process_next()
    completed = _wait_batch(client, batch["batch_id"])
    failed = completed["items"][0]
    assert failed["error"] == "recognition_timeout" and failed["retryable"]
    assert failed["type_hint"] == "document:SB"
    with sessions() as db:
        assert db.get(DocumentIntakeFile, failed["file_id"]).content == _png((255, 0, 0))
    assert client.post(f"{ROOT}/{batch['batch_id']}/retry").status_code == 202
    assert worker.process_next()
    assert not worker.process_next()
    assert _wait_batch(client, batch["batch_id"])["items"][0]["type_key"] == "document:SB"


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_shutdown_leaves_original_pending_for_recovery(intake, monkeypatch):
    client, sessions, uploads = intake
    batch = _queue(client, (255, 0, 0))

    def stopped(*args, **kwargs):
        raise InterruptedError("stopped")

    monkeypatch.setattr(document_intake, "recognize_document_bounded", stopped)
    assert not document_intake._RecognitionWorker(sessions, uploads).process_next()
    with sessions() as db:
        row = db.scalars(select(DocumentIntakeFile)).one()
        assert row.result["pending"] and row.content == _png((255, 0, 0))
    assert document_intake._RecognitionWorker(sessions, uploads, _recognize).process_next()
    assert _wait_batch(client, batch["batch_id"])["items"][0]["fields"]["number"] == "SB-432"


@pytest.mark.parametrize("warning", ["ocr_timeout", "ocr_failed", "ocr_unavailable", "recognition_time_limit"])
def test_partial_recognition_is_retryable_without_erasing_scan(intake, warning):
    client, sessions, _ = intake
    batch = _upload(client, (255, 0, 0))
    file_id = batch["items"][0]["file_id"]
    with sessions.begin() as db:
        row = db.get(DocumentIntakeFile, file_id)
        row.result = {**row.result, "warnings": [warning]}
    result = _wait_batch(client, batch["batch_id"])
    assert result["items"][0]["retryable"]
    with sessions() as db:
        assert db.get(DocumentIntakeFile, file_id).content == _png((255, 0, 0))


@pytest.mark.parametrize("committed,rollback_fails", [(True, False), (False, False), (True, True)])
def test_unknown_commit_never_deletes_approved_bytes(intake, monkeypatch, committed, rollback_fails):
    client, sessions, uploads = intake
    batch = _upload(client, (255, 0, 0))
    approval = _approval(batch["items"])
    commit, rollback = sessions.class_.commit, sessions.class_.rollback
    failures = []

    def lost_response(db):
        if committed:
            commit(db)
        raise OperationalError("COMMIT", {}, RuntimeError("connection lost"))

    def broken_rollback(db):
        if not failures:
            failures.append(True)
            raise OperationalError("ROLLBACK", {}, RuntimeError("connection lost"))
        rollback(db)

    with monkeypatch.context() as patch:
        patch.setattr(sessions.class_, "commit", lost_response)
        if rollback_fails:
            patch.setattr(sessions.class_, "rollback", broken_rollback)
        assert _save(client, batch, approval)[0]["error"] == "save_outcome_unknown"
    [retained] = uploads.glob("*.pdf")
    assert retained.read_bytes().startswith(b"%PDF")
    with sessions() as db:
        draft = db.get(DocumentIntakeFile, batch["items"][0]["file_id"])
        assert bool(draft.saved_key) == committed
        assert bool(draft.content) != committed
        if committed:
            attachment = db.scalars(select(Attachment)).one()
            assert Path(attachment.file_path) == retained
    assert _save(client, batch, approval)[0]["status"] == "saved"
    with sessions() as db:
        assert len(db.scalars(select(Document)).all()) == 1
        [attachment] = db.scalars(select(Attachment)).all()
        assert Path(attachment.file_path).read_bytes().startswith(b"%PDF")
    assert len(list(uploads.glob("*.pdf"))) == (1 if committed else 2)


def test_failed_exclusive_create_does_not_remove_existing_file(intake, monkeypatch):
    client, sessions, uploads = intake
    batch = _upload(client, (255, 0, 0))
    occupied = uploads / (("e" * 32) + ".pdf")
    occupied.write_bytes(b"%PDF-existing-file")
    monkeypatch.setattr(document_intake, "uuid4", lambda: SimpleNamespace(hex="e" * 32))
    assert _save(client, batch, _approval(batch["items"]))[0]["error"] == "save_failed"
    assert occupied.read_bytes() == b"%PDF-existing-file"
    with sessions() as db:
        row = db.get(DocumentIntakeFile, batch["items"][0]["file_id"])
        assert row.content and not row.saved_key
        assert not db.scalars(select(Attachment)).all()
