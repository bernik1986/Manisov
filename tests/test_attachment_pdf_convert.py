"""Attachment upload: raster images stored as PDF; PDF unchanged."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.attachment_convert import image_bytes_to_pdf, prepare_attachment_bytes
from app import main as main_module
from app.main import app, get_db_session
from models.db import Base
from models.schema import Candidate, Document, Role, User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def _tiny_png_bytes() -> bytes:
    img = Image.new("RGB", (4, 4), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _tiny_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (4, 4), color=(40, 50, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_image_bytes_to_pdf_produces_pdf_header():
    pdf = image_bytes_to_pdf(_tiny_png_bytes())
    assert pdf.startswith(b"%PDF")


def test_prepare_attachment_bytes_png_becomes_pdf():
    png = _tiny_png_bytes()
    stored, suffix, media = prepare_attachment_bytes(".png", png)
    assert suffix == ".pdf"
    assert media == "application/pdf"
    assert stored.startswith(b"%PDF")
    assert len(stored) > len(png) // 2


def test_prepare_attachment_bytes_jpeg_becomes_pdf():
    stored, suffix, _ = prepare_attachment_bytes(".jpeg", _tiny_jpeg_bytes())
    assert suffix == ".pdf"
    assert stored.startswith(b"%PDF")


def test_prepare_attachment_bytes_pdf_unchanged():
    original = b"%PDF-1.4 minimal"
    stored, suffix, media = prepare_attachment_bytes(".pdf", original)
    assert stored == original
    assert suffix == ".pdf"
    assert media == "application/pdf"


def test_prepare_attachment_bytes_rejects_invalid_pdf():
    with pytest.raises(HTTPException) as exc_info:
        prepare_attachment_bytes(".pdf", b"not a pdf")
    assert exc_info.value.status_code == 400


@pytest.fixture
def upload_client(tmp_path):
    main_module.UPLOADS_DIR = tmp_path / "uploads"
    main_module.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    engine = __import__("sqlalchemy").create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app) as test_client:
            yield test_client, TestingSessionLocal, tmp_path
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_upload_png_stored_as_pdf_on_disk(upload_client):
    client, Session, tmp_path = upload_client
    db_session = Session()
    admin_role = Role(name="admin")
    db_session.add(admin_role)
    db_session.flush()
    db_session.add(
        User(
            username="admin_convert",
            password_hash=pwd_context.hash("admin123"),
            role_id=admin_role.role_id,
            is_active=True,
        )
    )
    candidate = Candidate(surname="Koval", first_name="Jan", current_rank="AB")
    db_session.add(candidate)
    db_session.flush()
    doc = Document(candidate_id=candidate.candidate_id, document_type="Passport")
    db_session.add(doc)
    db_session.commit()
    cid = candidate.candidate_id
    did = doc.document_id
    db_session.close()

    login = client.post("/auth/login", json={"username": "admin_convert", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.post(
        f"/candidates/{cid}/attachments",
        headers=headers,
        files={"file": ("phone_scan.png", _tiny_png_bytes(), "image/png")},
        data={"attachment_type": "document", "relation_id": str(did)},
    )
    assert response.status_code == 200
    payload = response.json()["attachment"]
    assert payload["file_name"] == "AB Koval Passport.pdf"
    assert payload["file_type"] == "application/pdf"

    stored_path = __import__("pathlib").Path(payload["file_path"])
    assert stored_path.suffix.lower() == ".pdf"
    assert stored_path.read_bytes().startswith(b"%PDF")

    download = client.get(f"/attachments/{payload['attachment_id']}/download", headers=headers)
    assert download.status_code == 200
    assert download.headers.get("content-type", "").startswith("application/pdf")
    assert download.content.startswith(b"%PDF")
