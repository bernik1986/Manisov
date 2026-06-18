from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.db import Base
from models.schema import Candidate, Role, User
from parser.pdf_parser import PDFParser
from tests.canonical_test_helpers import count_certificate_rows

app_main_spec = importlib.util.spec_from_file_location("parcer_app_main", PROJECT_ROOT / "app" / "main.py")
assert app_main_spec and app_main_spec.loader
app_main = importlib.util.module_from_spec(app_main_spec)
app_main_spec.loader.exec_module(app_main)

app = app_main.app
get_db_session = app_main.get_db_session
pwd_context = app_main.pwd_context


TESTS_DIR = Path(__file__).resolve().parent
DORCHYNETS_PDF = TESTS_DIR / "2O Dorchynets CHANDRIS CR-RT 05A - SEAMEN'S APPLICATION & INTERVIEW RECORD.pdf"
MALINOVSKY_PDF = TESTS_DIR / "ETO Malinovsky CHANDRIS CR-RT 05A - SEAMEN'S APPLICATION & INTERVIEW RECORD.pdf"


def _make_test_client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite:///:memory:",
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

    with TestingSessionLocal() as session:
        admin_role = Role(name="admin", description="Full access")
        session.add(admin_role)
        session.flush()
        session.add(
            User(
                username="admin",
                password_hash=pwd_context.hash("admin123"),
                full_name="Test Admin",
                role_id=admin_role.role_id,
                is_active=True,
            )
        )
        session.commit()

    return TestClient(app), TestingSessionLocal


def _login_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_chandris_pdf_parser_extracts_documents_certificates_and_experience() -> None:
    result = PDFParser().parse(DORCHYNETS_PDF)

    assert result["personal_data"]["surname"] == "Dorchynets"
    assert result["personal_data"]["first_name"] == "Vasyl"
    assert result["personal_data"]["passport_number"] == "FN 677634"
    assert result["applications"][0]["position_applied_for"] == "Second Officer"
    assert len(result["documents"]) >= 3
    assert len(result["certificates"]) >= 2
    assert len(result["flag_documents"]) >= 2
    assert len(result["sea_service"]) >= 4
    assert any(item.get("vessel_name") == "Delta Angelica" for item in result["sea_service"])
    assert any(item.get("certificate_type") == "Yellow Fever Vaccination" for item in result["certificates"])


def test_chandris_pdf_parser_handles_split_competency_rank_and_engine_data() -> None:
    result = PDFParser().parse(MALINOVSKY_PDF)

    assert result["personal_data"]["surname"] == "Malinovsky"
    assert result["personal_data"]["first_name"] == "Roman"
    assert result["personal_data"]["certificate_of_competency_rank"] == "First-class electro-technical officer"
    assert len(result["documents"]) >= 3
    assert len(result["certificates"]) >= 2
    assert len(result["sea_service"]) >= 6
    assert any(item.get("rank_on_vessel") == "Electrician" for item in result["sea_service"])
    assert any(item.get("main_engine") == "MAN-B&W 6S70MC-C" for item in result["sea_service"])


def test_upload_pdf_persists_related_sections_for_chandris_forms() -> None:
    client, _session_local = _make_test_client()
    try:
        headers = _login_headers(client)

        with DORCHYNETS_PDF.open("rb") as fh:
            upload_response = client.post(
                "/upload",
                files={"file": (DORCHYNETS_PDF.name, fh, "application/pdf")},
                headers=headers,
            )

        assert upload_response.status_code == 200
        payload = upload_response.json()
        candidate_id = payload["candidate_id"]

        candidate_response = client.get(f"/candidates/{candidate_id}", headers=headers)
        assert candidate_response.status_code == 200
        candidate_payload = candidate_response.json()

        assert candidate_payload["candidate"]["surname"] == "DORCHYNETS"
        assert len(candidate_payload["documents"]) >= 3
        assert count_certificate_rows(candidate_payload) >= 2
        assert len(candidate_payload["flag_documents"]) >= 2
        assert len(candidate_payload["sea_service"]) >= 4
        assert len(candidate_payload["family_contacts"]) >= 1
    finally:
        app.dependency_overrides.clear()


def test_duplicate_pdf_upload_merges_into_existing_candidate() -> None:
    client, session_local = _make_test_client()
    try:
        headers = _login_headers(client)

        with session_local() as session:
            candidate = Candidate(
                surname="Dorchynets",
                first_name="Vasyl",
                middle_name="Vasyl",
                date_of_birth=date(1985, 11, 23),
                full_name="Vasyl Vasyl Dorchynets",
                email="legacy@example.com",
            )
            session.add(candidate)
            session.commit()
            session.refresh(candidate)
            candidate_id = candidate.candidate_id

        with DORCHYNETS_PDF.open("rb") as fh:
            upload_response = client.post(
                "/upload",
                files={"file": (DORCHYNETS_PDF.name, fh, "application/pdf")},
                headers=headers,
            )

        assert upload_response.status_code == 200
        payload = upload_response.json()
        assert payload["duplicate"] is True
        assert payload["candidate_id"] == candidate_id
        assert payload["requires_confirmation"] is True
        assert payload["updated"] is False

        candidate_response_before_merge = client.get(f"/candidates/{candidate_id}", headers=headers)
        assert candidate_response_before_merge.status_code == 200
        candidate_payload_before_merge = candidate_response_before_merge.json()
        assert candidate_payload_before_merge["candidate"]["passport_number"] is None

        with DORCHYNETS_PDF.open("rb") as fh:
            confirm_response = client.post(
                "/upload",
                data={"confirm_duplicate_update": "true"},
                files={"file": (DORCHYNETS_PDF.name, fh, "application/pdf")},
                headers=headers,
            )
        assert confirm_response.status_code == 200
        confirm_payload = confirm_response.json()
        assert confirm_payload["duplicate"] is True
        assert confirm_payload["candidate_id"] == candidate_id
        assert confirm_payload["requires_confirmation"] is False
        assert confirm_payload["updated"] is True

        candidate_response = client.get(f"/candidates/{candidate_id}", headers=headers)
        assert candidate_response.status_code == 200
        candidate_payload = candidate_response.json()

        assert candidate_payload["candidate"]["passport_number"] == "FN 677634"
        assert len(candidate_payload["documents"]) >= 3
        assert count_certificate_rows(candidate_payload) >= 2
        assert len(candidate_payload["flag_documents"]) >= 2
        assert len(candidate_payload["sea_service"]) >= 4
        assert len(candidate_payload["family_contacts"]) >= 1
    finally:
        app.dependency_overrides.clear()
