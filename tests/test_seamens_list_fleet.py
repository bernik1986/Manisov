"""Seamens Data fleet column and filter: latest sea service vessel_type only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from datetime import date
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import _display_list_fleet_from_row, _latest_sea_service, _raw_list_fleet_from_row, app, get_db_session
from models.db import Base
from models.schema import Application, Candidate, Role, SeaService, User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def test_latest_sea_service_picks_most_recent_sign_on() -> None:
    cand = Candidate(surname="X", first_name="Y")
    cand.sea_service = [
        SeaService(sea_service_id=1, sign_on_date=date(2020, 1, 1), vessel_type="Bulk Carrier"),
        SeaService(sea_service_id=2, sign_on_date=date(2024, 6, 1), vessel_type="Oil Tanker"),
    ]
    latest = _latest_sea_service(cand)
    assert latest is not None
    assert latest.vessel_type == "Oil Tanker"


def test_fleet_from_row_ignores_proposed_vessel_and_older_contracts() -> None:
    cand = Candidate(surname="Z", first_name="W")
    cand.applications = [Application(proposed_vessel="TBN")]
    cand.sea_service = [
        SeaService(sea_service_id=1, sign_on_date=date(2022, 1, 1), vessel_type="bulker"),
        SeaService(sea_service_id=2, sign_on_date=date(2024, 1, 1), vessel_type=""),
    ]
    assert _raw_list_fleet_from_row(cand) is None
    assert _display_list_fleet_from_row(cand) is None

    cand.sea_service[1].vessel_type = "VLCC"
    assert _display_list_fleet_from_row(cand) == "VLCC"


@pytest.fixture
def fleet_latest_client():
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
        with TestClient(app) as client:
            yield client, TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_paged_fleet_filter_uses_latest_contract_only(fleet_latest_client) -> None:
    client, Session = fleet_latest_client
    db = Session()
    role = Role(name="admin")
    db.add(role)
    db.flush()
    db.add(
        User(
            username="admin_fleet2",
            password_hash=pwd_context.hash("admin123"),
            role_id=role.role_id,
            is_active=True,
        )
    )
    cand = Candidate(surname="LatestFleet", first_name="Test")
    db.add(cand)
    db.flush()
    db.add(Application(candidate_id=cand.candidate_id, proposed_vessel="TBN"))
    db.add(
        SeaService(
            candidate_id=cand.candidate_id,
            sign_on_date=date(2020, 1, 1),
            vessel_type="Dry Bulk Carrier",
        )
    )
    db.add(
        SeaService(
            candidate_id=cand.candidate_id,
            sign_on_date=date(2024, 1, 1),
            vessel_type="Chem Tanker",
        )
    )
    db.commit()
    cand_id = cand.candidate_id
    db.close()

    login = client.post("/auth/login", json={"username": "admin_fleet2", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    row = client.get("/candidates/paged?page_size=50", headers=headers)
    assert row.status_code == 200
    by_id = {r["id"]: r for r in row.json()["data"]}
    assert by_id[cand_id]["fleet"] == "Chemical Tanker"

    bulk_only = client.get("/candidates/paged?fleet=Bulk+Carrier&page_size=50", headers=headers)
    assert cand_id not in {r["id"] for r in bulk_only.json()["data"]}

    chem = client.get("/candidates/paged?fleet=Chemical+Tanker&page_size=50", headers=headers)
    assert cand_id in {r["id"] for r in chem.json()["data"]}
