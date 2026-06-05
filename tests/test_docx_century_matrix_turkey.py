from __future__ import annotations

from pathlib import Path

import pytest

from parser.docx_parser import DocxParser

TESTS_DIR = Path(__file__).resolve().parent
CO_TURKEY_05A = TESTS_DIR / "CO Turkey CR-RT 05A OCTOBER - Seamen's Application and Interview Record 2.docx"


@pytest.mark.skipif(not CO_TURKEY_05A.is_file(), reason="fixture docx not present")
def test_century_co_turkey_matrix_sea_totals_from_bii_table() -> None:
    result = DocxParser().parse(CO_TURKEY_05A)
    pd = result["personal_data"]
    assert pd.get("father_name")
    assert pd.get("mother_name")
    assert pd.get("total_sea_service_in_rank") == "4 years"
    assert "8" in (pd.get("total_sea_service") or "")
    assert "8" in (pd.get("total_years_of_sea_service") or "")
    assert pd.get("years_in_this_type_of_vessel")
    assert pd.get("years_as_watch_officer")
