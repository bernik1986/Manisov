"""Shared helpers for canonical certificate / diploma slots."""

from __future__ import annotations

from typing import Any, Callable

from app.template_field_values import clean_document_number_field
from models.schema import Certificate


def cert_text(cert: Certificate | dict[str, Any]) -> str:
    if isinstance(cert, Certificate):
        parts = [
            cert.certificate_type or "",
            cert.certificate_name_raw or "",
            cert.certificate_group or "",
            cert.certificate_code or "",
        ]
    else:
        parts = [
            str(cert.get("certificate_type") or ""),
            str(cert.get("certificate_name_raw") or ""),
            str(cert.get("certificate_group") or ""),
            str(cert.get("certificate_code") or ""),
        ]
    return " ".join(parts).lower()


def cert_value(cert: Certificate | dict[str, Any] | None, field: str) -> Any:
    if cert is None:
        return None
    if isinstance(cert, Certificate):
        return getattr(cert, field, None)
    return cert.get(field)


def storage_fields_from_spec(spec: dict[str, Any]) -> dict[str, str]:
    slot_id = str(spec.get("code") or "")
    display_code = str(spec.get("display_code") or slot_id)
    display_type = str(spec.get("display_type") or spec.get("certificate_type") or display_code)
    return {
        "certificate_group": str(spec.get("certificate_group") or ""),
        "certificate_code": display_code,
        "certificate_type": display_type,
        "certificate_name_raw": slot_id,
    }


def enrich_cert_dict_with_spec(cert: dict[str, Any], spec: dict[str, Any], slot_code_key: str) -> dict[str, Any]:
    """Attach display_code / display_type from canonical spec for API + UI."""
    fields = storage_fields_from_spec(spec)
    return {
        **cert,
        slot_code_key: spec["code"],
        "display_code": spec.get("display_code") or fields["certificate_code"],
        "display_type": spec.get("display_type") or fields["certificate_type"],
    }


def default_slot_matches_spec(cert: Certificate | dict[str, Any], spec: dict[str, Any]) -> bool:
    slot_id = str(spec.get("code") or "")
    category = str(cert_value(cert, "certificate_code") or "").strip()
    name_raw = str(cert_value(cert, "certificate_name_raw") or "").strip()
    group = str(cert_value(cert, "certificate_group") or "").strip()
    dtype = str(cert_value(cert, "certificate_type") or "").strip().lower()
    display_code = str(spec.get("display_code") or "").strip()
    display_type = str(spec.get("display_type") or spec.get("certificate_type") or "").strip().lower()

    if name_raw and name_raw == slot_id:
        return True
    if category and category == slot_id:
        return True
    if display_code and category == display_code:
        return True
    if group and group == spec.get("certificate_group") and dtype == display_type:
        return True
    if dtype and display_type and dtype == display_type:
        return True
    text = cert_text(cert)
    return any(term in text for term in spec.get("match_terms") or ())


def find_slot_for_spec(
    certificates: list[Certificate | dict[str, Any]],
    spec: dict[str, Any],
    match_fn: Callable[[Certificate | dict[str, Any], dict[str, Any]], bool],
    *,
    excluded_ids: set[int] | None = None,
    skip_record: Callable[[Certificate | dict[str, Any]], bool] | None = None,
) -> Certificate | dict[str, Any] | None:
    excluded = excluded_ids or set()
    for cert in certificates:
        cert_id = cert_value(cert, "certificate_id")
        if cert_id is not None and int(cert_id) in excluded:
            continue
        if skip_record and skip_record(cert):
            continue
        if match_fn(cert, spec):
            return cert
    return None


def cert_to_dict(cert: Certificate) -> dict[str, Any]:
    return {
        "certificate_id": cert.certificate_id,
        "candidate_id": cert.candidate_id,
        "certificate_group": cert.certificate_group,
        "certificate_type": cert.certificate_type,
        "certificate_name_raw": cert.certificate_name_raw,
        "certificate_code": cert.certificate_code,
        "certificate_number": cert.certificate_number,
        "issuing_authority": cert.issuing_authority,
        "date_issued": cert.date_issued,
        "expiry_date": cert.expiry_date,
        "unlimited_validity": cert.unlimited_validity,
        "country_of_issue": cert.country_of_issue,
        "is_present": cert.is_present,
        "remarks": cert.remarks,
        "scan_file": cert.scan_file,
        "created_at": cert.created_at,
    }


def ensure_canonical_slots(
    session,
    candidate_id: int,
    specs: tuple[dict[str, Any], ...],
    match_fn: Callable[[Certificate | dict[str, Any], dict[str, Any]], bool],
    *,
    skip_record: Callable[[Certificate | dict[str, Any]], bool] | None = None,
) -> bool:
    existing = session.query(Certificate).filter(Certificate.candidate_id == candidate_id).all()
    claimed: set[int] = set()
    changed = False

    for spec in specs:
        match = find_slot_for_spec(existing, spec, match_fn, excluded_ids=claimed, skip_record=skip_record)
        if match is not None:
            cert_id = cert_value(match, "certificate_id")
            if cert_id is not None:
                claimed.add(int(cert_id))
            if isinstance(match, Certificate):
                fields = storage_fields_from_spec(spec)
                for field, value in fields.items():
                    if (getattr(match, field) or "") != value:
                        setattr(match, field, value)
                        changed = True
            continue

        session.add(Certificate(candidate_id=candidate_id, **storage_fields_from_spec(spec)))
        changed = True

    if changed:
        session.commit()
    return changed


def order_slots_for_response(
    certificates: list[dict[str, Any]],
    specs: tuple[dict[str, Any], ...],
    match_fn: Callable[[Certificate | dict[str, Any], dict[str, Any]], bool],
    *,
    session=None,
    candidate_id: int | None = None,
    slot_code_key: str = "slot_code",
) -> list[dict[str, Any]]:
    remaining = list(certificates)
    ordered: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    created_any = False

    for spec in specs:
        match_idx = None
        for idx, cert in enumerate(remaining):
            cert_id = cert.get("certificate_id")
            if cert_id is not None and int(cert_id) in used_ids:
                continue
            if match_fn(cert, spec):
                match_idx = idx
                break
        if match_idx is None:
            if session is not None and candidate_id is not None:
                row = Certificate(candidate_id=candidate_id, **storage_fields_from_spec(spec))
                session.add(row)
                session.flush()
                doc = enrich_cert_dict_with_spec(cert_to_dict(row), spec, slot_code_key)
                ordered.append(doc)
                used_ids.add(int(row.certificate_id))
                created_any = True
                continue
            fields = storage_fields_from_spec(spec)
            ordered.append(
                enrich_cert_dict_with_spec(
                    {"certificate_id": None, **fields, "is_canonical_placeholder": True},
                    spec,
                    slot_code_key,
                )
            )
            continue
        cert = enrich_cert_dict_with_spec(remaining.pop(match_idx), spec, slot_code_key)
        if cert.get("certificate_id") is not None:
            used_ids.add(int(cert["certificate_id"]))
        ordered.append(cert)

    if created_any and session is not None:
        session.commit()
    return ordered


def apply_slot_placeholders(
    context: dict[str, Any],
    specs: tuple[dict[str, Any], ...],
    match_fn: Callable[[Certificate | dict[str, Any], dict[str, Any]], bool],
    combined_keys: tuple[str, ...] = ("certificates",),
) -> None:
    combined: list[dict[str, Any]] = []
    for key in combined_keys:
        for item in context.get(key) or []:
            if item not in combined:
                combined.append(item)

    claimed: set[int] = set()

    for spec in specs:
        cert_rec = find_slot_for_spec(combined, spec, match_fn, excluded_ids=claimed)
        cert_id = cert_value(cert_rec, "certificate_id")
        if cert_id is not None:
            claimed.add(int(cert_id))
        prefix = spec["placeholder_prefix"]
        cert_dict: dict[str, Any] | None = None
        if isinstance(cert_rec, dict):
            cert_dict = cert_rec
        elif isinstance(cert_rec, Certificate):
            cert_dict = cert_to_dict(cert_rec)
        number = clean_document_number_field(cert_value(cert_rec, "certificate_number"), cert_dict)
        context.setdefault(f"{prefix}_certificate_number", number)
        context.setdefault(f"{prefix}_issue_date", cert_value(cert_rec, "date_issued") or "")
        context.setdefault(f"{prefix}_expiry_date", cert_value(cert_rec, "expiry_date") or "")
        context.setdefault(f"{prefix}_issuing_authority", cert_value(cert_rec, "issuing_authority") or "")
        context.setdefault(f"{prefix}_country_of_issue", cert_value(cert_rec, "country_of_issue") or "")
        for legacy_prefix in spec.get("legacy_prefixes") or ():
            context.setdefault(f"{legacy_prefix}_document_number", context.get(f"{prefix}_certificate_number") or "")
            context.setdefault(f"{legacy_prefix}_issue_date", context.get(f"{prefix}_issue_date") or "")
            context.setdefault(f"{legacy_prefix}_expiry_date", context.get(f"{prefix}_expiry_date") or "")
            context.setdefault(f"{legacy_prefix}_issuing_authority", context.get(f"{prefix}_issuing_authority") or "")
