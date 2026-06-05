"""Canonical document slots for candidate cards and docxtpl placeholders."""

from __future__ import annotations

from typing import Any

from app.template_field_values import clean_document_number_field
from models.schema import Document

# Keep document_type stable; match_terms map parsed / legacy rows to a slot.
CANONICAL_DOCUMENT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "code": "YF",
        "document_type": "Yellow Fever",
        "match_terms": ("yellow fever", "yf", "yellow fever vaccination"),
        "placeholder_prefix": "yf",
    },
    {
        "code": "TP Bio",
        "document_type": "Travel Passport (Ukraine)",
        "match_terms": (
            "tp bio",
            "travel passport (ukraine)",
            "travel passport ukraine",
            "ukrainian travel passport",
            "загран паспорт украин",
        ),
        "placeholder_prefix": "tp_bio",
    },
    {
        "code": "TP",
        "document_type": "Travel Passport",
        "match_terms": ("travel passport", "passport", "tp", "загран паспорт"),
        "placeholder_prefix": "tp",
    },
    {
        "code": "SB",
        "document_type": "Seaman's Book",
        "match_terms": ("seaman's book", "seaman book", "seafarer book", "sb"),
        "placeholder_prefix": "sb",
    },
    {
        "code": "SS",
        "document_type": "Sea Service Record",
        "match_terms": ("sea service record", "discharge book", "discharge", "послужн", "ss"),
        "placeholder_prefix": "ss",
    },
    {
        "code": "SID",
        "document_type": "Seafarer Identity Document",
        "match_terms": (
            "seafarer identity",
            "seaman identity",
            "seafarers identity",
            "sid",
            "удостоверение личности моряка",
        ),
        "placeholder_prefix": "sid",
    },
    {
        "code": "CP",
        "document_type": "Civil Passport",
        "match_terms": ("civil passport", "national passport", "гражданский паспорт", "cp"),
        "placeholder_prefix": "cp",
    },
    {
        "code": "ID code",
        "document_type": "Tax ID Code",
        "match_terms": ("tax id", "id code", "inn", "ид код", "инн"),
        "placeholder_prefix": "id_code",
    },
    {
        "code": "ID card",
        "document_type": "Biometric ID Card",
        "match_terms": ("biometric id", "biometric passport", "id card", "биометрическ"),
        "placeholder_prefix": "id_card",
    },
    {
        "code": "Residence",
        "document_type": "Residence Registration",
        "match_terms": ("residence", "residence registration", "прописк", "registration"),
        "placeholder_prefix": "residence",
    },
)

CANONICAL_DOCUMENT_TYPES: tuple[str, ...] = tuple(spec["document_type"] for spec in CANONICAL_DOCUMENT_SPECS)


def _document_text(doc: Document | dict[str, Any]) -> str:
    if isinstance(doc, Document):
        parts = [doc.document_type or "", doc.document_name_raw or "", doc.document_category or ""]
    else:
        parts = [
            str(doc.get("document_type") or ""),
            str(doc.get("document_name_raw") or ""),
            str(doc.get("document_category") or ""),
        ]
    return " ".join(parts).lower()


def document_matches_spec(doc: Document | dict[str, Any], spec: dict[str, Any]) -> bool:
    code = spec.get("code")
    dtype = str(_doc_value(doc, "document_type") or "").strip().lower()
    canonical = str(spec.get("document_type") or "").strip().lower()
    category = str(_doc_value(doc, "document_category") or "").strip()

    if category and category == code:
        return True
    if dtype and dtype == canonical:
        return True

    text = _document_text(doc)
    # "Travel Passport (Ukraine)" must map to TP Bio, not generic TP / Passport.
    if code == "TP" and ("ukraine" in dtype or category == "TP Bio"):
        return False
    if code == "TP Bio":
        return any(term in text for term in spec.get("match_terms") or ())

    return any(term in text for term in spec.get("match_terms") or ())


def _doc_value(doc: Document | dict[str, Any] | None, field: str) -> Any:
    if doc is None:
        return None
    if isinstance(doc, Document):
        return getattr(doc, field, None)
    return doc.get(field)


def find_document_for_spec(
    documents: list[Document | dict[str, Any]],
    spec: dict[str, Any],
    *,
    excluded_ids: set[int] | None = None,
) -> Document | dict[str, Any] | None:
    excluded = excluded_ids or set()
    for doc in documents:
        doc_id = doc.document_id if isinstance(doc, Document) else doc.get("document_id")
        if doc_id is not None and doc_id in excluded:
            continue
        if document_matches_spec(doc, spec):
            return doc
    return None


def ensure_canonical_documents(session, candidate_id: int) -> bool:
    """Insert empty rows for canonical document types missing on this candidate."""
    existing = session.query(Document).filter(Document.candidate_id == candidate_id).all()
    claimed: set[int] = set()
    added = False

    for spec in CANONICAL_DOCUMENT_SPECS:
        match = find_document_for_spec(existing, spec, excluded_ids=claimed)
        if match is not None:
            doc_id = match.document_id if isinstance(match, Document) else match.get("document_id")
            if doc_id is not None:
                claimed.add(int(doc_id))
            continue
        session.add(
            Document(
                candidate_id=candidate_id,
                document_category=spec["code"],
                document_type=spec["document_type"],
            )
        )
        added = True

    if added:
        session.commit()
    return added


def order_documents_for_response(
    documents: list[dict[str, Any]],
    *,
    session=None,
    candidate_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return documents in canonical order; extras appended at the end."""
    remaining = list(documents)
    ordered: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    created_any = False

    for spec in CANONICAL_DOCUMENT_SPECS:
        match_idx = None
        for idx, doc in enumerate(remaining):
            doc_id = doc.get("document_id")
            if doc_id is not None and doc_id in used_ids:
                continue
            if document_matches_spec(doc, spec):
                match_idx = idx
                break
        if match_idx is None:
            if session is not None and candidate_id is not None:
                row = Document(
                    candidate_id=candidate_id,
                    document_category=spec["code"],
                    document_type=spec["document_type"],
                )
                session.add(row)
                session.flush()
                doc = {
                    "document_id": row.document_id,
                    "candidate_id": row.candidate_id,
                    "document_category": row.document_category,
                    "document_type": row.document_type,
                    "document_name_raw": row.document_name_raw,
                    "document_number": row.document_number,
                    "issuing_authority": row.issuing_authority,
                    "place_of_issue": row.place_of_issue,
                    "date_of_issue": row.date_of_issue,
                    "date_of_expiry": row.date_of_expiry,
                    "validity_status": row.validity_status,
                    "unlimited_validity": row.unlimited_validity,
                    "country_of_issue": row.country_of_issue,
                    "remarks": row.remarks,
                    "scan_file": row.scan_file,
                    "verified": row.verified,
                    "created_at": row.created_at,
                    "document_code": spec["code"],
                }
                ordered.append(doc)
                used_ids.add(int(row.document_id))
                created_any = True
                continue
            ordered.append(
                {
                    "document_id": None,
                    "document_category": spec["code"],
                    "document_type": spec["document_type"],
                    "document_number": None,
                    "issuing_authority": None,
                    "date_of_issue": None,
                    "date_of_expiry": None,
                    "place_of_issue": None,
                    "is_canonical_placeholder": True,
                }
            )
            continue
        doc = {**remaining.pop(match_idx)}
        doc["document_code"] = spec["code"]
        if doc.get("document_id") is not None:
            used_ids.add(int(doc["document_id"]))
        ordered.append(doc)

    if created_any and session is not None:
        session.commit()

    for doc in remaining:
        if doc.get("document_id") is not None and doc["document_id"] in used_ids:
            continue
        ordered.append(doc)
    return ordered


def apply_canonical_document_placeholders(context: dict[str, Any]) -> None:
    documents = context.get("documents") or []
    claimed: set[int] = set()

    for spec in CANONICAL_DOCUMENT_SPECS:
        doc_rec = find_document_for_spec(documents, spec, excluded_ids=claimed)
        doc_id = _doc_value(doc_rec, "document_id")
        if doc_id is not None:
            claimed.add(int(doc_id))

        prefix = spec["placeholder_prefix"]
        doc_dict = doc_rec if isinstance(doc_rec, dict) else None
        context.setdefault(
            f"{prefix}_document_number",
            clean_document_number_field(_doc_value(doc_rec, "document_number"), doc_dict),
        )
        context.setdefault(f"{prefix}_issue_date", _doc_value(doc_rec, "date_of_issue") or "")
        context.setdefault(f"{prefix}_expiry_date", _doc_value(doc_rec, "date_of_expiry") or "")
        context.setdefault(f"{prefix}_issuing_authority", _doc_value(doc_rec, "issuing_authority") or "")
        context.setdefault(
            f"{prefix}_place_of_issue",
            _doc_value(doc_rec, "place_of_issue") or _doc_value(doc_rec, "country_of_issue") or "",
        )

    # Legacy template aliases
    tp_doc = find_document_for_spec(documents, CANONICAL_DOCUMENT_SPECS[2])
    sb_doc = find_document_for_spec(documents, CANONICAL_DOCUMENT_SPECS[3])
    yf_doc = find_document_for_spec(documents, CANONICAL_DOCUMENT_SPECS[0])
    context.setdefault("passport_number", _doc_value(tp_doc, "document_number") or context.get("passport_number") or "")
    context.setdefault("passport_issue_date", _doc_value(tp_doc, "date_of_issue") or context.get("passport_issue_date") or "")
    context.setdefault("passport_expiry_date", _doc_value(tp_doc, "date_of_expiry") or context.get("passport_expiry_date") or "")
    context.setdefault(
        "passport_place_of_issue",
        _doc_value(tp_doc, "place_of_issue") or context.get("passport_place_of_issue") or "",
    )
    context.setdefault("passport_issue_place", context.get("passport_place_of_issue") or "")

    context.setdefault("seaman_book_number", _doc_value(sb_doc, "document_number") or context.get("seaman_book_number") or "")
    context.setdefault("seaman_book_issue_date", _doc_value(sb_doc, "date_of_issue") or "")
    context.setdefault("seaman_book_expiry_date", _doc_value(sb_doc, "date_of_expiry") or "")
    context.setdefault(
        "seaman_book_issue_place",
        _doc_value(sb_doc, "place_of_issue") or context.get("passport_place_of_issue") or "",
    )

    context.setdefault("yellow_fever_issue_date", _doc_value(yf_doc, "date_of_issue") or context.get("yellow_fever_issue_date") or "")
    context.setdefault("yellow_fever_expiry_date", _doc_value(yf_doc, "date_of_expiry") or context.get("yellow_fever_expiry_date") or "")
    context.setdefault(
        "yellow_fever_issue_place",
        _doc_value(yf_doc, "place_of_issue") or context.get("passport_place_of_issue") or "",
    )


def canonical_document_placeholder_tokens() -> list[str]:
    tokens: list[str] = []
    for spec in CANONICAL_DOCUMENT_SPECS:
        prefix = spec["placeholder_prefix"]
        for suffix in ("document_number", "issue_date", "expiry_date", "issuing_authority", "place_of_issue"):
            tokens.append(f"{{{{ {prefix}_{suffix} }}}}")
    return tokens
