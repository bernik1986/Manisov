from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.contract_fields import (
    CANDIDATE_PERSONAL_PLACEHOLDER_FIELDS,
    build_saved_contract_payload,
    candidate_personal_placeholder_lines,
    contract_placeholders_from_saved,
    parse_contract_json,
)
from app.main import app, get_db_session, pwd_context
from models.db import Base
from models.schema import Candidate, Company, CompanyFolder, Role, User, Vessel


@pytest.fixture
def db_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


@pytest.fixture
def db_session(db_setup):
    session = db_setup()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def users_fixture(db_session):
    admin_role = Role(name="admin", description="Admin")
    db_session.add(admin_role)
    db_session.flush()
    user = User(
        username="admin_contract",
        password_hash=pwd_context.hash("admin123"),
        role_id=admin_role.role_id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def client(db_setup, db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_contract_placeholders_include_airports():
    data = {
        "company_name": "Co",
        "rank": "CO",
        "contract_home_airport": "Odessa International",
        "contract_departure_airport": "Bucharest",
        "contract_departure_date": "15-06-2026",
    }
    placeholders = contract_placeholders_from_saved(data)
    assert placeholders["contract_home_airport"] == "Odessa International"
    assert placeholders["contract_departure_airport"] == "Bucharest"
    assert placeholders["contract_departure_date"] == "15-06-2026"
    assert placeholders["home_airport"] == "Odessa International"
    assert placeholders["departure_airport"] == "Bucharest"
    assert placeholders["departure_date"] == "15-06-2026"


def test_contract_placeholders_include_vessel_fields(db_session):
    root = CompanyFolder(name="Companies", parent_id=None)
    db_session.add(root)
    db_session.flush()
    company = Company(folder_id=root.folder_id, name="Drylog", slug="drylog")
    db_session.add(company)
    db_session.flush()
    vessel = Vessel(
        company_id=company.company_id,
        name="Star",
        slug="star",
        imo="1234567",
        flag="Malta",
        grt="45000",
    )
    db_session.add(vessel)
    db_session.commit()

    data = {
        "company_id": company.company_id,
        "company_name": company.name,
        "vessel_id": vessel.vessel_id,
        "vessel_name": vessel.name,
        "rank": "Chief Officer",
        "contract_number": "C-001",
    }
    placeholders = contract_placeholders_from_saved(data, db_session=db_session)
    assert placeholders["contract_company_name"] == "Drylog"
    assert placeholders["contract_rank"] == "Chief Officer"
    assert placeholders["contract_number"] == "C-001"
    assert placeholders["contract_vessel_imo"] == "1234567"
    assert placeholders["company_drylog_star_imo"] == "1234567"


def test_save_and_load_contract_json(client: TestClient, db_session, users_fixture):
    root = CompanyFolder(name="Companies", parent_id=None)
    db_session.add(root)
    db_session.flush()
    candidate = Candidate(surname="Test", first_name="User", current_rank="CO")
    company = Company(folder_id=root.folder_id, name="Century", slug="century")
    db_session.add_all([candidate, company])
    db_session.commit()

    login = client.post("/auth/login", json={"username": "admin_contract", "password": "admin123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.put(
        f"/candidates/{candidate.candidate_id}/contract",
        headers=headers,
        json={
            "company_id": company.company_id,
            "rank": "Chief Officer",
            "contract_number": "SEA-99",
            "contract_period": "6 months",
            "contract_home_airport": "Warsaw Chopin",
            "contract_departure_airport": "Istanbul",
            "contract_departure_date": "20-07-2026",
        },
    )
    assert response.status_code == 200
    saved = response.json()["contract"]
    assert saved["contract_number"] == "SEA-99"
    assert saved["rank"] == "Chief Officer"
    assert saved["contract_home_airport"] == "Warsaw Chopin"
    assert saved["contract_departure_airport"] == "Istanbul"
    assert saved["contract_departure_date"] == "20-07-2026"

    db_session.refresh(candidate)
    parsed = parse_contract_json(candidate.contract_json)
    assert parsed["contract_number"] == "SEA-99"
    assert parsed["contract_departure_date"] == "20-07-2026"
    assert candidate.home_airport == "Warsaw Chopin"
    assert candidate.departure_airport == "Istanbul"


def test_contracts_folder_endpoint_empty(client: TestClient, db_session, users_fixture):
    candidate = Candidate(surname="X", first_name="Y")
    db_session.add(candidate)
    db_session.commit()

    login = client.post("/auth/login", json={"username": "admin_contract", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/templates-manager/contracts-folder", headers=headers)
    assert response.status_code == 200
    assert response.json()["files"] == []


def test_candidate_personal_placeholder_lines():
    lines = candidate_personal_placeholder_lines()
    assert "{{ surname }}" in lines
    assert "{{ age }}" in lines
    assert len(lines) == len(CANDIDATE_PERSONAL_PLACEHOLDER_FIELDS)


def test_build_saved_contract_payload():
    saved = build_saved_contract_payload(
        company_id=1,
        company_name="Co",
        vessel_id=2,
        vessel_name="V",
        rank="Master",
        editable={"contract_number": "1"},
        username="admin",
    )
    assert saved["company_id"] == 1
    assert saved["vessel_name"] == "V"
    assert saved["contract_number"] == "1"
