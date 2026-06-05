from __future__ import annotations

from pathlib import Path

import pytest

from parser.docx_parser import DocxParser

KUCHYNSKY_DOCX = Path(
    r"C:\Users\berni\Downloads\MST Kuchynsky OVERSEAS Application Form Eff. 04 Feb, 2020 (11).docx"
)


@pytest.mark.skipif(not KUCHYNSKY_DOCX.is_file(), reason="Sample overseas DOCX not on disk")
def test_overseas_kuchynsky_enriches_profile_and_family() -> None:
    result = DocxParser().parse(KUCHYNSKY_DOCX)
    personal = result["personal_data"]

    latin = personal.get("latin_full_name") or ""
    native = personal.get("native_full_name") or ""
    assert latin.startswith("Kuchynsky") and latin.endswith(" Oleg")
    assert native.startswith("Kuchynsky") and native.endswith(" Oleg")
    assert personal.get("marital_status") == "Married"
    assert personal.get("country") == "Turkey"
    assert personal.get("region") == "Alanya"

    family = result.get("family_contacts") or []
    assert len(family) >= 1
    spouse = family[0]
    assert spouse.get("full_name") == "Kuchynska Zlata"
    assert spouse.get("relationship_to_candidate") == "Spouse"
    assert spouse.get("phone")


def test_enrich_overseas_personal_unit() -> None:
    parser = DocxParser()
    personal = {
        "surname": "Test",
        "first_name": "Ivan",
        "middle_name": "Ivan",
        "permanent_address": "1 Main St, Odessa, Ukraine",
        "spouse_name": "Testova Maria",
    }
    parser._enrich_overseas_personal(personal)
    assert personal["latin_full_name"] == "Test Ivan"
    assert personal["marital_status"] == "Married"
    assert personal["country"] == "Ukraine"
    assert personal["region"] == "Odessa"

    family = parser._derive_family_contacts_overseas(personal)
    assert family[0]["full_name"] == "Testova Maria"
