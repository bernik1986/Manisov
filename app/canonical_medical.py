"""Canonical medical document slots (stored as Certificate rows)."""

from __future__ import annotations

from typing import Any

from app.template_field_values import clean_document_number_field
from models.schema import Certificate

from app.canonical_diplomas import (
    _cert_text,
    _cert_value,
    _diploma_display_label,
    find_certificate_for_spec,
    order_specs_for_response,
)

MEDICAL_GROUP = "Medical Document"

CANONICAL_MEDICAL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "code": "COVID",
        "certificate_type": "Covid Certificate",
        "certificate_group": MEDICAL_GROUP,
        "match_terms": (
            "covid certificate",
            "covid-19",
            "covid 19",
            "covid vaccination",
            "coronavirus",
            "vaccination covid",
        ),
        "placeholder_prefix": "covid_certificate",
        "legacy_prefixes": (),
    },
    {
        "code": "MED_EXAM",
        "certificate_type": "Medical Examination",
        "certificate_group": MEDICAL_GROUP,
        "match_terms": (
            "medical examination",
            "medical exam",
            "seafarer medical",
            "medical fitness",
            "ilo medical",
            "medical certificate",
            "medical report",
        ),
        "placeholder_prefix": "medical_examination",
        "legacy_prefixes": ("medical_fitness",),
    },
    {
        "code": "HEP_B",
        "certificate_type": "Hepatitis vaccination",
        "certificate_group": MEDICAL_GROUP,
        "match_terms": (
            "hepatitis vaccination",
            "hepatitis vaccine",
            "hepatitis b",
            "hep b",
            "hepatitis",
        ),
        "placeholder_prefix": "hepatitis_vaccination",
        "legacy_prefixes": (),
    },
)

ALL_MEDICAL_SLOT_CODES: frozenset[str] = frozenset(str(s["code"]) for s in CANONICAL_MEDICAL_SPECS)

_NON_MEDICAL_CERTIFICATE_GROUPS: frozenset[str] = frozenset(
    {
        "Conventional Certificate",
        "ECDIS Certificate",
        "Company Certificate",
        "BWTS Certificate",
        "Diploma",
        "Tanker Diploma",
    }
)

_STCW_MEDICAL_TRAINING_TERMS: frozenset[str] = frozenset(
    {
        "medical first aid",
        "medical care",
        "craft and rb medical",
        "proficiency in medical",
    }
)


def medical_matches_spec(cert: Certificate | dict[str, Any], spec: dict[str, Any]) -> bool:
    code = str(spec.get("code") or "")
    slot_raw = str(_cert_value(cert, "certificate_name_raw") or "").strip()
    category = str(_cert_value(cert, "certificate_code") or "").strip()
    group = str(_cert_value(cert, "certificate_group") or "").strip()
    if group in _NON_MEDICAL_CERTIFICATE_GROUPS:
        return False
    dtype = str(_cert_value(cert, "certificate_type") or "").strip().lower()
    canonical = str(spec.get("certificate_type") or "").strip().lower()
    text = _cert_text(cert)

    if any(term in text for term in _STCW_MEDICAL_TRAINING_TERMS):
        return False

    if slot_raw and slot_raw == code:
        return True
    if category and category == code:
        return True
    if category and category == spec.get("certificate_type"):
        return True
    if group and group == spec.get("certificate_group") and dtype == canonical:
        return True
    if dtype and dtype == canonical:
        return True

    if code == "MED_EXAM":
        if "first aid" in text or "medical care" in text:
            return False
        return any(term in text for term in spec.get("match_terms") or ())

    if code == "HEP_B":
        if "covid" in text:
            return False
        return any(term in text for term in spec.get("match_terms") or ())

    if code == "COVID":
        return any(term in text for term in spec.get("match_terms") or ())

    return any(term in text for term in spec.get("match_terms") or ())


def is_canonical_medical_record(cert: Certificate | dict[str, Any]) -> bool:
    slot = str(_cert_value(cert, "certificate_name_raw") or "").strip()
    if slot in ALL_MEDICAL_SLOT_CODES:
        return True
    group = str(_cert_value(cert, "certificate_group") or "").strip()
    if group == MEDICAL_GROUP:
        return True
    if group in _NON_MEDICAL_CERTIFICATE_GROUPS:
        return False
    return any(medical_matches_spec(cert, spec) for spec in CANONICAL_MEDICAL_SPECS)


def ensure_canonical_medical(session, candidate_id: int) -> bool:
    existing = session.query(Certificate).filter(Certificate.candidate_id == candidate_id).all()
    claimed: set[int] = set()
    changed = False

    for spec in CANONICAL_MEDICAL_SPECS:
        match = find_certificate_for_spec(
            existing,
            spec,
            excluded_ids=claimed,
            match_fn=medical_matches_spec,
        )
        if match is not None:
            cert_id = _cert_value(match, "certificate_id")
            if cert_id is not None:
                claimed.add(int(cert_id))
            if isinstance(match, Certificate):
                label = _diploma_display_label(spec)
                if (match.certificate_group or "") != spec["certificate_group"]:
                    match.certificate_group = spec["certificate_group"]
                    changed = True
                if (match.certificate_name_raw or "") != spec["code"]:
                    match.certificate_name_raw = spec["code"]
                    changed = True
                if (match.certificate_code or "") != label:
                    match.certificate_code = label
                    changed = True
                if (match.certificate_type or "") != spec["certificate_type"]:
                    match.certificate_type = spec["certificate_type"]
                    changed = True
            continue

        label = _diploma_display_label(spec)
        session.add(
            Certificate(
                candidate_id=candidate_id,
                certificate_group=spec["certificate_group"],
                certificate_code=label,
                certificate_type=spec["certificate_type"],
                certificate_name_raw=spec["code"],
            )
        )
        changed = True

    if changed:
        session.commit()
    return changed


def order_medical_for_response(
    certificates: list[dict[str, Any]],
    *,
    session=None,
    candidate_id: int | None = None,
) -> list[dict[str, Any]]:
    return order_specs_for_response(
        certificates,
        CANONICAL_MEDICAL_SPECS,
        match_fn=medical_matches_spec,
        slot_code_key="medical_code",
        session=session,
        candidate_id=candidate_id,
    )


def apply_canonical_medical_placeholders(context: dict[str, Any]) -> None:
    combined = list(context.get("certificates") or [])
    for key in ("medical_documents",):
        for item in context.get(key) or []:
            if item not in combined:
                combined.append(item)

    claimed: set[int] = set()

    for spec in CANONICAL_MEDICAL_SPECS:
        cert_rec = find_certificate_for_spec(
            combined,
            spec,
            excluded_ids=claimed,
            match_fn=medical_matches_spec,
        )
        cert_id = _cert_value(cert_rec, "certificate_id")
        if cert_id is not None:
            claimed.add(int(cert_id))
        prefix = spec["placeholder_prefix"]
        cert_dict: dict[str, Any] | None = None
        if isinstance(cert_rec, dict):
            cert_dict = cert_rec
        elif isinstance(cert_rec, Certificate):
            from app.certificate_canonical_slots import cert_to_dict

            cert_dict = cert_to_dict(cert_rec)
        context.setdefault(
            f"{prefix}_certificate_number",
            clean_document_number_field(_cert_value(cert_rec, "certificate_number"), cert_dict),
        )
        context.setdefault(f"{prefix}_issue_date", _cert_value(cert_rec, "date_issued") or "")
        context.setdefault(f"{prefix}_expiry_date", _cert_value(cert_rec, "expiry_date") or "")
        context.setdefault(f"{prefix}_issuing_authority", _cert_value(cert_rec, "issuing_authority") or "")
        context.setdefault(f"{prefix}_country_of_issue", _cert_value(cert_rec, "country_of_issue") or "")
        for legacy_prefix in spec.get("legacy_prefixes") or ():
            context.setdefault(f"{legacy_prefix}_certificate_number", context.get(f"{prefix}_certificate_number") or "")
            context.setdefault(f"{legacy_prefix}_document_number", context.get(f"{prefix}_certificate_number") or "")
            context.setdefault(f"{legacy_prefix}_issue_date", context.get(f"{prefix}_issue_date") or "")
            context.setdefault(f"{legacy_prefix}_expiry_date", context.get(f"{prefix}_expiry_date") or "")
            context.setdefault(f"{legacy_prefix}_issuing_authority", context.get(f"{prefix}_issuing_authority") or "")


def canonical_medical_placeholder_tokens() -> list[str]:
    suffixes = ("certificate_number", "issue_date", "expiry_date", "issuing_authority", "country_of_issue")
    tokens: list[str] = []
    for spec in CANONICAL_MEDICAL_SPECS:
        prefix = spec["placeholder_prefix"]
        for suffix in suffixes:
            tokens.append(f"{{{{ {prefix}_{suffix} }}}}")
    return tokens
