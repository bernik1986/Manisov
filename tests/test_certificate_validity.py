"""Certificate validity modes: +5 years, unlimited."""

from __future__ import annotations

from datetime import date

import pytest

from app.certificate_validity import (
    apply_certificate_validity_defaults,
    apply_plus5_years,
)


@pytest.mark.parametrize(
    "issued,expiry,expected_expiry,expected_issued",
    [
        (date(2020, 3, 1), None, date(2025, 3, 1), None),
        (None, date(2025, 6, 15), None, date(2020, 6, 15)),
        (date(2020, 2, 29), None, date(2025, 2, 28), None),
    ],
)
def test_apply_plus5_years(issued, expiry, expected_expiry, expected_issued) -> None:
    payload: dict = {}
    if issued:
        payload["date_issued"] = issued
    if expiry:
        payload["expiry_date"] = expiry
    out = apply_plus5_years(payload)
    if expected_expiry:
        assert out["expiry_date"] == expected_expiry
    if expected_issued:
        assert out["date_issued"] == expected_issued
    assert out["unlimited_validity"] is False


def test_apply_defaults_skips_when_both_dates_present() -> None:
    payload = {
        "date_issued": date(2020, 1, 1),
        "expiry_date": date(2023, 1, 1),
    }
    out = apply_certificate_validity_defaults(payload)
    assert out["expiry_date"] == date(2023, 1, 1)


def test_apply_defaults_unlimited_clears_expiry() -> None:
    out = apply_certificate_validity_defaults(
        {"unlimited_validity": True, "date_issued": date(2020, 1, 1), "expiry_date": date(2025, 1, 1)}
    )
    assert out["unlimited_validity"] is True
    assert out["expiry_date"] is None


def test_apply_defaults_fills_missing_when_only_issued() -> None:
    out = apply_certificate_validity_defaults({"date_issued": date(2020, 3, 1)})
    assert out["expiry_date"] == date(2025, 3, 1)
