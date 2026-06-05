from __future__ import annotations

from app.sea_service_row_normalize import (
    normalize_sea_service_row,
    sanitize_discharge_remarks,
    split_engine_and_power,
)


def test_split_kw_from_main_engine() -> None:
    eng, pwr = split_engine_and_power("Mitsubishi 6UEC45LSE-1 6840KW", None)
    assert eng == "Mitsubishi 6UEC45LSE-1"
    assert pwr == "6840KW"


def test_sanitize_crane_to_eoc() -> None:
    assert sanitize_discharge_remarks("4 Crane") == "EOC"
    assert sanitize_discharge_remarks("Malta") == "EOC"
    assert sanitize_discharge_remarks("EOC") == "EOC"
    assert sanitize_discharge_remarks("Transfer") == "Transfer"


def test_normalize_moves_flag_from_remarks() -> None:
    row = normalize_sea_service_row(
        {
            "remarks": "Liberia",
            "main_engine": "MAN B&W 7260KW",
        }
    )
    assert row["flag"] == "Liberia"
    assert row["remarks"] == "EOC"
    assert row["engine_power"] == "7260KW"
    assert "KW" not in (row.get("main_engine") or "").upper()
