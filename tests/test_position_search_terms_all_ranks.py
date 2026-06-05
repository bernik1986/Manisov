"""SQL search terms for each canonical rank must not match other rank labels."""

from __future__ import annotations

import pytest

from app.rank_normalization import RANK_OPTIONS, position_search_terms


def _allowed_other(canon: str, other: str) -> bool:
    return other == canon or other.startswith(f"{canon} ")


@pytest.mark.parametrize("canon", RANK_OPTIONS)
def test_position_search_terms_do_not_hit_unrelated_rank_labels(canon: str) -> None:
    terms = position_search_terms(canon)
    assert terms, f"no SQL terms for {canon}"
    for other in RANK_OPTIONS:
        if _allowed_other(canon, other):
            continue
        for term in terms:
            assert term.lower() not in other.lower(), (
                f"filter {canon!r} uses term {term!r} which substring-matches {other!r}"
            )


def test_chief_engineer_terms_exclude_ce() -> None:
    terms = position_search_terms("Chief Engineer")
    assert "ce" not in {t.lower() for t in terms}
    assert "CE" not in terms
