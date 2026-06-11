from __future__ import annotations

from zipfile import ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from app.docx_template_jinja import strip_email_hyperlinks_from_docx
from app.main import _assign_doc_fields
from app.template_field_values import (
    clean_document_number_field,
    sanitize_email_values_for_template_render,
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


def test_sanitize_email_values_keeps_single_plain_email() -> None:
    context = {
        "email": "mailto:bernik1986@gmail.com",
        "family_contacts": [{"email": "mailto:second@example.com second@example.com"}],
    }

    sanitize_email_values_for_template_render(context)

    assert context["email"] == "bernik1986@gmail.com"
    assert context["family_contacts"][0]["email"] == "second@example.com"


def test_strip_email_hyperlinks_from_docx_keeps_plain_text(tmp_path) -> None:
    path = tmp_path / "email_link.docx"
    doc = Document()
    paragraph = doc.add_paragraph("Email: ")
    rid = doc.part.relate_to("mailto:bernik1986@gmail.com", RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "mailto:bernik1986@gmail.com"
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    doc.save(path)

    strip_email_hyperlinks_from_docx(path)

    with ZipFile(path) as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8")
        rels_xml = zf.read("word/_rels/document.xml.rels").decode("utf-8")

    assert "bernik1986@gmail.com" in document_xml
    assert "mailto:" not in document_xml
    assert "<w:hyperlink" not in document_xml
    assert "mailto:" not in rels_xml
