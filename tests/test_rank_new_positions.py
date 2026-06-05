"""New canonical ranks: Pumpman, Oiler, Cook, trainees, Junior Officer, Electrician, Gas Engineer."""

from __future__ import annotations

import pytest

from app.rank_normalization import (
    RANK_OPTIONS,
    expand_canonical,
    position_search_terms,
    resolve_canonical_position,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("pumpman", "Pumpman"),
        ("помпман", "Pumpman"),
        ("oiler", "Oiler"),
        ("масленщик", "Oiler"),
        ("cook", "Cook"),
        ("судовой повар", "Cook"),
        ("chief mate trainee", "Chief Officer Trainee"),
        ("2/e trainee", "Second Engineer Trainee"),
        ("junior deck officer", "Junior Officer"),
        ("младший офицер", "Junior Officer"),
        ("ship electrician", "Electrician"),
        ("судовой электрик", "Electrician"),
        ("lng gas engineer", "Gas Engineer"),
        ("газовый инженер", "Gas Engineer"),
    ],
)
def test_resolve_new_position_synonyms(raw: str, expected: str) -> None:
    assert resolve_canonical_position(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ETO", "Electro Technical Officer"),
        ("eto", "Electro Technical Officer"),
        ("electrotechnical officer", "Electro Technical Officer"),
        ("motorman", "Motorman"),
        ("Motor Man", "Motorman"),
    ],
)
def test_eto_and_motorman_precedence_over_near_duplicates(raw: str, expected: str) -> None:
    assert resolve_canonical_position(raw) == expected


def test_third_officer_no_longer_maps_junior_officer() -> None:
    assert resolve_canonical_position("junior officer") == "Junior Officer"
    assert resolve_canonical_position("3/O") == "Third Officer"


def test_rank_options_include_all_new_canonicals() -> None:
    for label in (
        "Pumpman",
        "Oiler",
        "Cook",
        "Chief Officer Trainee",
        "Second Engineer Trainee",
        "Junior Officer",
        "Electrician",
        "Gas Engineer",
    ):
        assert label in RANK_OPTIONS


def test_position_search_terms_pumpman_expands() -> None:
    terms = position_search_terms("Pumpman")
    lowered = {t.lower() for t in terms}
    assert "pumpman" in lowered
    assert "насосчик" in lowered


def test_position_search_terms_oiler_not_motorman() -> None:
    terms = position_search_terms("Oiler")
    lowered = {t.lower() for t in terms}
    assert "oiler" in lowered
    assert "масленщик" in lowered


def test_expand_canonical_gas_engineer() -> None:
    terms = expand_canonical("Gas Engineer")
    assert "lng gas engineer" in {t.lower() for t in terms}
