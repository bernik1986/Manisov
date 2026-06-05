from __future__ import annotations

from app.scan_slot_codes import resolve_certificate_slot_code, resolve_document_slot_code
from models.schema import Certificate, Document


def test_document_slot_code_from_document_code():
    row = Document(document_type="Travel Passport", document_category="TP")
    assert resolve_document_slot_code(row) == "TP"


def test_certificate_slot_code_prefers_display_code():
    row = Certificate(
        certificate_name_raw="AFF",
        certificate_code="AFF",
        certificate_type="Advanced fire fighting",
    )
    assert resolve_certificate_slot_code(row) == "AFF"


def test_certificate_slot_code_diploma_slot():
    row = Certificate(
        certificate_name_raw="COVID",
        certificate_code="Covid Certificate",
        certificate_type="Covid Certificate",
    )
    assert resolve_certificate_slot_code(row) == "Covid Certificate"
