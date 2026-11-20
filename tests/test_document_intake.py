from contextlib import nullcontext
from errno import ENOSPC
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic, sleep

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DataError, OperationalError
from sqlalchemy.orm import sessionmaker

from app import document_intake
from app.main import _sync_notifications
from models.db import Base
from models.schema import Attachment, Candidate, Certificate, Document, DocumentIntakeFile, User


def _png(color):
    stream = BytesIO()
    Image.new("RGB", (30, 20), color).save(stream, format="PNG")
    return stream.getvalue()


def _recognize(path, catalog, *, deadline=None):
    if path.suffix == ".pdf":
        return {"type_key": "certificate:AFF", "fields": {}, "warnings": [], "page_count": 2}
    with Image.open(path) as image:
        r, g, b = image.getpixel((0, 0))
    key = "document:SB" if r > 0 else "certificate:AFF" if g > 0 else None
    assert key is None or key in {entry["key"] for entry in catalog}
    return {
        "type_key": key, "page_count": 1, "warnings": [] if key else ["unknown_type"],
        "fields": {"number": "SB-432" if r else "AFF-555",
                   "holder_name": "Other Person" if b else "Demo Sailor"},
    }


@pytest.fixture()
def intake(tmp_path, request):
    engine = create_engine(f"sqlite:///{tmp_path / 'pilot.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as db:
        db.add_all([
            Candidate(candidate_id=1, first_name="Demo", surname="Sailor"),
            Candidate(candidate_id=2, first_name="Other", surname="Sailor"),
            User(user_id=1, username="reviewer", password_hash="x"),
            User(user_id=2, username="other-recruiter", password_hash="x"),
        ])
        db.commit()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / document_intake.SWITCH_FILE).touch()

    def get_db():
        with sessions() as db:
            yield db

    def writer(x_user: int = Header(default=1), db=Depends(get_db)):
        if x_user == 3:
            raise HTTPException(403)
        return db.get(User, x_user)

    app = FastAPI()
    app.include_router(document_intake.intake_router(
        get_db, writer, uploads, _sync_notifications, lambda *args: None,
        sessions=sessions, recognize=lambda *args, **kwargs: _recognize(*args, **kwargs),
    ))
    client = TestClient(app)
    with (client if getattr(request, "param", True) else nullcontext(client)):
        yield client, sessions, uploads
    engine.dispose()


ROOT = "/candidates/1/document-intake"


def _queue(client, *colors):
    response = client.post(ROOT, files=[
        ("files", (f"page {index}.png", _png(color), "image/png")) for index, color in enumerate(colors)
    ])
    assert response.status_code == 202, response.text
    return response.json()


def _wait_batch(client, batch_id, *, processed=None):
    until = monotonic() + 10
    while monotonic() < until:
        response = client.get(ROOT)
        assert response.status_code == 200
        for batch in response.json()["batches"]:
            if batch["batch_id"] == batch_id and batch["processed"] >= (
                batch["total"] if processed is None else processed
            ):
                return batch
        sleep(0.025)
    pytest.fail("Intake worker did not process the expected files")


def _upload(client, *colors):
    batch = _queue(client, *colors)
    return _wait_batch(client, batch["batch_id"])


def test_background_queue_reports_progress_and_attempts_every_file(intake, monkeypatch):
    client, _, _ = intake
    started, release = Event(), Event()
    original = _recognize
    attempts = []

    def recognize(path, catalog, **kwargs):
        attempts.append(kwargs)
        if len(attempts) == 2:
            started.set()
            if not release.wait(10):
                raise RuntimeError("test did not release worker")
            raise ValueError("bad file must not stop the queue")
        return original(path, catalog, **kwargs)

    monkeypatch.setitem(globals(), "_recognize", recognize)
    try:
        batch = _queue(client, *((255, 0, 0),) * 34)
        assert (batch["processed"], batch["total"], batch["items"]) == (0, 34, [])
        assert started.wait(5)
        pending = _wait_batch(client, batch["batch_id"], processed=1)
        assert (pending["processed"], pending["items"]) == (1, [])
        assert client.get(ROOT, headers={"x-user": "2"}).json()["batches"] == []
        another = _queue(client, (0, 255, 0))
        assert another["processed"] == 0
    finally:
        release.set()
    finished = _wait_batch(client, batch["batch_id"])
    assert finished["processed"] == 34
    assert finished["items"][1]["error"] == "invalid_scan"
    assert finished["items"][-1]["fields"]["number"] == "SB-432"
    assert _wait_batch(client, another["batch_id"])["processed"] == 1
    assert attempts == [{}] * 35


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_new_worker_resumes_persisted_file(intake):
    client, sessions, uploads = intake
    marker = uploads / document_intake.SWITCH_FILE
    marker.unlink()
    with sessions.begin() as db:
        db.add(DocumentIntakeFile(
            file_id="a" * 32, batch_id="b" * 32, candidate_id=1, owner_id=1, position=0,
            created_at=document_intake._now(), name="persisted.png", content_type="image/png",
            content=_png((255, 0, 0)), result={"pending": True},
        ))
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)
    marker.touch()
    worker.start()
    try:
        result = _wait_batch(client, "b" * 32)
        assert result["items"][0]["fields"]["number"] == "SB-432"
    finally:
        worker.stop()


@pytest.mark.parametrize("intake", [False], indirect=True)
@pytest.mark.parametrize("failure,error", [(RuntimeError, "recognition_failed"), (ValueError, "invalid_scan")])
def test_persistent_preparation_failure_does_not_pin_oldest_job(intake, monkeypatch, failure, error):
    client, sessions, uploads = intake
    poisoned = _queue(client, (255, 0, 0))
    response = client.post(ROOT.replace("/1/", "/2/"), files=[
        ("files", ("good.png", _png((0, 255, 0)), "image/png")),
    ])
    assert response.status_code == 202
    original = document_intake.intake_catalog
    attempts = []

    def prepare(candidate):
        attempts.append(candidate.candidate_id)
        if candidate.candidate_id == 1:
            raise failure("persistent catalog failure; private details must not be stored")
        return original(candidate)

    monkeypatch.setattr(document_intake, "intake_catalog", prepare)
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)
    assert worker.process_next()
    # A new worker must also skip the terminal poison job.
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)
    assert worker.process_next()
    assert not worker.process_next()
    assert attempts == [1, 2]
    with sessions() as db:
        rows = db.scalars(select(DocumentIntakeFile).order_by(DocumentIntakeFile.created_at)).all()
        assert rows[0].batch_id == poisoned["batch_id"]
        assert rows[0].result == {"type_key": None, "fields": {}, "warnings": [], "page_count": 0, "error": error}
        assert rows[0].content == _png((255, 0, 0)) and rows[0].content_type == "image/png"
        assert rows[1].result["fields"]["number"] == "AFF-555"
        assert rows[1].content and not rows[1].result.get("pending")


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_full_temporary_disk_retains_originals_and_owner_can_retry(intake, monkeypatch):
    client, sessions, uploads = intake
    colors = [(255, 0, 0), (0, 255, 0)]
    batch = _queue(client, *colors)
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)

    def full_disk(**_kwargs):
        raise OSError(ENOSPC, "synthetic full disk")

    with monkeypatch.context() as patch:
        patch.setattr(document_intake, "TemporaryDirectory", full_disk)
        assert worker.process_next()
        assert worker.process_next()
        assert not worker.process_next()
    with sessions() as db:
        rows = db.scalars(select(DocumentIntakeFile).order_by(DocumentIntakeFile.position)).all()
        assert [row.content for row in rows] == [_png(color) for color in colors]
    failed = _wait_batch(client, batch["batch_id"])
    assert all(item["retryable"] and item["error"] == "recognition_failed" for item in failed["items"])
    retry_url = f"{ROOT}/{batch['batch_id']}/retry"
    assert client.post(retry_url, headers={"x-user": "2"}).status_code == 404
    retry = client.post(retry_url)
    assert retry.status_code == 202
    assert (retry.json()["processed"], retry.json()["total"]) == (0, 2)
    assert client.post(retry_url).status_code == 409
    assert worker.process_next()
    assert worker.process_next()
    complete = _wait_batch(client, batch["batch_id"])
    assert [item["fields"]["number"] for item in complete["items"]] == ["SB-432", "AFF-555"]
    assert not any(item["retryable"] for item in complete["items"])
    assert [item["file_id"] for item in complete["items"]] == [item["file_id"] for item in failed["items"]]


@pytest.mark.parametrize("intake", [False], indirect=True)
@pytest.mark.parametrize("bad_result", [
    {"fields": None}, {"type_key": []}, {"fields": {"number": object()}}, {"warnings": [object()]},
    {"fields": {"number": "bad\x00text"}}, {"fields": {"bad\x00key": "value"}},
    {"fields": {"number": "bad\ud800text"}}, {"fields": {"bad\udfffkey": "value"}},
    {"type_key": "bad\x00type"}, {"type_key": "bad\ud800type"},
    {"warnings": ["bad\x00warning"]}, {"warnings": ["bad\udfffwarning"]},
])
def test_malformed_recognition_cannot_poison_batch_completion(intake, bad_result):
    client, sessions, uploads = intake
    batch = _queue(client, (255, 0, 0), (0, 255, 0))
    results = iter([bad_result, {"type_key": "certificate:AFF", "fields": {"number": "OK"}, "pending": True}])
    worker = document_intake._RecognitionWorker(sessions, uploads, lambda *_: next(results))
    assert worker.process_next()
    assert worker.process_next()
    assert not worker.process_next()
    completed = _wait_batch(client, batch["batch_id"])
    assert completed["items"][0]["error"] == "invalid_scan"
    assert completed["items"][0]["fields"] == {}
    assert completed["items"][1]["fields"]["number"] == "OK"


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_preparation_database_failure_keeps_draft_for_retry(intake, monkeypatch):
    client, sessions, uploads = intake
    batch = _queue(client, (255, 0, 0))
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)

    def unavailable(_candidate):
        raise OperationalError("select", {}, RuntimeError("database unavailable"))

    with monkeypatch.context() as patch:
        patch.setattr(document_intake, "intake_catalog", unavailable)
        with pytest.raises(OperationalError):
            worker.process_next()
    with sessions() as db:
        row = db.scalars(select(DocumentIntakeFile)).one()
        assert row.result.get("pending") and row.content
    assert worker.process_next()
    assert _wait_batch(client, batch["batch_id"])["items"][0]["fields"]["number"] == "SB-432"


@pytest.mark.parametrize("intake", [False], indirect=True)
@pytest.mark.parametrize("failure", [DataError, OperationalError])
def test_result_persistence_distinguishes_poison_data_from_outage(intake, monkeypatch, failure):
    client, sessions, uploads = intake
    batch = _queue(client, (255, 0, 0), (0, 255, 0))
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)
    original = sessions.class_.commit
    commits = []

    def commit(db):
        commits.append(True)
        if len(commits) == 1:
            db.flush()
            raise failure("update", {}, RuntimeError("injected persistence failure"))
        return original(db)

    with monkeypatch.context() as patch:
        patch.setattr(sessions.class_, "commit", commit)
        if failure is OperationalError:
            with pytest.raises(OperationalError):
                worker.process_next()
        else:
            assert worker.process_next()
    with sessions() as db:
        row = db.scalars(select(DocumentIntakeFile).order_by(DocumentIntakeFile.position)).first()
        if failure is DataError:
            assert row.result["error"] == "recognition_failed"
            assert not row.result.get("pending") and row.content == _png((255, 0, 0))
        else:
            assert row.result.get("pending") and row.content
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)
    while worker.process_next():
        pass
    completed = _wait_batch(client, batch["batch_id"])
    assert completed["items"][1]["fields"]["number"] == "AFF-555"
    assert completed["items"][0].get("error") == ("recognition_failed" if failure is DataError else None)


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_discard_during_recognition_does_not_restore_draft(intake):
    client, sessions, uploads = intake
    batch = _queue(client, (255, 0, 0))

    def recognize(path, catalog):
        assert client.delete(f"{ROOT}/{batch['batch_id']}").status_code == 204
        return _recognize(path, catalog)

    worker = document_intake._RecognitionWorker(sessions, uploads, recognize)
    assert worker.process_next()
    assert not worker.process_next()
    with sessions() as db:
        assert not db.scalars(select(DocumentIntakeFile)).all()


def _save(client, batch, *documents, bulk=False):
    response = client.post(
        f"/candidates/1/document-intake/{batch['batch_id']}/save", json={"documents": documents, "bulk": bulk},
    )
    assert response.status_code == 200, response.text
    return response.json()["results"]


def _approval(items, kind="document:SB", action="create", **extra):
    return {"file_ids": [item["file_id"] for item in items], "type_key": kind,
            "fields": {"number": "SB-432", "issue_date": "2024-04-25"}, "action": action, **extra}


def test_runtime_switch_blocks_every_operation_without_deleting_drafts(intake):
    client, sessions, uploads = intake
    root = "/candidates/1/document-intake"
    marker = uploads / document_intake.SWITCH_FILE
    assert client.get(root + "/status", headers={"x-user": "3"}).status_code == 403
    assert client.get(root + "/status").json() == {"enabled": True}
    batch = _upload(client, (255, 0, 0))
    file = batch["items"][0]
    batch_path = f"{root}/{batch['batch_id']}"
    preview = f"{batch_path}/files/{file['file_id']}"

    marker.unlink()
    state = client.get(root + "/status")
    assert state.json() == {"enabled": False}
    assert state.headers["cache-control"] == "no-store"
    responses = [
        client.get(root),
        client.post(root, files=[("files", ("other.png", _png((255, 0, 0)), "image/png"))]),
        client.get(preview),
        client.delete(batch_path),
        client.post(batch_path + "/save", json={"documents": [_approval([file])]}),
    ]
    assert all(response.status_code == 404 and response.json()["detail"] == "intake_disabled" for response in responses)
    with sessions() as db:
        assert db.get(DocumentIntakeFile, file["file_id"]).content == _png((255, 0, 0))
        assert db.scalars(select(Attachment)).first() is None

    marker.touch()
    assert client.get(root + "/status").json() == {"enabled": True}
    assert client.get(preview).status_code == 200
    assert _save(client, batch, _approval([file]))[0]["status"] == "saved"
    marker.unlink()
    with sessions() as db:
        assert db.scalars(select(Attachment)).first() is not None


def test_draft_storage_limit_does_not_erase_existing_drafts(intake, monkeypatch):
    client, sessions, _ = intake
    batch = _upload(client, (255, 0, 0))
    monkeypatch.setattr(document_intake, "MAX_DRAFT_BYTES", len(_png((255, 0, 0))))
    response = client.post("/candidates/1/document-intake", files=[
        ("files", ("new.png", _png((255, 0, 0)), "image/png")),
    ])
    assert response.status_code == 409
    assert response.json()["detail"] == "draft_storage_limit"
    with sessions() as db:
        assert db.get(DocumentIntakeFile, batch["items"][0]["file_id"]).content


def test_private_preview_grouped_save_and_retry(intake):
    client, sessions, uploads = intake
    batch = _upload(client, (255, 0, 0), (254, 0, 0), (0, 255, 0))
    first, second, other = batch["items"]
    assert first["group_key"] == second["group_key"]
    assert not other.get("group_key")
    preview = f"/candidates/1/document-intake/{batch['batch_id']}/files/{first['file_id']}"
    assert client.get(preview).content == _png((255, 0, 0))
    assert client.get(preview).headers["cache-control"] == "no-store"
    assert client.get(preview, headers={"x-user": "2"}).status_code == 404
    assert client.get(preview.replace("/candidates/1/", "/candidates/2/")).status_code == 404
    assert client.get("/candidates/1/document-intake", headers={"x-user": "3"}).status_code == 403
    with sessions() as db:
        assert not db.scalars(select(Document)).all()
        assert not db.scalars(select(Attachment)).all()
    approved = _approval([second, first])
    assert _save(client, batch, approved)[0]["status"] == "saved"
    assert _save(client, batch, approved)[0]["status"] == "saved"
    assert client.get(preview).status_code == 404
    with sessions() as db:
        doc = db.scalars(select(Document)).one()
        assert doc.document_category == "SB"
        assert doc.document_number == "SB-432"
        from app.canonical_documents import CANONICAL_DOCUMENT_SPECS, find_document_for_spec
        sb = next(spec for spec in CANONICAL_DOCUMENT_SPECS if spec["code"] == "SB")
        assert find_document_for_spec([doc], sb) is doc
        attachments = db.scalars(select(Attachment).order_by(Attachment.attachment_id)).all()
        assert len(attachments) == 2
        assert [a.checksum for a in attachments] == [
            document_intake.sha256(_png((254, 0, 0))).hexdigest(),
            document_intake.sha256(_png((255, 0, 0))).hexdigest(),
        ]
        for attachment in attachments:
            assert attachment.description == f"document:{doc.document_id}"
            assert attachment.file_name.endswith(" SAILOR SB.pdf")
            assert Path(attachment.file_path).read_bytes().startswith(b"%PDF")
        assert db.get(DocumentIntakeFile, other["file_id"]).content
    assert len(list(uploads.glob("*.pdf"))) == 2


def test_existing_match_retains_unfilled_values_and_replaces_old_scan(intake):
    client, sessions, uploads = intake
    with sessions() as db:
        row = Document(candidate_id=1, document_type="Seaman's Book", document_category="SB",
                       document_number="SB 432", issuing_authority="Original Authority")
        db.add(row)
        db.flush()
        record_id = row.document_id
        old_path = uploads / "original.pdf"
        old_path.write_bytes(b"%PDF-original")
        db.add(Attachment(candidate_id=1, file_name="original.pdf", file_path=str(old_path),
                          source="document", description=f"document:{record_id}"))
        db.commit()
    batch = _upload(client, (255, 0, 0))
    existing = client.get("/candidates/1/document-intake").json()["existing"]
    assert existing[0]["fields"]["authority"] == "Original Authority"
    assert _save(client, batch, _approval(batch["items"]))[0]["error"] == "existing_duplicate"
    changes = _approval(batch["items"], action="update", existing_id=record_id, existing_version=existing[0]["version"],
                        fields={"number": "SB-432", "authority": "", "expiry_date": "2034-10-15"})
    assert _save(client, batch, changes)[0]["status"] == "saved"
    with sessions() as db:
        row = db.get(Document, record_id)
        assert row.issuing_authority == "Original Authority"
        assert row.date_of_expiry.isoformat() == "2034-10-15"
        [attachment] = db.scalars(select(Attachment)).all()
        assert Path(attachment.file_path).read_bytes().startswith(b"%PDF")
        assert attachment.file_path != str(old_path)
    assert not old_path.exists()


def test_intake_approval_rejects_stale_record_version(intake):
    client, sessions, _ = intake
    with sessions.begin() as db:
        row = Document(candidate_id=1, document_type="Seaman's Book", document_category="SB", document_number="SB 432")
        db.add(row)
        db.flush()
        record_id = row.document_id
    batch = _upload(client, (255, 0, 0))
    existing = client.get("/candidates/1/document-intake").json()["existing"][0]
    with sessions.begin() as db:
        db.get(Document, record_id).issuing_authority = "New authority from another manager"
    changes = _approval(batch["items"], action="update", existing_id=record_id, existing_version=existing["version"],
                        fields={"number": "SB-432", "authority": "Stale authority"})
    assert _save(client, batch, changes)[0]["error"] == "record_changed"
    with sessions() as db:
        assert db.get(Document, record_id).issuing_authority == "New authority from another manager"
        assert not db.get(DocumentIntakeFile, batch["items"][0]["file_id"]).saved_key


def test_replacement_can_return_to_previous_scan_and_keep_shared_file(intake):
    client, sessions, _ = intake
    initial = _upload(client, (255, 0, 0))
    assert _save(client, initial, _approval(initial["items"]))[0]["status"] == "saved"
    with sessions.begin() as db:
        first = db.scalar(select(Attachment))
        original_path = Path(first.file_path)
        shared = Attachment(candidate_id=2, file_name="shared.pdf", file_path=str(original_path),
                            source="document", description="document:999")
        db.add(shared)
        record_id = db.scalar(select(Document.document_id))
    for color in [(254, 0, 0), (255, 0, 0), (255, 0, 0)]:
        batch = _upload(client, color)
        existing = client.get(ROOT).json()["existing"][0]
        approval = _approval(batch["items"], action="update", existing_id=record_id,
                             existing_version=existing["version"])
        assert _save(client, batch, approval)[0]["status"] == "saved"
        assert _save(client, batch, approval)[0]["status"] == "saved"
        with sessions() as db:
            [current] = db.scalars(select(Attachment).where(Attachment.candidate_id == 1)).all()
            assert current.checksum == document_intake.sha256(_png(color)).hexdigest()
            assert Path(current.file_path).is_file()
            assert len(db.scalars(select(Document)).all()) == 1
            assert len(db.scalars(select(Attachment).where(Attachment.candidate_id == 2)).all()) == 1
        assert original_path.is_file()


@pytest.mark.parametrize("failure", ["conversion", "commit_before", "commit_after", "cleanup"])
def test_replacement_failure_keeps_a_usable_scan_and_supports_retry(intake, monkeypatch, failure):
    client, sessions, _ = intake
    initial = _upload(client, (255, 0, 0))
    assert _save(client, initial, _approval(initial["items"]))[0]["status"] == "saved"
    with sessions() as db:
        old_path = Path(db.scalar(select(Attachment)).file_path)
        record_id = db.scalar(select(Document.document_id))
    batch = _upload(client, (254, 0, 0))
    existing = client.get(ROOT).json()["existing"][0]
    approval = _approval(batch["items"], action="update", existing_id=record_id,
                         existing_version=existing["version"])
    original_commit = sessions.class_.commit
    original_unlink = Path.unlink

    def fail_conversion(*_):
        raise HTTPException(400, "invalid_scan")

    def fail_commit(db):
        if failure == "commit_after":
            original_commit(db)
        raise OperationalError("commit", {}, RuntimeError("injected replacement failure"))

    def fail_old_cleanup(path, *args, **kwargs):
        if path == old_path:
            raise OSError("injected cleanup failure")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        if failure == "conversion":
            patch.setattr(document_intake, "prepare_attachment_bytes", fail_conversion)
        elif failure == "cleanup":
            patch.setattr(Path, "unlink", fail_old_cleanup)
        else:
            patch.setattr(sessions.class_, "commit", fail_commit)
        result = _save(client, batch, approval)[0]
    assert old_path.is_file()
    with sessions() as db:
        [current] = db.scalars(select(Attachment)).all()
        assert Path(current.file_path).is_file()
        committed = failure in {"commit_after", "cleanup"}
        assert (current.file_path != str(old_path)) == committed
        draft = db.get(DocumentIntakeFile, batch["items"][0]["file_id"])
        assert (draft.content is None) == committed
    if failure == "cleanup":
        assert result["status"] == "saved"
    else:
        assert result["error"] == ("invalid_scan" if failure == "conversion" else "save_outcome_unknown")
    assert _save(client, batch, approval)[0]["status"] == "saved"
    with sessions() as db:
        [current] = db.scalars(select(Attachment)).all()
        assert current.checksum == document_intake.sha256(_png((254, 0, 0))).hexdigest()
        assert Path(current.file_path).is_file()


def test_partial_bulk_and_individual_confirmation(intake):
    client, sessions, _ = intake
    batch = _upload(client, (255, 0, 1), (0, 255, 0), (0, 0, 0))
    mismatch, good, unknown = batch["items"]
    assert "holder_mismatch" in mismatch["warnings"]
    mismatch_approval = _approval([mismatch], confirm_holder=True, fields={"holder_name": "Demo Sailor"})
    correct = _approval([good], kind="certificate:AFF", fields={"number": "AFF-555"})
    results = _save(client, batch, mismatch_approval, correct)
    assert [item["status"] for item in results] == ["error", "saved"]
    assert results[0]["error"] == "holder_mismatch"
    assert _save(client, batch, mismatch_approval, bulk=True)[0]["error"] == "holder_mismatch"
    assert _save(client, batch, mismatch_approval)[0]["status"] == "saved"
    assert unknown["type_key"] is None
    assert _save(client, batch, _approval([unknown], kind="visa:Visa USA"))[0]["status"] == "saved"
    with sessions() as db:
        assert db.scalars(select(Certificate)).one().certificate_name_raw == "AFF"
        assert {row.document_category for row in db.scalars(select(Document))} == {"SB", "Visa USA"}


def test_file_errors_and_discard(intake):
    client, sessions, _ = intake
    response = client.post("/candidates/1/document-intake", files=[
        ("files", ("unrelated.txt", b"text", "text/plain")),
        ("files", ("broken.png", b"broken", "image/png")),
        ("files", ("accepted.png", _png((255, 0, 0)), "image/png")),
    ])
    assert response.status_code == 202
    batch = _wait_batch(client, response.json()["batch_id"])
    assert [item.get("error") for item in batch["items"]] == ["unsupported_file", "invalid_scan", None]
    route = f"/candidates/1/document-intake/{batch['batch_id']}"
    client.delete(route, headers={"x-user": "2"})
    assert len(client.get("/candidates/1/document-intake").json()["batches"]) == 1
    assert client.delete(route).status_code == 204
    with sessions() as db:
        assert not db.scalars(select(DocumentIntakeFile)).all()
        assert not db.scalars(select(Attachment)).all()


def test_failed_conversion_rolls_back_document_and_already_written_scan(intake, monkeypatch):
    client, sessions, uploads = intake
    batch = _upload(client, (255, 0, 0), (254, 0, 0))
    original = document_intake.prepare_attachment_bytes
    broken = _png((254, 0, 0))

    def convert(suffix, content):
        if content == broken:
            raise HTTPException(400, "invalid_scan")
        return original(suffix, content)

    with monkeypatch.context() as patch:
        patch.setattr(document_intake, "prepare_attachment_bytes", convert)
        assert _save(client, batch, _approval(batch["items"]))[0]["error"] == "invalid_scan"
    assert [file.name for file in uploads.iterdir()] == [document_intake.SWITCH_FILE]
    with sessions() as db:
        assert not db.scalars(select(Document)).all()
        assert not db.scalars(select(Attachment)).all()
        assert all(row.saved_key is None and row.content for row in db.scalars(select(DocumentIntakeFile)))
    assert _save(client, batch, _approval(batch["items"]))[0]["status"] == "saved"


def test_pdf_preview_is_raster_and_paginated(intake):
    client, _, _ = intake
    with BytesIO() as stream, Image.new("RGB", (70, 90), "white") as first, Image.new("RGB", (90, 70), "blue") as second:
        first.save(stream, format="PDF", save_all=True, append_images=[second])
        response = client.post("/candidates/1/document-intake", files=[
            ("files", ("two-pages.pdf", stream.getvalue(), "application/pdf"))
        ])
    assert response.status_code == 202
    batch = _wait_batch(client, response.json()["batch_id"])
    item = batch["items"][0]
    assert item["page_count"] == 2
    preview = f"/candidates/1/document-intake/{batch['batch_id']}/files/{item['file_id']}"
    first, second = (client.get(preview, params={"page": page}) for page in (1, 2))
    assert first.headers["content-type"] == second.headers["content-type"] == "image/png"
    assert first.content != second.content
    assert client.get(preview, params={"page": 3}).status_code == 404


def test_can_add_renewal_without_changing_previous_number_and_scans(intake):
    client, sessions, _ = intake
    initial = _upload(client, (255, 0, 0))
    first = _approval(initial["items"], kind="document:YF", fields={"number": "YF-010"})
    assert _save(client, initial, first)[0]["status"] == "saved"
    renewal = _upload(client, (254, 0, 0))
    second = _approval(renewal["items"], kind="document:YF", fields={
        "number": "YF-011", "issue_date": "2028-08-01", "expiry_date": "2024-08-01",
    })
    assert _save(client, renewal, second)[0]["error"] == "expiry_before_issue"
    second["fields"]["expiry_date"] = "2038-08-01"
    assert _save(client, renewal, second)[0]["status"] == "saved"
    with sessions() as db:
        rows = db.scalars(select(Document).order_by(Document.document_id)).all()
        assert [row.document_number for row in rows] == ["YF-010", "YF-011"]
        assert {row.description for row in db.scalars(select(Attachment))} == {
            f"document:{doc.document_id}" for doc in rows
        }
