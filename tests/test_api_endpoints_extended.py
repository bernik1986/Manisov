from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.main as main_module
from app.main import ISSUE_EXPIRY_ORDER_ERROR_MSG, _with_expiry_flags, app, get_db_session, pwd_context
from models.db import Base
from tests.canonical_test_helpers import find_certificate, find_document
from models.schema import (
    Application,
    Candidate,
    Certificate,
    Document,
    FlagDocument,
    FamilyContact,
    Role,
    TemplateFolder,
    User,
)


@pytest.fixture
def testing_session_local():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_local


@pytest.fixture
def db_session(testing_session_local):
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(testing_session_local):
    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth_seed(db_session):
    admin_role = Role(name="admin", description="Admin")
    recruiter_role = Role(name="recruiter", description="Recruiter")
    db_session.add_all([admin_role, recruiter_role])
    db_session.flush()

    admin = User(
        username="admin_test",
        password_hash=pwd_context.hash("admin123"),
        full_name="Admin Test",
        role_id=admin_role.role_id,
        is_active=True,
    )
    recruiter = User(
        username="recruiter_test",
        password_hash=pwd_context.hash("recruit123"),
        full_name="Recruiter Test",
        role_id=recruiter_role.role_id,
        is_active=True,
    )
    db_session.add_all([admin, recruiter])
    db_session.commit()


def _auth_header(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_endpoint_accepts_file_for_authorized_user(
    client: TestClient,
    auth_seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyParser:
        def parse(self, _file_path: Path) -> dict[str, str]:
            return {"status": "ok"}

    monkeypatch.setattr(main_module, "_get_parser", lambda _path: DummyParser())
    monkeypatch.setattr(main_module, "_save_parsed_data", lambda *_args, **_kwargs: 42)

    headers = _auth_header(client, "admin_test", "admin123")
    upload_response = client.post(
        "/upload",
        files={"file": ("candidate.pdf", b"dummy-file-content", "application/pdf")},
        headers=headers,
    )

    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert payload["candidate_id"] == 42
    assert payload["result"] == {"status": "ok"}


def test_templates_manager_upload_accepts_docx_with_long_content_type(
    client: TestClient,
    auth_seed,
    db_session,
) -> None:
    root = TemplateFolder(name="Templates", parent_id=None)
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)

    headers = _auth_header(client, "admin_test", "admin123")
    upload_response = client.post(
        "/templates-manager/files",
        data={"folder_id": str(root.folder_id)},
        files={
            "file": (
                "sample.DOCX",
                b"dummy-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=headers,
    )

    assert upload_response.status_code == 200
    payload = upload_response.json()["file"]
    assert payload["file_name"] == "sample.DOCX"
    assert len(payload["file_type"] or "") <= 50


def test_templates_manager_upload_normalizes_path_like_filename(
    client: TestClient,
    auth_seed,
    db_session,
) -> None:
    root = TemplateFolder(name="Templates", parent_id=None)
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)

    headers = _auth_header(client, "admin_test", "admin123")
    upload_response = client.post(
        "/templates-manager/files",
        data={"folder_id": str(root.folder_id)},
        files={
            "file": (
                "CENTURY COE/MARINICKI/3O COE Template.docx",
                b"dummy-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=headers,
    )

    assert upload_response.status_code == 200
    payload = upload_response.json()["file"]
    assert payload["file_name"] == "3O COE Template.docx"


def test_templates_manager_upload_rejects_when_oversized(
    client: TestClient,
    auth_seed,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = TemplateFolder(name="Templates", parent_id=None)
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)

    monkeypatch.setattr(main_module, "MAX_TEMPLATE_MANAGER_UPLOAD_BYTES", 100)

    headers = _auth_header(client, "admin_test", "admin123")
    upload_response = client.post(
        "/templates-manager/files",
        data={"folder_id": str(root.folder_id)},
        files={"file": ("sample.docx", b"y" * 200, "application/octet-stream")},
        headers=headers,
    )

    assert upload_response.status_code == 413
    assert "лимит" in upload_response.json()["detail"]


def test_templates_manager_upload_rejects_invalid_extension(
    client: TestClient,
    auth_seed,
    db_session,
) -> None:
    root = TemplateFolder(name="Templates", parent_id=None)
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)

    headers = _auth_header(client, "admin_test", "admin123")
    upload_response = client.post(
        "/templates-manager/files",
        data={"folder_id": str(root.folder_id)},
        files={"file": ("bad.exe", b"MZ", "application/octet-stream")},
        headers=headers,
    )

    assert upload_response.status_code == 400
    assert upload_response.json()["detail"] == main_module.INVALID_TEMPLATE_FILE_TYPE_MESSAGE


def test_templates_manager_rename_normalizes_path_like_filename(
    client: TestClient,
    auth_seed,
    db_session,
) -> None:
    root = TemplateFolder(name="Templates", parent_id=None)
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)

    headers = _auth_header(client, "admin_test", "admin123")
    upload_response = client.post(
        "/templates-manager/files",
        data={"folder_id": str(root.folder_id)},
        files={"file": ("source.docx", b"dummy-docx", "application/octet-stream")},
        headers=headers,
    )
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file"]["template_file_id"]

    rename_response = client.put(
        f"/templates-manager/files/{file_id}",
        json={"file_name": "folder\\nested\\renamed.docx"},
        headers=headers,
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["file"]["file_name"] == "renamed.docx"


def test_get_candidate_returns_expiry_flags(db_session, client: TestClient, auth_seed) -> None:
    candidate = Candidate(surname="Flagged", first_name="User")
    db_session.add(candidate)
    db_session.flush()

    db_session.add(
        Document(
            candidate_id=candidate.candidate_id,
            document_type="Passport",
            date_of_expiry=date.today() + timedelta(days=20),
        )
    )
    db_session.add(
        Certificate(
            candidate_id=candidate.candidate_id,
            certificate_type="COC",
            expiry_date=date.today() - timedelta(days=1),
        )
    )
    db_session.commit()

    headers = _auth_header(client, "admin_test", "admin123")
    response = client.get(f"/candidates/{candidate.candidate_id}", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["surname"] == "Flagged"
    passport = find_document(payload["documents"], lambda row: row.get("warning") is True)
    assert passport is not None
    assert passport["warning"] is True
    assert passport["expired"] is False

    _section, expired_cert = find_certificate(
        payload,
        lambda row: row.get("expired") is True,
    )
    assert expired_cert is not None
    assert expired_cert["expired"] is True


def test_notifications_are_human_readable_and_include_focus_ids(
    db_session, client: TestClient, auth_seed
) -> None:
    candidate = Candidate(surname="Readable", first_name="Messages")
    db_session.add(candidate)
    db_session.flush()

    doc = Document(
        candidate_id=candidate.candidate_id,
        document_type="Passport",
        date_of_expiry=date.today() - timedelta(days=2),
    )
    cert = Certificate(
        candidate_id=candidate.candidate_id,
        certificate_type="GMDSS",
        expiry_date=date.today() - timedelta(days=1),
    )
    db_session.add_all([doc, cert])
    db_session.commit()
    db_session.refresh(doc)
    db_session.refresh(cert)

    headers = _auth_header(client, "admin_test", "admin123")
    response = client.get("/notifications", params={"sent": False}, headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    candidate_items = [item for item in items if item.get("candidate_id") == candidate.candidate_id]
    assert candidate_items, "Expected active notifications for candidate"

    doc_expired = next((item for item in candidate_items if item.get("message", "").startswith("Документ просрочен:")), None)
    cert_expired = next(
        (item for item in candidate_items if item.get("message", "").startswith("Сертификат просрочен:")),
        None,
    )
    assert doc_expired is not None
    assert cert_expired is not None

    assert "Кандидат #" not in doc_expired["message"]
    assert "(id=" not in doc_expired["message"]
    assert doc_expired.get("document_id") == doc.document_id

    assert "Кандидат #" not in cert_expired["message"]
    assert "(id=" not in cert_expired["message"]
    assert cert_expired.get("certificate_id") == cert.certificate_id
    assert cert_expired.get("document_id") is None


def test_search_endpoint_filters_by_position_and_expiry(
    db_session, client: TestClient, auth_seed
) -> None:
    warning_candidate = Candidate(surname="Petrov", first_name="Ivan", current_rank="Chief Officer")
    expired_candidate = Candidate(surname="Sidorov", first_name="Nikolay", current_rank="Captain")
    db_session.add_all([warning_candidate, expired_candidate])
    db_session.flush()

    db_session.add(
        Application(
            candidate_id=warning_candidate.candidate_id,
            position_applied_for="Chief Officer",
            rank_applied_for="C/O",
        )
    )
    db_session.add(
        Document(
            candidate_id=warning_candidate.candidate_id,
            document_type="Passport",
            date_of_expiry=date.today() + timedelta(days=60),
        )
    )
    db_session.add(
        Certificate(
            candidate_id=expired_candidate.candidate_id,
            certificate_type="COC",
            expiry_date=date.today() - timedelta(days=5),
        )
    )
    db_session.commit()

    headers = _auth_header(client, "admin_test", "admin123")
    by_position = client.get("/candidates/search", params={"position": "chief"}, headers=headers)
    assert by_position.status_code == 200
    assert any(item["surname"] == "Petrov" for item in by_position.json()["items"])

    by_warning = client.get("/candidates/search", params={"expiry_status": "warning"}, headers=headers)
    assert by_warning.status_code == 200
    warning_items = by_warning.json()["items"]
    assert any(item["surname"] == "Petrov" and item["expiry_warning"] is True for item in warning_items)

    by_expired = client.get("/candidates/search", params={"expiry_status": "expired"}, headers=headers)
    assert by_expired.status_code == 200
    expired_items = by_expired.json()["items"]
    assert any(item["surname"] == "Sidorov" and item["expiry_expired"] is True for item in expired_items)


def test_family_contact_put_explicit_null_clears_optional_fields(
    client: TestClient,
    auth_seed,
    db_session,
) -> None:
    candidate = Candidate(surname="Fam", first_name="Test")
    db_session.add(candidate)
    db_session.flush()
    fc = FamilyContact(
        candidate_id=candidate.candidate_id,
        full_name="Anna Petrova",
        relationship_to_candidate="Spouse",
        phone="+79990001122",
        email="anna@example.com",
        address="Kyiv",
    )
    db_session.add(fc)
    db_session.commit()

    headers = _auth_header(client, "admin_test", "admin123")
    response = client.put(
        f"/candidates/{candidate.candidate_id}/family-contacts/{fc.family_contact_id}",
        json={
            "full_name": "Anna Petrova",
            "relationship_to_candidate": None,
            "phone": None,
            "email": None,
            "address": None,
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()["family_contact"]
    assert payload.get("relationship_to_candidate") is None
    assert payload.get("phone") is None
    assert payload.get("email") is None
    assert payload.get("address") is None


def test_flag_document_put_explicit_null_clears_optional_fields(
    client: TestClient,
    auth_seed,
    db_session,
) -> None:
    candidate = Candidate(surname="Flag", first_name="Clear")
    db_session.add(candidate)
    db_session.flush()
    fd = FlagDocument(
        candidate_id=candidate.candidate_id,
        flag_country="Panama",
        flag_document_type="BOOK",
        rank="Master",
        doc_number="DOC-1",
        remarks="keep me until cleared",
    )
    db_session.add(fd)
    db_session.commit()

    headers = _auth_header(client, "admin_test", "admin123")
    response = client.put(
        f"/candidates/{candidate.candidate_id}/flag-documents/{fd.flag_document_id}",
        json={
            "flag_country": "Panama",
            "flag_document_type": None,
            "rank": None,
            "remarks": None,
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()["flag_document"]
    assert payload.get("flag_document_type") is None
    assert payload.get("rank") is None
    assert payload.get("remarks") is None


def test_get_candidate_requires_authentication(client: TestClient, auth_seed, db_session) -> None:
    candidate = Candidate(surname="Solo", first_name="Test")
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    response = client.get(f"/candidates/{candidate.candidate_id}")
    assert response.status_code == 401


def test_login_blocks_after_failed_attempts(
    client: TestClient,
    auth_seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module.login_throttle_reset_for_testing()
    monkeypatch.setattr(main_module, "LOGIN_MAX_FAILED_ATTEMPTS", 3)
    monkeypatch.setattr(main_module, "LOGIN_LOCKOUT_SECONDS", 120)
    for _ in range(3):
        resp = client.post("/auth/login", json={"username": "admin_test", "password": "bad"})
        assert resp.status_code == 401
    blocked = client.post("/auth/login", json={"username": "admin_test", "password": "admin123"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    main_module.login_throttle_reset_for_testing()
    ok = client.post("/auth/login", json={"username": "admin_test", "password": "admin123"})
    assert ok.status_code == 200


def test_document_put_rejects_expiry_before_issue(client: TestClient, auth_seed, db_session) -> None:
    candidate = Candidate(surname="DocDates", first_name="Test")
    db_session.add(candidate)
    db_session.flush()
    doc = Document(
        candidate_id=candidate.candidate_id,
        document_type="Passport",
        date_of_issue=date(2020, 1, 10),
        date_of_expiry=date(2030, 1, 10),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    headers = _auth_header(client, "admin_test", "admin123")
    resp = client.put(
        f"/candidates/{candidate.candidate_id}/documents/{doc.document_id}",
        json={"date_of_expiry": "2019-12-31"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json().get("detail") == ISSUE_EXPIRY_ORDER_ERROR_MSG


def test_document_put_rejects_both_dates_when_expiry_before_issue(client: TestClient, auth_seed, db_session) -> None:
    candidate = Candidate(surname="DocDates2", first_name="Test")
    db_session.add(candidate)
    db_session.flush()
    doc = Document(
        candidate_id=candidate.candidate_id,
        document_type="CDC",
        date_of_issue=date(2021, 6, 1),
        date_of_expiry=date(2026, 6, 1),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    headers = _auth_header(client, "admin_test", "admin123")
    resp = client.put(
        f"/candidates/{candidate.candidate_id}/documents/{doc.document_id}",
        json={"date_of_issue": "2025-03-03", "date_of_expiry": "2025-01-01"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json().get("detail") == ISSUE_EXPIRY_ORDER_ERROR_MSG


def test_document_post_rejects_expiry_before_issue(client: TestClient, auth_seed, db_session) -> None:
    candidate = Candidate(surname="DocDates3", first_name="Test")
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    headers = _auth_header(client, "admin_test", "admin123")
    resp = client.post(
        f"/candidates/{candidate.candidate_id}/documents",
        json={
            "document_type": "Visa",
            "date_of_issue": "2023-06-06",
            "date_of_expiry": "2020-06-06",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json().get("detail") == ISSUE_EXPIRY_ORDER_ERROR_MSG


def test_certificate_put_rejects_expiry_before_issue(client: TestClient, auth_seed, db_session) -> None:
    candidate = Candidate(surname="CertDates", first_name="Test")
    db_session.add(candidate)
    db_session.flush()
    cert = Certificate(
        candidate_id=candidate.candidate_id,
        certificate_type="STCW",
        date_issued=date(2019, 1, 1),
        expiry_date=date(2029, 1, 1),
    )
    db_session.add(cert)
    db_session.commit()
    db_session.refresh(cert)
    headers = _auth_header(client, "admin_test", "admin123")
    resp = client.put(
        f"/candidates/{candidate.candidate_id}/certificates/{cert.certificate_id}",
        json={"expiry_date": "2018-06-06"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json().get("detail") == ISSUE_EXPIRY_ORDER_ERROR_MSG


def test_flag_document_put_rejects_expiry_before_issuance(client: TestClient, auth_seed, db_session) -> None:
    candidate = Candidate(surname="FlagDates", first_name="Test")
    db_session.add(candidate)
    db_session.flush()
    fd = FlagDocument(
        candidate_id=candidate.candidate_id,
        flag_country="Malta",
        date_of_issuance=date(2021, 4, 4),
        date_of_expiry=date(2027, 4, 4),
    )
    db_session.add(fd)
    db_session.commit()
    db_session.refresh(fd)
    headers = _auth_header(client, "admin_test", "admin123")
    resp = client.put(
        f"/candidates/{candidate.candidate_id}/flag-documents/{fd.flag_document_id}",
        json={"date_of_expiry": "2020-01-01"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json().get("detail") == ISSUE_EXPIRY_ORDER_ERROR_MSG


def test_expiry_highlight_business_logic() -> None:
    items = [
        {"name": "warning-doc", "date_of_expiry": (date.today() + timedelta(days=30)).isoformat()},
        {"name": "expired-doc", "date_of_expiry": (date.today() - timedelta(days=3)).isoformat()},
        {"name": "normal-doc", "date_of_expiry": (date.today() + timedelta(days=500)).isoformat()},
    ]

    flagged = _with_expiry_flags(items, "date_of_expiry")

    assert flagged[0]["warning"] is True and flagged[0]["expired"] is False
    assert flagged[1]["expired"] is True and flagged[1]["warning"] is False
    assert flagged[2]["warning"] is False and flagged[2]["expired"] is False
