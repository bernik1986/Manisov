"""Tests for scripts/normalize_ranks_and_fleet.py data migration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.db import Base
from models.schema import Application, Candidate, SeaService
from scripts.normalize_ranks_and_fleet import evaluate_field, run_normalization
from app.rank_normalization import resolve_canonical_position
from app.fleet_normalization import resolve_canonical_fleet


@pytest.fixture
def norm_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed_candidate(session) -> Candidate:
    cand = Candidate(
        surname="Normov",
        first_name="Test",
        current_rank="Capt",
        certificate_of_competency_rank="C/O",
    )
    session.add(cand)
    session.flush()
    session.add(
        Application(
            candidate_id=cand.candidate_id,
            rank_applied_for="C/O",
            position_applied_for="2/O",
        )
    )
    session.add(
        SeaService(
            candidate_id=cand.candidate_id,
            rank_on_vessel="2/O",
            vessel_type="bulker",
        )
    )
    session.add(
        Candidate(
            surname="Unknownov",
            first_name="Bad",
            current_rank="XYZ unknown rank",
        )
    )
    session.commit()
    session.refresh(cand)
    return cand


def test_evaluate_field_unmapped_and_updated() -> None:
    assert evaluate_field("", resolve_canonical_position, max_length=100) == ("empty", None)
    assert evaluate_field("Capt", resolve_canonical_position, max_length=100) == (
        "updated",
        "Master",
    )
    assert evaluate_field("Master", resolve_canonical_position, max_length=100) == (
        "unchanged",
        None,
    )
    assert evaluate_field("not a rank at all", resolve_canonical_position, max_length=100) == (
        "unmapped",
        None,
    )


def test_dry_run_does_not_change_database(norm_session) -> None:
    cand = _seed_candidate(norm_session)
    stats = run_normalization(norm_session, apply=False)
    norm_session.expire_all()

    row = norm_session.get(Candidate, cand.candidate_id)
    assert row.current_rank == "Capt"
    sea = norm_session.query(SeaService).filter_by(candidate_id=cand.candidate_id).one()
    assert sea.vessel_type == "bulker"
    assert stats.updated > 0


def test_apply_writes_canonical_values(norm_session) -> None:
    cand = _seed_candidate(norm_session)
    stats = run_normalization(norm_session, apply=True)
    norm_session.expire_all()

    assert stats.updated >= 5
    row = norm_session.get(Candidate, cand.candidate_id)
    assert row.current_rank == "Master"
    assert row.certificate_of_competency_rank == "Chief Officer"
    app = norm_session.query(Application).filter_by(candidate_id=cand.candidate_id).one()
    assert app.rank_applied_for == "Chief Officer"
    assert app.position_applied_for == "Second Officer"
    sea = norm_session.query(SeaService).filter_by(candidate_id=cand.candidate_id).one()
    assert sea.rank_on_vessel == "Second Officer"
    assert sea.vessel_type == "Bulk Carrier"


def test_apply_is_idempotent(norm_session) -> None:
    _seed_candidate(norm_session)
    first = run_normalization(norm_session, apply=True)
    norm_session.expire_all()
    second = run_normalization(norm_session, apply=True)
    assert first.updated >= 1
    assert second.updated == 0


def test_unmapped_rank_left_unchanged(norm_session) -> None:
    _seed_candidate(norm_session)
    run_normalization(norm_session, apply=True)
    norm_session.expire_all()
    unknown = norm_session.query(Candidate).filter(Candidate.surname == "UNKNOWNOV").one()
    assert unknown.current_rank == "XYZ unknown rank"


def test_fleet_evaluate_bulker() -> None:
    assert evaluate_field("bulker", resolve_canonical_fleet, max_length=100) == (
        "updated",
        "Bulk Carrier",
    )
