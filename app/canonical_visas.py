"""Canonical visa slots (stored as Document rows) for candidate cards and docxtpl."""

from __future__ import annotations

from typing import Any

from app.canonical_documents import _doc_value
from app.template_field_values import clean_document_number_field
from models.schema import Document

# code == document_type == display name; placeholder_prefix for Word templates.
CANONICAL_VISA_SPECS: tuple[dict[str, Any], ...] = (
    {
        "code": "Visa USA",
        "document_type": "Visa USA",
        "match_terms": ("usa visa", "us visa", "american visa", "visa usa"),
        "placeholder_prefix": "usa_visa",
    },
    {
        "code": "Australian Maritime Crew Visa",
        "document_type": "Australian Maritime Crew Visa",
        "match_terms": (
            "australian maritime crew visa",
            "maritime crew visa (australia)",
            "maritime crew visa",
            "mcv",
            "australia crew visa",
            "crew visa australia",
        ),
        "placeholder_prefix": "mcv",
    },
    {
        "code": "Visa Canada",
        "document_type": "Visa Canada",
        "match_terms": ("visa canada", "canada visa", "canadian visa"),
        "placeholder_prefix": "visa_canada",
    },
    {
        "code": "Visa Schengen",
        "document_type": "Visa Schengen",
        "match_terms": ("visa schengen", "schengen visa"),
        "placeholder_prefix": "visa_schengen",
    },
    {
        "code": "Visa China",
        "document_type": "Visa China",
        "match_terms": ("visa china", "china visa", "chinese visa"),
        "placeholder_prefix": "visa_china",
    },
    {
        "code": "Visa Brazil",
        "document_type": "Visa Brazil",
        "match_terms": ("visa brazil", "brazil visa", "brazilian visa"),
        "placeholder_prefix": "visa_brazil",
    },
    {
        "code": "Visa Fujairah",
        "document_type": "Visa Fujairah",
        "match_terms": ("visa fujairah", "fujairah visa"),
        "placeholder_prefix": "visa_fujairah",
    },
    {
        "code": "Visa Taiwan",
        "document_type": "Visa Taiwan",
        "match_terms": ("visa taiwan", "taiwan visa"),
        "placeholder_prefix": "visa_taiwan",
    },
    {
        "code": "Visa Indonesia",
        "document_type": "Visa Indonesia",
        "match_terms": ("visa indonesia", "indonesia visa", "indonesian visa"),
        "placeholder_prefix": "visa_indonesia",
    },
    {
        "code": "Australian Transit Visa",
        "document_type": "Australian Transit Visa",
        "match_terms": ("australian transit visa", "transit visa australia", "australia transit visa"),
        "placeholder_prefix": "visa_australian_transit",
    },
    {
        "code": "Visa India",
        "document_type": "Visa India",
        "match_terms": ("visa india", "india visa", "indian visa"),
        "placeholder_prefix": "visa_india",
    },
    {
        "code": "Visa Thailand",
        "document_type": "Visa Thailand",
        "match_terms": ("visa thailand", "thailand visa", "thai visa"),
        "placeholder_prefix": "visa_thailand",
    },
)

CANONICAL_VISA_CODES: frozenset[str] = frozenset(spec["code"] for spec in CANONICAL_VISA_SPECS)

# Legacy document_category values from the old Documents section.
_LEGACY_VISA_CATEGORIES: dict[str, str] = {
    "MCV": "Australian Maritime Crew Visa",
    "Visa USA": "Visa USA",
}


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


def visa_matches_spec(doc: Document | dict[str, Any], spec: dict[str, Any]) -> bool:
    code = spec.get("code")
    dtype = str(_doc_value(doc, "document_type") or "").strip().lower()
    canonical = str(spec.get("document_type") or "").strip().lower()
    category = str(_doc_value(doc, "document_category") or "").strip()

    if category and category == code:
        return True
    if category and _LEGACY_VISA_CATEGORIES.get(category) == code:
        return True
    if dtype and dtype == canonical:
        return True
    # Legacy parser rows (e.g. document_type "USA Visa").
    text = _document_text(doc)
    return any(term in text for term in spec.get("match_terms") or ())


def _document_id(doc: Document | dict[str, Any]) -> int | None:
    raw = doc.document_id if isinstance(doc, Document) else doc.get("document_id")
    return int(raw) if raw is not None else None


def visa_row_has_data(doc: Document | dict[str, Any]) -> bool:
    return bool(
        str(_doc_value(doc, "document_number") or "").strip()
        or _doc_value(doc, "date_of_issue")
        or _doc_value(doc, "date_of_expiry")
        or str(_doc_value(doc, "scan_file") or "").strip()
        or str(_doc_value(doc, "place_of_issue") or "").strip()
        or str(_doc_value(doc, "issuing_authority") or "").strip()
    )


def normalize_visa_row(doc: Document | dict[str, Any], spec: dict[str, Any]) -> None:
    if isinstance(doc, Document):
        doc.document_category = spec["code"]
        doc.document_type = spec["document_type"]
    else:
        doc["document_category"] = spec["code"]
        doc["document_type"] = spec["document_type"]
        doc["visa_code"] = spec["code"]


def pick_primary_visa_row(matches: list[Document | dict[str, Any]]) -> Document | dict[str, Any]:
    with_data = [row for row in matches if visa_row_has_data(row)]
    pool = with_data or matches
    return min(pool, key=lambda row: _document_id(row) or 0)


def find_all_visas_for_spec(
    documents: list[Document | dict[str, Any]],
    spec: dict[str, Any],
    *,
    excluded_ids: set[int] | None = None,
) -> list[Document | dict[str, Any]]:
    excluded = excluded_ids or set()
    found: list[Document | dict[str, Any]] = []
    for doc in documents:
        doc_id = _document_id(doc)
        if doc_id is not None and doc_id in excluded:
            continue
        if visa_matches_spec(doc, spec):
            found.append(doc)
    return found


def find_visa_for_spec(
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
        if visa_matches_spec(doc, spec):
            return doc
    return None


def document_is_visa(doc: Document | dict[str, Any]) -> bool:
    if any(visa_matches_spec(doc, spec) for spec in CANONICAL_VISA_SPECS):
        return True
    category = str(_doc_value(doc, "document_category") or "").strip()
    if category in CANONICAL_VISA_CODES:
        return True
    dtype = str(_doc_value(doc, "document_type") or "").strip()
    if category and category == dtype and "visa" in dtype.lower():
        return True
    return False


def visa_matches_any_canonical_spec(doc: Document | dict[str, Any]) -> bool:
    return any(visa_matches_spec(doc, spec) for spec in CANONICAL_VISA_SPECS)


def deduplicate_canonical_visa_rows(session, candidate_id: int) -> bool:
    """Merge duplicate DB rows for the same visa slot; drop empty duplicates."""
    existing = session.query(Document).filter(Document.candidate_id == candidate_id).all()
    changed = False
    claimed: set[int] = set()

    for spec in CANONICAL_VISA_SPECS:
        matches = find_all_visas_for_spec(existing, spec, excluded_ids=claimed)
        if not matches:
            continue
        primary = pick_primary_visa_row(matches)
        primary_id = _document_id(primary)
        if primary_id is not None:
            claimed.add(primary_id)
        if isinstance(primary, Document):
            if (
                primary.document_category != spec["code"]
                or primary.document_type != spec["document_type"]
            ):
                primary.document_category = spec["code"]
                primary.document_type = spec["document_type"]
                changed = True
        for extra in matches:
            extra_id = _document_id(extra)
            if extra_id is None or extra_id == primary_id:
                continue
            if isinstance(extra, Document):
                session.delete(extra)
            changed = True

    if changed:
        session.commit()
    return changed


def partition_documents_and_visas(
    documents: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visas: list[dict[str, Any]] = []
    non_visas: list[dict[str, Any]] = []
    for doc in documents:
        if document_is_visa(doc):
            visas.append(doc)
        else:
            non_visas.append(doc)
    return non_visas, visas


def ensure_canonical_visas(session, candidate_id: int) -> bool:
    existing = session.query(Document).filter(Document.candidate_id == candidate_id).all()
    claimed: set[int] = set()
    added = False

    for spec in CANONICAL_VISA_SPECS:
        matches = find_all_visas_for_spec(existing, spec, excluded_ids=claimed)
        if matches:
            primary = pick_primary_visa_row(matches)
            doc_id = _document_id(primary)
            if doc_id is not None:
                claimed.add(doc_id)
            if isinstance(primary, Document):
                if (
                    primary.document_category != spec["code"]
                    or primary.document_type != spec["document_type"]
                ):
                    primary.document_category = spec["code"]
                    primary.document_type = spec["document_type"]
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
    deduplicate_canonical_visa_rows(session, candidate_id)
    return added


def order_visas_for_response(
    documents: list[dict[str, Any]],
    *,
    session=None,
    candidate_id: int | None = None,
) -> list[dict[str, Any]]:
    remaining = list(documents)
    ordered: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    created_any = False

    for spec in CANONICAL_VISA_SPECS:
        matches = [
            doc
            for doc in remaining
            if (_document_id(doc) is None or _document_id(doc) not in used_ids) and visa_matches_spec(doc, spec)
        ]
        if not matches:
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
                    "visa_code": spec["code"],
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
                    "visa_code": spec["code"],
                    "is_canonical_placeholder": True,
                }
            )
            continue
        primary = pick_primary_visa_row(matches)
        match_ids = {_document_id(row) for row in matches if _document_id(row) is not None}
        remaining = [doc for doc in remaining if _document_id(doc) not in match_ids]
        doc = {**primary, "visa_code": spec["code"]}
        if doc.get("document_id") is not None:
            used_ids.add(int(doc["document_id"]))
        ordered.append(doc)

    if created_any and session is not None:
        session.commit()

    for doc in remaining:
        doc_id = _document_id(doc)
        if doc_id is not None and doc_id in used_ids:
            continue
        if visa_matches_any_canonical_spec(doc):
            continue
        code = str(doc.get("document_category") or doc.get("document_type") or "").strip()
        if "visa" not in code.lower() and "visa" not in _document_text(doc):
            continue
        doc = {**doc, "visa_code": code or None}
        if doc_id is not None:
            used_ids.add(doc_id)
        ordered.append(doc)
    return ordered


def apply_canonical_visa_placeholders(context: dict[str, Any]) -> None:
    documents = context.get("documents") or []
    visas = context.get("visas") or []
    pool = list(visas) if visas else [doc for doc in documents if document_is_visa(doc)]
    claimed: set[int] = set()

    for spec in CANONICAL_VISA_SPECS:
        doc_rec = find_visa_for_spec(pool, spec, excluded_ids=claimed)
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
        context.setdefault(f"{prefix}_visa_code", spec["code"])
        context.setdefault(f"{prefix}_visa_name", spec["document_type"])

    usa_doc = find_visa_for_spec(pool, CANONICAL_VISA_SPECS[0], excluded_ids=set())
    context.setdefault(
        "usa_visa_number",
        clean_document_number_field(_doc_value(usa_doc, "document_number"), usa_doc if isinstance(usa_doc, dict) else None)
        or context.get("usa_visa_number")
        or "",
    )
    context.setdefault("usa_visa_issue_date", _doc_value(usa_doc, "date_of_issue") or context.get("usa_visa_issue_date") or "")
    context.setdefault("usa_visa_expiry_date", _doc_value(usa_doc, "date_of_expiry") or context.get("usa_visa_expiry_date") or "")
    context.setdefault(
        "usa_visa_place_of_issue",
        _doc_value(usa_doc, "place_of_issue") or context.get("usa_visa_place_of_issue") or "",
    )
    context.setdefault("usa_visa_issue_place", context.get("usa_visa_place_of_issue") or "")


def canonical_visa_placeholder_tokens() -> list[str]:
    tokens: list[str] = []
    for spec in CANONICAL_VISA_SPECS:
        prefix = spec["placeholder_prefix"]
        for suffix in (
            "document_number",
            "issue_date",
            "expiry_date",
            "issuing_authority",
            "place_of_issue",
            "visa_code",
            "visa_name",
        ):
            tokens.append(f"{{{{ {prefix}_{suffix} }}}}")
    return tokens
