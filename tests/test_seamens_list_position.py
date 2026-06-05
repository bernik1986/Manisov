"""
Seamens Data list: position column and position filter.

Source of truth for displayed/filtered rank:
  first application (lowest application_id) → position_applied_for, else rank_applied_for.

Not used for list/filter:
  candidates.current_rank, sea_services.rank_on_vessel.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import _raw_list_position_from_row, app, get_db_session
from app.rank_normalization import display_position_label
from models.db import Base
from models.schema import Application, Candidate, Role, SeaService, User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@pytest.fixture
def seamens_client():
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


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/auth/login", json={"username": "admin_seamens", "password": "admin123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_admin(db) -> None:
    role = Role(name="admin")
    db.add(role)
    db.flush()
    db.add(
        User(
            username="admin_seamens",
            password_hash=pwd_context.hash("admin123"),
            role_id=role.role_id,
            is_active=True,
        )
    )
    db.commit()


def test_raw_list_position_prefers_first_application_fields() -> None:
    db = sessionmaker(
        bind=__import__("sqlalchemy").create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    )()
    Base.metadata.create_all(bind=db.get_bind())
    try:
        cand = Candidate(surname="App", first_name="First", current_rank="Master")
        db.add(cand)
        db.flush()
        db.add(
            Application(
                candidate_id=cand.candidate_id,
                application_id=10,
                position_applied_for="Chief Officer",
            )
        )
        db.add(
            Application(
                candidate_id=cand.candidate_id,
                application_id=5,
                position_applied_for="Second Engineer",
            )
        )
        db.add(
            SeaService(
                candidate_id=cand.candidate_id,
                rank_on_vessel="Electrician",
            )
        )
        db.commit()
        db.refresh(cand)
        db.expire(cand, ["applications", "sea_service"])
        assert _raw_list_position_from_row(cand) == "Second Engineer"
    finally:
        Base.metadata.drop_all(bind=db.get_bind())
        db.close()


def test_raw_list_position_uses_rank_applied_when_position_empty() -> None:
    db = sessionmaker(
        bind=__import__("sqlalchemy").create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    )()
    Base.metadata.create_all(bind=db.get_bind())
    try:
        cand = Candidate(surname="Rank", first_name="Only")
        db.add(cand)
        db.flush()
        db.add(
            Application(
                candidate_id=cand.candidate_id,
                rank_applied_for="3/O",
            )
        )
        db.commit()
        db.refresh(cand)
        assert display_position_label(_raw_list_position_from_row(cand)) == "Third Officer"
    finally:
        Base.metadata.drop_all(bind=db.get_bind())
        db.close()


def test_raw_list_position_none_without_application() -> None:
    cand = Candidate(surname="Empty", first_name="App", current_rank="Master")
    cand.applications = []
    cand.sea_service = [SeaService(rank_on_vessel="AB")]
    assert _raw_list_position_from_row(cand) is None


def test_paged_list_ignores_sea_service_and_current_rank(seamens_client) -> None:
    client, Session = seamens_client
    db = Session()
    _seed_admin(db)
    mixed = Candidate(surname="Mixed", first_name="Rank", current_rank="Chief Officer")
    chief = Candidate(surname="Chief", first_name="Only")
    db.add_all([mixed, chief])
    db.flush()
    db.add(
        Application(
            candidate_id=mixed.candidate_id,
            position_applied_for="Second Officer",
        )
    )
    db.add(
        Application(
            candidate_id=chief.candidate_id,
            position_applied_for="Chief Officer",
        )
    )
    db.add(
        SeaService(
            candidate_id=mixed.candidate_id,
            rank_on_vessel="Chief Officer",
        )
    )
    db.add(
        SeaService(
            candidate_id=chief.candidate_id,
            rank_on_vessel="Second Officer",
        )
    )
    db.commit()
    mixed_id = mixed.candidate_id
    chief_id = chief.candidate_id
    db.close()

    headers = _auth_headers(client)
    all_rows = client.get("/candidates/paged?page_size=50", headers=headers)
    assert all_rows.status_code == 200
    by_id = {row["id"]: row for row in all_rows.json()["data"]}
    assert by_id[mixed_id]["position"] == "Second Officer"
    assert by_id[chief_id]["position"] == "Chief Officer"


def test_paged_position_filter_matches_application_only(seamens_client) -> None:
    client, Session = seamens_client
    db = Session()
    _seed_admin(db)
    cand = Candidate(surname="Filter", first_name="Me", current_rank="Master")
    db.add(cand)
    db.flush()
    db.add(Application(candidate_id=cand.candidate_id, position_applied_for="Second Engineer"))
    db.add(SeaService(candidate_id=cand.candidate_id, rank_on_vessel="Master"))
    db.commit()
    cand_id = cand.candidate_id
    db.close()

    headers = _auth_headers(client)
    hit = client.get("/candidates/paged?position=Second+Engineer&page_size=20", headers=headers)
    miss = client.get("/candidates/paged?position=Master&page_size=20", headers=headers)
    assert hit.status_code == 200
    assert miss.status_code == 200
    hit_ids = {r["id"] for r in hit.json()["data"]}
    miss_ids = {r["id"] for r in miss.json()["data"]}
    assert cand_id in hit_ids
    assert cand_id not in miss_ids


@pytest.mark.parametrize(
    "filter_canon,application_raw,expected_in_filter",
    [
        ("Chief Engineer", "C/E", True),
        ("Chief Officer", "C/O", True),
        ("Second Officer", "2/O", True),
        ("Chief Engineer", "2/O", False),
    ],
)
def test_position_filter_synonyms_respect_application_source(
    seamens_client,
    filter_canon: str,
    application_raw: str,
    expected_in_filter: bool,
) -> None:
    client, Session = seamens_client
    db = Session()
    _seed_admin(db)
    cand = Candidate(surname=f"Syn{application_raw.replace('/', '')}", first_name="Test")
    db.add(cand)
    db.flush()
    db.add(Application(candidate_id=cand.candidate_id, position_applied_for=application_raw))
    db.commit()
    cand_id = cand.candidate_id
    db.close()

    headers = _auth_headers(client)
    resp = client.get(
        f"/candidates/paged?position={filter_canon.replace(' ', '+')}&page_size=50",
        headers=headers,
    )
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["data"]}
    if expected_in_filter:
        assert cand_id in ids
    else:
        assert cand_id not in ids
