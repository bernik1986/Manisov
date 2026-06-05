"""Sanitize values passed into docxtpl placeholders (empty stays empty)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_LABEL_KEYS = (
    "certificate_type",
    "certificate_code",
    "certificate_name_raw",
    "certificate_group",
    "document_type",
    "document_category",
    "document_name_raw",
    "display_type",
    "display_code",
)


_LIST_KEYS = (
    "certificates",
    "conventional_certificates",
    "diplomas",
    "tanker_diplomas",
    "medical_documents",
    "ecdis_certificates",
    "company_certificates",
    "bwts_certificates",
    "documents",
    "flag_documents",
)

_METADATA_KEYS = frozenset(
    {
        *_LABEL_KEYS,
        "certificate_id",
        "document_id",
        "flag_document_id",
        "candidate_id",
        "created_at",
        "display_code",
        "display_type",
        "diploma_code",
        "slot_code",
        "document_code",
        "is_canonical_placeholder",
        "is_present",
        "verified",
        "validity_status",
        "unlimited_validity",
    }
)

_USER_VALUE_KEYS = (
    "certificate_number",
    "document_number",
    "date_issued",
    "expiry_date",
    "date_of_issue",
    "date_of_expiry",
    "issuing_authority",
    "country_of_issue",
    "place_of_issue",
    "scan_file",
    "remarks",
)


def record_has_filled_template_data(record: dict[str, Any]) -> bool:
    """True when the seafarer card has real data for this row (not an empty canonical slot)."""
    if record.get("is_canonical_placeholder"):
        return False
    if record.get("is_present") is True:
        return True

    number = clean_document_number_field(
        record.get("certificate_number") or record.get("document_number"),
        record,
    )
    if number:
        return True

    for key in _USER_VALUE_KEYS:
        if key in ("certificate_number", "document_number"):
            continue
        if str(record.get(key) or "").strip():
            return True

    for key, value in record.items():
        if key in _METADATA_KEYS:
            continue
        if value is None or value is False:
            continue
        if str(value).strip():
            return True
    return False


def prepare_docx_template_context(context: dict[str, Any], template_path: Path) -> dict[str, Any]:
    """Patch DOCX Jinja if needed, then keep only filled rows for template loops."""
    from app.docx_template_jinja import patch_docx_file

    try:
        patch_docx_file(template_path)
    except Exception:
        pass
    ctx = dict(context)
    sanitize_records_for_template_render(ctx)
    return ctx


def sanitize_records_for_template_render(context: dict[str, Any]) -> None:
    """Prepare list rows for Jinja loops: clean numbers and drop empty canonical slots."""
    for key in _LIST_KEYS:
        rows = context.get(key)
        if not isinstance(rows, list):
            continue
        sanitized: list[Any] = []
        for row in rows:
            if not isinstance(row, dict):
                sanitized.append(row)
                continue
            item = dict(row)
            item["certificate_number"] = clean_document_number_field(
                item.get("certificate_number"),
                item,
            )
            item["document_number"] = clean_document_number_field(
                item.get("document_number"),
                item,
            )
            if record_has_filled_template_data(item):
                sanitized.append(item)
        context[key] = sanitized


def clean_document_number_field(value: Any, record: dict[str, Any] | None = None) -> str:
    """
    Return document/certificate number for templates.
    Never substitute slot code or type label when the real number is missing.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if record is None:
        return text
    low = text.lower()
    for key in _LABEL_KEYS:
        label = str(record.get(key) or "").strip()
        if label and low == label.lower():
            return ""
    return text
