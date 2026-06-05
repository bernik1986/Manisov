from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app, get_db_session
from models.db import Base
from models.schema import Attachment, Candidate, Document, Role, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture()
def client_with_attachment(tmp_path: Path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    scan_path = uploads / "scan.pdf"
    scan_path.write_bytes(b"%PDF-1.4 e2e")

    def override_get_db_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestingSessionLocal() as session:
        role = Role(name="admin")
        session.add(role)
        session.flush()
        session.add(
            User(
                username="dl_admin",
                password_hash=pwd_context.hash("admin123"),
                role_id=role.role_id,
                is_active=True,
            )
        )
        candidate = Candidate(surname="Test", first_name="Dl")
        session.add(candidate)
        session.flush()
        doc = Document(candidate_id=candidate.candidate_id, document_type="Passport")
        session.add(doc)
        session.flush()
        att = Attachment(
            candidate_id=candidate.candidate_id,
            file_name="scan.pdf",
            file_path=str(scan_path),
            file_type="application/pdf",
            source="document",
            description=f"document:{doc.document_id}",
        )
        session.add(att)
        session.commit()
        attach_id = att.attachment_id
        candidate_id = candidate.candidate_id

    with TestClient(app) as test_client:
        yield test_client, attach_id, candidate_id

    app.dependency_overrides.clear()


def test_attachment_download_requires_auth(client_with_attachment) -> None:
    client, attach_id, _ = client_with_attachment
    response = client.get(f"/attachments/{attach_id}/download")
    assert response.status_code == 401


def test_attachment_download_with_token_returns_file(client_with_attachment) -> None:
    client, attach_id, _ = client_with_attachment
    login = client.post("/auth/login", json={"username": "dl_admin", "password": "admin123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    response = client.get(
        f"/attachments/{attach_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert b"PDF" in response.content or len(response.content) > 4
