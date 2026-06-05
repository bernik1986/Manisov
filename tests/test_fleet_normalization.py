"""Fleet / vessel-type normalization for Seamens Data filters and list display."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.fleet_normalization import (
    CANONICAL_ALIASES,
    FLEET_OPTIONS,
    FLEET_PRECEDENCE,
    display_fleet_label,
    expand_canonical_fleet,
    fleet_search_terms,
    resolve_canonical_fleet,
)
from app.main import app, get_db_session
from models.db import Base
from models.schema import Application, Candidate, Role, SeaService, User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("bulk carrier", "Bulk Carrier"),
        ("BULKER", "Bulk Carrier"),
        ("балкер", "Bulk Carrier"),
        ("dry cargo bulk carrier", "Bulk Carrier"),
        ("container ship", "Container Vessel"),
        ("Container", "Container Vessel"),
        ("контейнеровоз", "Container Vessel"),
        ("boxship", "Container Vessel"),
        ("lng carrier", "LNG Carrier"),
        ("ЛНГ", "LNG Carrier"),
        ("lpg tanker", "LPG Carrier"),
        ("oil/chemical tanker", "Oil/Chemical Tanker"),
        ("product chemical tanker", "Oil/Chemical Tanker"),
        ("parcel tanker", "Oil/Chemical Tanker"),
        ("crude oil tanker", "Crude Oil Tanker"),
        ("oil tanker", "Crude Oil Tanker"),
        ("aframax", "Crude Oil Tanker"),
        ("VLCC", "VLCC"),
        ("very large crude carrier", "VLCC"),
        ("chemical tanker", "Chemical Tanker"),
        ("химовоз", "Chemical Tanker"),
        ("chem tanker", "Chemical Tanker"),
        ("general cargo ship", "General Cargo Vessel"),
        ("сухогруз", "General Cargo Vessel"),
        ("freighter", "General Cargo Vessel"),
        ("Tugboat", "Tug"),
        ("harbour tug", "Tug"),
        ("AHT", "Tug"),
        ("cruise ship", "Passenger Vessel"),
        ("ferry", "Passenger Vessel"),
        ("ro-pax", "Passenger Vessel"),
        ("OSV", "Offshore Vessel"),
        ("AHTS", "Offshore Vessel"),
        ("platform supply vessel", "Offshore Vessel"),
        ("heavy lift vessel", "Heavy-Lift Vessel"),
        ("HLV", "Heavy-Lift Vessel"),
        ("reefer vessel", "Reefer"),
        ("refrigerated cargo ship", "Reefer"),
        ("ro-ro", "Ro-Ro"),
        ("car carrier", "Ro-Ro"),
        ("PCTC", "Ro-Ro"),
        ("multipurpose vessel", "Multi-Purpose Vessel"),
        ("mpp vessel", "Multi-Purpose Vessel"),
    ],
)
def test_resolve_canonical_fleet_synonyms(raw: str, expected: str) -> None:
    assert resolve_canonical_fleet(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "m/v Agia Pisti",
        "TBN",
        "Aquasmeralda",
    ],
)
def test_resolve_canonical_fleet_unknown_returns_none(raw: str) -> None:
    assert resolve_canonical_fleet(raw) is None


def test_fleet_precedence_crude_over_chemical() -> None:
    assert resolve_canonical_fleet("crude oil tanker vessel") == "Crude Oil Tanker"


def test_fleet_precedence_chemical_vs_oil_chemical() -> None:
    assert resolve_canonical_fleet("chemical tanker") == "Chemical Tanker"


def test_display_fleet_label_maps_or_preserves() -> None:
    assert display_fleet_label("bulker") == "Bulk Carrier"
    assert display_fleet_label("m/v Random Name") == "m/v Random Name"


def test_fleet_options_match_precedence_keys() -> None:
    assert list(FLEET_OPTIONS) == list(FLEET_PRECEDENCE)
    assert set(FLEET_OPTIONS) == set(CANONICAL_ALIASES.keys())


def test_expand_canonical_fleet_includes_aliases() -> None:
    terms = expand_canonical_fleet("Bulk Carrier")
    lowered = {t.lower() for t in terms}
    assert "bulk carrier" in lowered
    assert "bulker" in lowered
    assert "балкер" in lowered


def test_fleet_search_terms_from_canonical_dropdown_value() -> None:
    terms = fleet_search_terms("Crude Oil Tanker")
    assert "crude oil tanker" in {t.lower() for t in terms}
    assert "oil tanker" in {t.lower() for t in terms}


def test_fleet_search_terms_vlcc() -> None:
    terms = fleet_search_terms("VLCC")
    lowered = {t.lower() for t in terms}
    assert "vlcc" in lowered
    assert "very large crude carrier" in lowered


def test_fleet_search_terms_from_free_text_synonym() -> None:
    terms = fleet_search_terms("bulker")
    assert "bulk carrier" in {t.lower() for t in terms}


@pytest.fixture
def fleet_list_client(tmp_path):
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


def test_paged_list_displays_canonical_fleet_and_filters_by_synonym(fleet_list_client) -> None:
    client, Session = fleet_list_client
    db = Session()
    role = Role(name="admin")
    db.add(role)
    db.flush()
    db.add(
        User(
            username="admin_fleet",
            password_hash=pwd_context.hash("admin123"),
            role_id=role.role_id,
            is_active=True,
        )
    )
    bulk = Candidate(surname="Bulkov", first_name="Ivan")
    chem = Candidate(surname="Chemov", first_name="Petr")
    other = Candidate(surname="Shipov", first_name="Ann")
    db.add_all([bulk, chem, other])
    db.flush()
    db.add(
        Application(candidate_id=bulk.candidate_id, position_applied_for="AB"),
    )
    db.add(
        Application(candidate_id=chem.candidate_id, position_applied_for="2/E"),
    )
    db.add(
        Application(
            candidate_id=other.candidate_id,
            proposed_vessel="TBN",
            position_applied_for="Master",
        )
    )
    db.add(
        SeaService(
            candidate_id=bulk.candidate_id,
            vessel_type="Dry Bulk Carrier",
            rank_on_vessel="AB",
        )
    )
    db.add(
        SeaService(
            candidate_id=chem.candidate_id,
            vessel_type="Chem Tanker",
            rank_on_vessel="2/E",
        )
    )
    db.commit()
    bulk_id = bulk.candidate_id
    chem_id = chem.candidate_id
    other_id = other.candidate_id
    db.close()

    login = client.post("/auth/login", json={"username": "admin_fleet", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    all_rows = client.get("/candidates/paged?page=1&page_size=20", headers=headers)
    assert all_rows.status_code == 200
    by_id = {row["id"]: row for row in all_rows.json()["data"]}
    assert by_id[bulk_id]["fleet"] == "Bulk Carrier"
    assert by_id[chem_id]["fleet"] == "Chemical Tanker"
    assert by_id[other_id]["fleet"] in (None, "-", "")

    filtered = client.get("/candidates/paged?fleet=Bulk+Carrier&page_size=20", headers=headers)
    assert filtered.status_code == 200
    ids = {row["id"] for row in filtered.json()["data"]}
    assert bulk_id in ids
    assert chem_id not in ids

    filtered_chem = client.get("/candidates/paged?fleet=Chemical+Tanker", headers=headers)
    assert filtered_chem.status_code == 200
    chem_ids = {row["id"] for row in filtered_chem.json()["data"]}
    assert chem_id in chem_ids
    assert bulk_id not in chem_ids
