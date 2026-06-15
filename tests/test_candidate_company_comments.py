from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.main import app, get_db_session, pwd_context
from models.db import Base
from models.schema import Candidate, Role, User


@pytest.fixture
def db_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


@pytest.fixture
def db_session(db_setup):
    session = db_setup()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_seed(db_session):
    admin_role = Role(name="admin", description="Admin")
    db_session.add(admin_role)
    db_session.flush()
    user = User(
        username="admin_candidate_company",
        password_hash=pwd_context.hash("admin123"),
        full_name="Admin",
        role_id=admin_role.role_id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def client(db_setup):
    def override_get_db():
        db = db_setup()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": "admin_candidate_company", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_candidate_company_filter_and_comments(client: TestClient, db_session, auth_seed) -> None:
    headers = _auth_headers(client)

    companies_resp = client.get("/companies-manager", headers=headers)
    assert companies_resp.status_code == 200
    companies = companies_resp.json()["companies"]
    marmaras = next(item for item in companies if item["name"] == "Marmaras")
    delta = next(item for item in companies if item["name"] == "Delta Tankers")

    candidate_a = Candidate(surname="Ivanov", first_name="Ivan")
    candidate_b = Candidate(surname="Petrov", first_name="Petro", company_id=delta["company_id"])
    db_session.add_all([candidate_a, candidate_b])
    db_session.commit()
    db_session.refresh(candidate_a)
    db_session.refresh(candidate_b)

    update_resp = client.put(
        f"/candidates/{candidate_a.candidate_id}",
        json={"company_id": marmaras["company_id"]},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["candidate"]["company_id"] == marmaras["company_id"]

    comment_resp = client.post(
        f"/candidates/{candidate_a.candidate_id}/comments",
        json={"comment_text": "First call completed"},
        headers=headers,
    )
    assert comment_resp.status_code == 200
    created_comment = comment_resp.json()["comment"]
    assert created_comment["comment_text"] == "First call completed"
    assert created_comment["created_at"]

    candidate_resp = client.get(f"/candidates/{candidate_a.candidate_id}", headers=headers)
    assert candidate_resp.status_code == 200
    payload = candidate_resp.json()
    assert payload["candidate"]["company_id"] == marmaras["company_id"]
    assert payload["comments"][0]["comment_text"] == "First call completed"

    list_resp = client.get(
        "/candidates/paged",
        params={"company_id": marmaras["company_id"], "page_size": 20},
        headers=headers,
    )
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert list_payload["total"] == 1
    assert list_payload["data"][0]["id"] == candidate_a.candidate_id
    assert list_payload["data"][0]["company_name"] == "Marmaras"
