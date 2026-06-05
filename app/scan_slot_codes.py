"""Resolve table «Код» values for scan filenames from relation rows."""

from __future__ import annotations

import re

from models.schema import Certificate, Document, FlagDocument

from app.canonical_certificates import (
    ALL_CANONICAL_CERTIFICATE_SPECS,
    parse_code_type,
)
from app.canonical_diplomas import ALL_CANONICAL_DIPLOMA_SPECS
from app.canonical_documents import CANONICAL_DOCUMENT_SPECS
from app.canonical_medical import CANONICAL_MEDICAL_SPECS

_CERT_SLOT_IDS: frozenset[str] = frozenset(
    str(s["code"])
    for specs in (
        ALL_CANONICAL_DIPLOMA_SPECS,
        CANONICAL_MEDICAL_SPECS,
        ALL_CANONICAL_CERTIFICATE_SPECS,
    )
    for s in specs
)

_DOC_SLOT_CODES: frozenset[str] = frozenset(str(s["code"]) for s in CANONICAL_DOCUMENT_SPECS)

_DISPLAY_CODE_BY_SLOT: dict[str, str] = {}
for specs in (
    ALL_CANONICAL_DIPLOMA_SPECS,
    CANONICAL_MEDICAL_SPECS,
    ALL_CANONICAL_CERTIFICATE_SPECS,
):
    for spec in specs:
        slot_id = str(spec["code"])
        display = str(spec.get("display_code") or spec.get("certificate_type") or slot_id).strip()
        _DISPLAY_CODE_BY_SLOT[slot_id] = display


def _normalize_slot_token(value: str) -> str:
    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "", str(value or "").strip())
    return re.sub(r"\s+", " ", cleaned).strip()


def _code_from_label_line(label: str) -> str:
    text = _normalize_slot_token(label)
    if not text:
        return ""
    left, _ = parse_code_type(text)
    return _normalize_slot_token(left or text)


def resolve_document_slot_code(row: Document) -> str:
    for field in ("document_category", "document_name_raw"):
        value = _normalize_slot_token(getattr(row, field, None) or "")
        if value:
            if value in _DOC_SLOT_CODES:
                return value
            return value
    return _code_from_label_line(row.document_type or "") or "DOC"


def resolve_certificate_slot_code(row: Certificate) -> str:
    slot_raw = _normalize_slot_token(row.certificate_name_raw or "")
    if slot_raw in _CERT_SLOT_IDS:
        display = _DISPLAY_CODE_BY_SLOT.get(slot_raw, "")
        if display:
            return display
        return slot_raw

    code_field = _normalize_slot_token(row.certificate_code or "")
    if code_field:
        short = _code_from_label_line(code_field)
        if short:
            return short
        if len(code_field) <= 24:
            return code_field

    dtype = _normalize_slot_token(row.certificate_type or "")
    if dtype:
        short = _code_from_label_line(dtype)
        if short:
            return short
    return "CERT"


def resolve_flag_document_slot_code(row: FlagDocument) -> str:
    doc_type = _normalize_slot_token(row.flag_document_type or "")
    if doc_type:
        token = re.sub(r"[^A-Za-z0-9]+", "", doc_type)[:12]
        if token:
            return token.upper()
    country = _normalize_slot_token(row.flag_country or "")
    if country:
        token = re.sub(r"[^A-Za-z0-9]+", "", country)[:8]
        if token:
            return token.upper()
    return "FLAG"
