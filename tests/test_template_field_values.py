from __future__ import annotations

from app.main import _assign_doc_fields
from app.template_field_values import (
    clean_document_number_field,
    record_has_filled_template_data,
    sanitize_records_for_template_render,
)


def test_clean_document_number_rejects_type_label() -> None:
    record = {"certificate_type": "COP Ship's Cook", "certificate_code": "COP_COOK"}
    assert clean_document_number_field("COP Ship's Cook", record) == ""
    assert clean_document_number_field("ABC12345", record) == "ABC12345"


def test_assign_doc_fields_does_not_use_certificate_code() -> None:
    context: dict = {
        "certificates": [
            {
                "certificate_type": "Radar Observer",
                "certificate_code": "RADAR",
                "certificate_number": None,
            }
        ],
        "documents": [],
    }
    _assign_doc_fields(context, "radar", cert_terms=["radar"])
    assert context["radar_document_number"] == ""


def test_record_has_filled_template_data_rejects_empty_canonical_slot() -> None:
    row = {
        "certificate_id": 1,
        "certificate_code": "COC",
        "certificate_type": "COC",
        "certificate_name_raw": "END_COC",
        "certificate_number": None,
        "date_issued": None,
        "expiry_date": None,
    }
    assert record_has_filled_template_data(row) is False


def test_record_has_filled_template_data_keeps_number_or_dates() -> None:
    assert record_has_filled_template_data({"certificate_number": "123/2024"}) is True
    assert record_has_filled_template_data({"date_issued": "01-01-2020"}) is True
    assert record_has_filled_template_data({"is_present": True}) is True


def test_sanitize_filters_empty_rows_from_template_lists() -> None:
    context = {
        "certificates": [
            {"certificate_type": "COC", "certificate_code": "COC", "certificate_name_raw": "COC"},
            {"certificate_type": "Radar", "certificate_number": "01176/2024"},
        ]
    }
    sanitize_records_for_template_render(context)
    assert len(context["certificates"]) == 1
    assert context["certificates"][0]["certificate_number"] == "01176/2024"
