"""Contract duration Y/M/D for sea service (inclusive dates)."""

from __future__ import annotations

from datetime import date

import pytest

from app.sea_service_duration import apply_sea_service_defaults, contract_duration_ymd


@pytest.mark.parametrize(
    "sign_on,sign_off,expected",
    [
        (date(2025, 12, 23), date(2026, 5, 3), "0/4/11"),
        (date(2025, 2, 8), date(2025, 6, 23), "0/4/16"),
        (date(2024, 9, 5), date(2024, 12, 11), "0/3/7"),
        (date(2024, 2, 15), date(2024, 6, 2), "0/3/19"),
        (date(2023, 7, 3), date(2023, 11, 16), "0/4/14"),
        (date(2022, 10, 27), date(2023, 3, 8), "0/4/10"),
        ("23-12-2025", "03-05-2026", "0/4/11"),
    ],
)
def test_contract_duration_ymd(sign_on, sign_off, expected: str) -> None:
    assert contract_duration_ymd(sign_on, sign_off) == expected


def test_contract_duration_invalid_range() -> None:
    assert contract_duration_ymd(date(2026, 1, 1), date(2025, 1, 1)) is None


def test_apply_sea_service_defaults_remarks_eoc() -> None:
    out = apply_sea_service_defaults({"vessel_name": "MV Test"})
    assert out["remarks"] == "EOC"


def test_apply_sea_service_defaults_keeps_custom_remarks() -> None:
    out = apply_sea_service_defaults({"remarks": "Mutual agreement"})
    assert out["remarks"] == "Mutual agreement"


def test_main_imports_contract_duration_helper() -> None:
    """PUT /sea-service uses apply_contract_duration_to_payload from main."""
    import app.main as main_module

    assert callable(main_module.apply_contract_duration_to_payload)
