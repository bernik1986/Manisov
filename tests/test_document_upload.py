"""Public candidate upload through the existing CRM document intake workflow."""

import json
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
import pypdfium2 as pdfium
import pytest
from sqlalchemy import select

from app import document_intake
from app.attachment_naming import attachment_download_filename
from models.schema import Attachment, Candidate, Certificate, Document, DocumentIntakeFile, DocumentUploadSubmission, FlagDocument
from tests.test_document_intake import ROOT, _png, _recognize, _wait_batch, intake  # noqa: F401


PUBLIC = "/public/document-upload"
NOTIFICATIONS = "/document-upload/notifications"


@pytest.fixture(autouse=True)
def enable_public_upload(intake):
    _, _, uploads = intake
    (uploads / document_intake.PUBLIC_SWITCH_FILE).touch()


def _link(client, root=ROOT):
    response = client.post(f"{root}/upload-link")
    assert response.status_code == 200, response.text
    return {"X-Document-Upload-Token": response.json()["token"]}


def _submit(client, headers, files, groups=(), request_id=None):
    return client.post(
        PUBLIC, headers=headers, files=files,
        data={"manifest": json.dumps({"request_id": request_id or uuid4().hex, "documents": list(groups)})},
    )


def _file(field, name, color):
    return field, (name, _png(color), "image/png")


def _rows(db, batch_id):
    return db.scalars(select(DocumentIntakeFile).where(
        DocumentIntakeFile.batch_id == batch_id,
    ).order_by(DocumentIntakeFile.position)).all()


@pytest.mark.parametrize("limit,reason", [
    ("MAX_PENDING_SUBMISSIONS", "submission_limit"),
    ("MAX_PUBLIC_DRAFT_BYTES", "draft_storage_limit"),
])
def test_exhausted_quota_skips_photo_preparation_and_allows_receipt_replay(intake, monkeypatch, limit, reason):
    client, _, _ = intake
    headers = _link(client)
    files = [_file("pages", "one.png", (255, 0, 0))]
    groups = [{"type_key": "document:SB", "page_count": 1}]
    request_id = uuid4().hex
    first = _submit(client, headers, files, groups, request_id)
    assert first.status_code == 201
    monkeypatch.setattr(document_intake, limit, 0)
    monkeypatch.setattr(document_intake, "prepare_submission_files", lambda *a: pytest.fail("converted despite quota"))
    replay = _submit(client, headers, files, groups, request_id)
    assert replay.status_code == 200 and replay.json() == first.json()
    rejected = _submit(client, headers, files, groups)
    assert rejected.status_code == 409 and rejected.json()["detail"] == reason


@pytest.mark.parametrize("name", ["application.docx", "profile.xlsx"])
def test_personal_link_rejects_questionnaire_files(intake, name):
    client, sessions, _ = intake
    response = _submit(client, _link(client), [("files", (name, b"PK", "application/octet-stream"))])
    assert response.status_code == 400 and response.json()["detail"] == "unsupported_file"
    with sessions() as db:
        assert not db.scalar(select(DocumentUploadSubmission))


@pytest.mark.parametrize("type_key, model, identity, relation, number_field", [
    ("document:SB", Document, {"document_type": "Seaman's Book", "document_category": "SB"}, "document", "document_number"),
    ("certificate:AFF", Certificate, {"certificate_type": "Advanced Fire Fighting", "certificate_group": "Certificate", "certificate_name_raw": "AFF", "certificate_code": "AFF"}, "certificate", "certificate_number"),
    ("flag_document:endorsement", FlagDocument, {"flag_document_type": "Endorsement", "flag_country": "Panama"}, "flag_document", "doc_number"),
])
def test_public_upload_replaces_existing_scan_and_retries_without_duplicates(
    intake, type_key, model, identity, relation, number_field,
):
    client, sessions, uploads = intake
    old_path = uploads / "old.pdf"
    old_path.write_bytes(b"%PDF-old-scan")
    unrelated_path = uploads / "unrelated.pdf"
    unrelated_path.write_bytes(b"%PDF-unrelated-scan")
    with sessions.begin() as db:
        record = model(candidate_id=1, **identity, **{number_field: "REPLACE-123"})
        db.add(record)
        db.flush()
        record_id = getattr(record, f"{relation}_id")
        description = f"{relation}:{record_id}"
        db.add_all([
            Attachment(candidate_id=1, file_name="old.pdf", file_path=str(old_path),
                       source=relation, description=description),
            Attachment(candidate_id=2, file_name="unrelated.pdf", file_path=str(unrelated_path),
                       source=relation, description=description),
        ])
    sent = _submit(client, _link(client), [
        _file("pages", "first.png", (255, 0, 0)),
        _file("pages", "second.png", (0, 0, 255)),
    ], [{"type_key": type_key, "page_count": 2}])
    assert sent.status_code == 201, sent.text
    batch_id = sent.json()["submission_id"]
    assert client.post(f"{ROOT}/submissions/{batch_id}/recognize").status_code == 202
    batch = _wait_batch(client, batch_id)
    file_id = batch["items"][0]["file_id"]
    existing = next(item for item in client.get(ROOT).json()["existing"]
                    if item["type_key"] == type_key and item["id"] == record_id)
    fields = {"number": "REPLACE-123", "expiry_date": "2035-12-31"}
    if relation == "flag_document":
        fields["country"] = "Panama"
    body = {"documents": [{
        "file_ids": [file_id], "type_key": type_key, "fields": fields,
        "action": "update", "existing_id": record_id, "existing_version": existing["version"],
        "confirm_type_mismatch": True,
    }], "bulk": False, "finish_submission": True}
    response = client.post(f"{ROOT}/{batch_id}/save", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "saved", response.text
    assert response.json()["submission_finished"] is True
    assert client.post(f"{ROOT}/{batch_id}/save", json=body).json() == response.json()
    with sessions() as db:
        assert len(db.scalars(select(model)).all()) == 1
        record = db.get(model, record_id)
        expiry = record.expiry_date if relation == "certificate" else record.date_of_expiry
        assert expiry.isoformat() == "2035-12-31"
        [attachment] = db.scalars(select(Attachment).where(Attachment.candidate_id == 1)).all()
        assert attachment.description == description and attachment.source == relation
        assert attachment.file_name == attachment_download_filename(db, db.get(Candidate, 1), attachment)
        content = Path(attachment.file_path).read_bytes()
        with pdfium.PdfDocument(content) as pdf:
            assert len(pdf) == 2
        for page_number, channel in [(1, 0), (2, 2)]:
            with Image.open(BytesIO(document_intake.render_preview_page(content, page_number))) as page:
                pixel = page.convert("RGB").getpixel((page.width // 2, page.height // 2))
                assert pixel[channel] > 235 and sum(pixel[:3]) < 275
        assert db.get(DocumentIntakeFile, file_id).content is None
        assert db.get(DocumentUploadSubmission, batch_id).status == "closed"
        assert len(db.scalars(select(Attachment).where(Attachment.candidate_id == 2)).all()) == 1
    assert not old_path.exists()
    assert unrelated_path.read_bytes() == b"%PDF-unrelated-scan"
    assert client.get(NOTIFICATIONS).json()["items"] == []


def test_received_upload_uses_same_editable_review_and_removes_temporary_files(intake):
    client, sessions, _ = intake
    headers = _link(client)
    catalog = client.get(PUBLIC, headers=headers)
    assert catalog.headers["Cache-Control"] == "no-store"
    assert set(catalog.json()) == {"catalog", "limits"}
    assert "document:SB" in {item["key"] for item in catalog.json()["catalog"]}
    with Image.new("RGB", (30, 20), "red") as image, BytesIO() as output:
        exif = Image.Exif()
        exif[274] = 6  # Camera orientation: 90 degrees clockwise.
        image.save(output, format="JPEG", exif=exif)
        camera_page = ("pages", ("zzz.jpg", output.getvalue(), "image/jpeg"))
    files = [
        _file("files", "folder/standalone.png", (0, 255, 0)),
        camera_page,
        _file("pages", "aaa.png", (0, 0, 255)),
    ]
    groups = [{"type_key": "document:SB", "page_count": 2}]
    request_id = uuid4().hex
    sent = _submit(client, headers, files, groups, request_id)
    assert sent.status_code == 201, sent.text
    received = sent.json()
    assert received["file_count"] == 2
    batch_id = received["submission_id"]
    duplicate = _submit(client, headers, files, groups, request_id)
    assert duplicate.status_code == 200 and duplicate.json() == received

    [notification] = client.get(NOTIFICATIONS).json()["items"]
    assert (notification["candidate_id"], notification["submission_id"], notification["status"]) == (1, batch_id, "received")
    assert client.get(ROOT).json()["batches"] == []
    inbox = client.get(f"{ROOT}/submissions").json()
    assert inbox["upload_enabled"] is True and inbox["items"][0]["file_count"] == 2
    with sessions() as db:
        loose, joined = _rows(db, batch_id)
        assert loose.name == "standalone.png"
        assert joined.content_type == "application/pdf" and joined.content.startswith(b"%PDF-")
        assert not any(row.result.get("pending") for row in (loose, joined))
        assert db.scalar(select(Document)) is None and db.scalar(select(Attachment)) is None
        file_id = joined.file_id
    assert client.get(f"{ROOT}/{batch_id}/files/{file_id}").status_code == 404

    action = f"{ROOT}/submissions/{batch_id}/recognize"
    assert client.post(action.replace("/1/", "/2/")).status_code == 404
    assert client.post(action, headers={"x-user": "3"}).status_code == 403
    assert client.post(action).json()["external"] is True
    batch = _wait_batch(client, batch_id)
    assert batch["total"] == 2
    review = batch["items"][1]
    assert review["type_key"] == "document:SB"
    assert "type_hint_mismatch" in review["warnings"]
    for page, channel in [(1, 0), (2, 2)]:
        rendered = client.get(f"{ROOT}/{batch_id}/files/{file_id}", params={"page": page})
        assert rendered.status_code == 200
        with Image.open(BytesIO(rendered.content)) as image:
            assert (image.height > image.width) == (page == 1)
            color = image.convert("RGB").getpixel((image.width // 2, image.height // 2))
            assert color[channel] > 235 and sum(color) < 275

    approval = {"file_ids": [file_id], "type_key": "document:SB",
                "fields": {"number": "EDITED-123"}, "action": "create"}
    body = {"documents": [approval], "bulk": True, "finish_submission": True}
    save_url = f"{ROOT}/{batch_id}/save"
    blocked = client.post(save_url, json=body)
    assert blocked.json()["results"][0]["error"] == "type_hint_mismatch"
    approval["confirm_type_mismatch"] = True
    assert client.post(save_url, json=body).json()["results"][0]["error"] == "type_hint_mismatch"
    body["bulk"] = False
    response = client.post(save_url, json=body)
    assert response.status_code == 200 and response.json()["submission_finished"] is True, response.text
    assert client.post(save_url, json=body).json() == response.json()
    assert client.get(NOTIFICATIONS).json()["items"] == []
    assert client.get(ROOT).json()["batches"] == []
    with sessions() as db:
        record = db.scalar(select(Document))
        assert record.candidate_id == 1 and record.document_number == "EDITED-123"
        [attachment] = db.scalars(select(Attachment)).all()
        assert attachment.file_name == attachment_download_filename(db, db.get(Candidate, 1), attachment)
        assert attachment.file_name.endswith(" SAILOR SB.pdf")
        assert Path(attachment.file_path).read_bytes().startswith(b"%PDF-")
        [saved] = _rows(db, batch_id)
        assert saved.content is None and saved.content_type is None
        assert db.get(DocumentUploadSubmission, batch_id).closed_at is not None


def test_link_scope_validation_revocation_and_disabled_switch(intake):
    client, sessions, uploads = intake
    headers = _link(client)
    assert headers == _link(client)
    assert headers != _link(client, ROOT.replace("/1/", "/2/"))
    assert client.get(PUBLIC).status_code == 404
    assert client.post(f"{ROOT}/upload-link", headers={"x-user": "3"}).status_code == 403
    assert client.get(NOTIFICATIONS, headers={"x-user": "3"}).status_code == 403

    fake = [("files", ("fake.pdf", b"<script></script>", "application/pdf"))]
    assert _submit(client, headers, fake).json()["detail"] == "invalid_scan"
    valid = [_file("files", "valid.png", (0, 255, 0))]
    mismatched = [{"type_key": "document:SB", "page_count": 1}]
    assert _submit(client, headers, valid, mismatched).json()["detail"] == "invalid_manifest"
    bad_type = [{"type_key": "document:missing", "page_count": 1}]
    assert _submit(client, headers, [_file("pages", "image.png", "white")], bad_type).json()["detail"] == "type_required"
    with Image.new("RGB", (32, 32), "red") as first, Image.new("RGB", (32, 32), "blue") as second, BytesIO() as buf:
        first.save(buf, format="PNG", save_all=True, append_images=[second], duration=100)
        animated = [("pages", ("animated.png", buf.getvalue(), "image/png"))]
    assert _submit(client, headers, animated, mismatched).json()["detail"] == "invalid_scan"
    assert client.get(f"{ROOT}/submissions").json()["items"] == []

    sent = _submit(client, headers, valid)
    assert sent.status_code == 201, sent.text
    batch = sent.json()["submission_id"]
    assert client.delete(f"{ROOT}/upload-link").status_code == 204
    assert client.get(PUBLIC, headers=headers).status_code == 404
    assert _submit(client, headers, valid).status_code == 404
    new_headers = _link(client)
    assert headers != new_headers
    assert client.delete(f"{ROOT}/submissions/{batch}").status_code == 204
    with sessions() as db:
        assert not _rows(db, batch)
    (uploads / document_intake.SWITCH_FILE).unlink()
    assert client.get(PUBLIC, headers=new_headers).status_code == 404
    assert client.get(NOTIFICATIONS).json() == {"enabled": False, "items": []}


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_external_bytes_survive_waiting_and_ocr_failure_until_review(intake, monkeypatch):
    client, sessions, uploads = intake
    response = _submit(client, _link(client), [_file("pages", "page.png", "red")],
                       [{"type_key": "document:SB", "page_count": 1}])
    assert response.status_code == 201, response.text
    batch_id = response.json()["submission_id"]
    worker = document_intake._RecognitionWorker(sessions, uploads, _recognize)
    with sessions.begin() as db:
        [row] = _rows(db, batch_id)
        row.created_at -= timedelta(days=8)
        content = row.content
    assert not worker.process_next()
    assert client.post(f"{ROOT}/submissions/{batch_id}/recognize").status_code == 202

    def unavailable(**_kwargs):
        raise OSError("synthetic temporary storage outage")

    with monkeypatch.context() as patch:
        patch.setattr(document_intake, "TemporaryDirectory", unavailable)
        assert worker.process_next()
    with sessions() as db:
        [row] = _rows(db, batch_id)
        assert row.content == content and row.result["type_hint"] == "document:SB"
    failed = _wait_batch(client, batch_id)["items"][0]
    assert failed["retryable"] and failed["error"] == "recognition_failed"
    assert client.post(f"{ROOT}/{batch_id}/retry").status_code == 202
    assert worker.process_next()
    reviewed = _wait_batch(client, batch_id)["items"][0]
    assert reviewed["file_id"] == failed["file_id"] and reviewed["type_key"] == "document:SB"
    assert client.delete(f"{ROOT}/{batch_id}").status_code == 204
    with sessions() as db:
        assert not _rows(db, batch_id)


def test_public_pause_keeps_received_files_available_for_ocr(intake):
    client, _, uploads = intake
    token = _link(client)
    files = [_file("files", "scan.png", "red")]
    sent = _submit(client, token, files)
    assert sent.status_code == 201
    batch_id = sent.json()["submission_id"]

    marker = uploads / document_intake.PUBLIC_SWITCH_FILE
    marker.unlink()
    assert client.get(f"{ROOT}/status").json()["enabled"] is True
    assert client.get(PUBLIC, headers=token).status_code == 404
    assert _submit(client, token, files).status_code == 404
    assert client.post(f"{ROOT}/upload-link").status_code == 404
    inbox = client.get(f"{ROOT}/submissions").json()
    assert not inbox["upload_enabled"]
    assert [item["submission_id"] for item in inbox["items"]] == [batch_id]
    assert client.get(NOTIFICATIONS).json()["enabled"]
    assert client.post(f"{ROOT}/submissions/{batch_id}/recognize").status_code == 202
    assert _wait_batch(client, batch_id)["items"][0]["type_key"] == "document:SB"
    assert client.delete(f"{ROOT}/{batch_id}").status_code == 204
    assert client.get(NOTIFICATIONS).json() == {"enabled": False, "items": []}
    marker.touch()
    assert _link(client) == token


@pytest.mark.parametrize("intake", [False], indirect=True)
def test_public_byte_quotas_reserve_space_for_manager_uploads(intake, monkeypatch):
    client, sessions, _ = intake
    upload = _file("files", "scan.png", "red")
    size = len(upload[1][1])
    monkeypatch.setattr(document_intake, "MAX_CANDIDATE_PUBLIC_DRAFT_BYTES", size)
    monkeypatch.setattr(document_intake, "MAX_PUBLIC_DRAFT_BYTES", 2 * size)
    monkeypatch.setattr(document_intake, "MAX_DRAFT_BYTES", 3 * size)
    with sessions.begin() as db:
        db.add(Candidate(candidate_id=3, surname="Third"))
    token = _link(client)
    request_id = uuid4().hex
    first = _submit(client, token, [upload], request_id=request_id)
    assert first.status_code == 201
    assert _submit(client, token, [upload], request_id=request_id).status_code == 200
    rejected = _submit(client, token, [upload])
    assert rejected.status_code == 409 and rejected.json()["detail"] == "submission_limit"
    assert client.delete(f"{ROOT}/upload-link").status_code == 204
    assert _submit(client, _link(client), [upload]).json()["detail"] == "submission_limit"
    second = _link(client, ROOT.replace("/1/", "/2/"))
    assert _submit(client, second, [upload]).status_code == 201
    third = _link(client, ROOT.replace("/1/", "/3/"))
    full = _submit(client, third, [upload])
    assert full.status_code == 409 and full.json()["detail"] == "draft_storage_limit"
    assert client.post(ROOT, files=[upload]).status_code == 202
    assert client.delete(f"{ROOT}/submissions/{first.json()['submission_id']}").status_code == 204
    assert _submit(client, third, [upload]).status_code == 201


def test_public_parser_rejects_an_oversized_part_header(intake):
    client, _, _ = intake
    headers = {**_link(client), "Content-Type": "multipart/form-data; boundary=regression"}
    body = (b'--regression\r\nContent-Disposition: form-data; name="manifest"\r\nX-Oversized: '
            + b"x" * (64 * 1024) + b"\r\n\r\n{}\r\n--regression--\r\n")
    response = client.post(PUBLIC, headers=headers, content=body)
    assert response.status_code == 400 and response.json()["detail"] == "invalid_manifest"
    assert client.get(f"{ROOT}/submissions").json()["items"] == []
