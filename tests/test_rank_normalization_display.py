"""Canonical position labels (resolve, display, SQL search terms).

Seamens Data list column and position filter use recruitment application fields;
see tests/test_seamens_list_position.py.
"""

from __future__ import annotations

from app.rank_normalization import display_position_label, resolve_canonical_position


def test_resolve_2e_synonyms():
    for raw in ("2E", "2/E", "2nd Engineer", "Second Engineer Officer"):
        assert resolve_canonical_position(raw) == "Second Engineer"


def test_resolve_co_and_jr_officer_aliases() -> None:
    assert resolve_canonical_position("CO") == "Chief Officer"
    assert resolve_canonical_position("C/O") == "Chief Officer"
    assert resolve_canonical_position("JR. OFFICER") == "Junior Officer"


def test_resolve_engine_cadet_not_deck_cadet() -> None:
    assert resolve_canonical_position("Engine Cadet") == "Engine Cadet"
    assert resolve_canonical_position("Deck Cadet") == "Deck Cadet"


def test_chief_officer_search_terms_exclude_short_co_substring() -> None:
    from app.rank_normalization import position_search_terms

    terms = position_search_terms("Chief Officer")
    lowered = {t.lower() for t in terms}
    assert "co" not in lowered
    assert not any("second officer" in f"%{t.lower()}%" for t in terms if len(t) <= 3)


def test_display_position_label_maps_synonym():
    assert display_position_label("2E") == "Second Engineer"
    assert display_position_label("Chief Mate") == "Chief Officer"


def test_display_position_label_keeps_unknown():
    assert display_position_label("Superintendent") == "Superintendent"
    assert display_position_label(None) is None
    assert display_position_label("  ") is None
