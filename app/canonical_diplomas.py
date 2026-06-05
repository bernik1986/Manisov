"""Canonical diploma / tanker diploma slots (stored as Certificate rows)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.template_field_values import clean_document_number_field
from models.schema import Certificate

DIPLOMA_GROUP = "Diploma"
TANKER_DIPLOMA_GROUP = "Tanker Diploma"

# certificate_code, certificate_type, certificate_group, match_terms, placeholder_prefix
CANONICAL_DIPLOMA_SPECS: tuple[dict[str, Any], ...] = (
    {
        "code": "COC",
        "certificate_type": "COC",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": (
            "certificate of competency",
            "certificate of competence",
            "competency",
            "competence",
        ),
        "placeholder_prefix": "coc",
        "legacy_prefixes": ("coc",),
        "legacy_slot_codes": ("COC_END",),
    },
    {
        "code": "END_COC",
        "certificate_type": "Endorsement COC",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": (
            "endorsement coc",
            "coc endorsement",
            "endorsement to coc",
            "coc & endorsement",
            "coc and endorsement",
        ),
        "placeholder_prefix": "endorsement_coc",
        "legacy_prefixes": ("coc_endorsement",),
        "legacy_slot_codes": ("COC_END",),
    },
    {
        "code": "COC_GMDSS",
        "certificate_type": "COC GMDSS",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": ("coc gmdss", "gmdss", "radio operator"),
        "placeholder_prefix": "coc_gmdss",
        "legacy_prefixes": ("gmdss",),
        "legacy_slot_codes": ("COC_GMDSS",),
    },
    {
        "code": "END_GMDSS",
        "certificate_type": "Endorsement GMDSS",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": (
            "endorsement gmdss",
            "gmdss endorsement",
            "coc gmdss & endorsement",
            "coc gmdss and endorsement",
        ),
        "placeholder_prefix": "endorsement_gmdss",
        "legacy_prefixes": ("coc_gmdss_endorsement",),
        "legacy_slot_codes": ("COC_GMDSS",),
    },
    {
        "code": "COC_NAT",
        "certificate_type": "COC",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": (
            "ethiopian",
            "egyptian",
            "ukrainian coc",
            "national coc",
            " ministry of transport",
            " flag coc",
        ),
        "placeholder_prefix": "coc_national",
        "legacy_prefixes": (),
        "legacy_slot_codes": ("COC",),
    },
    {
        "code": "COP_WELDER",
        "certificate_type": "COP Ship's Welder",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": ("ship's welder", "ships welder", "ship welder", "welder", "ftr"),
        "placeholder_prefix": "cop_ships_welder",
        "legacy_prefixes": (),
    },
    {
        "code": "COP_AB",
        "certificate_type": "COP Able Seafarer",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": ("able seafarer", "able seaman", "ab seafarer"),
        "placeholder_prefix": "cop_able_seafarer",
        "legacy_prefixes": (),
    },
    {
        "code": "COP_MOTO",
        "certificate_type": "COP Motorman",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": ("motorman", "motor man", "oiler"),
        "placeholder_prefix": "cop_motorman",
        "legacy_prefixes": (),
    },
    {
        "code": "COP_COOK",
        "certificate_type": "COP Ship's Cook",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": ("ship's cook", "ships cook", "ship cook"),
        "placeholder_prefix": "cop_ships_cook",
        "legacy_prefixes": (),
    },
    {
        "code": "COP_ELEC",
        "certificate_type": "COP Electrician",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": ("electrician", "electrical"),
        "placeholder_prefix": "cop_electrician",
        "legacy_prefixes": (),
    },
    {
        "code": "COP",
        "certificate_type": "COP",
        "certificate_group": DIPLOMA_GROUP,
        "match_terms": (
            "certificate of proficiency",
            "cop ",
            " cop",
        ),
        "placeholder_prefix": "cop",
        "legacy_prefixes": (),
    },
)

CANONICAL_TANKER_DIPLOMA_SPECS: tuple[dict[str, Any], ...] = (
    {
        "code": "T_BOC",
        "certificate_type": "COP Basic Oil&Chemical",
        "certificate_group": TANKER_DIPLOMA_GROUP,
        "match_terms": (
            "basic oil",
            "oil & chemical",
            "oil and chemical",
            "oil/chemical",
            "basic oil and chemical",
            "oil chemical tanker",
        ),
        "placeholder_prefix": "cop_basic_oil_chemical",
        "legacy_prefixes": (),
    },
    {
        "code": "T_ACC",
        "certificate_type": "COP Advanced Chemical",
        "certificate_group": TANKER_DIPLOMA_GROUP,
        "match_terms": ("advanced chemical", "adv chemical", "chemical tanker advanced"),
        "placeholder_prefix": "cop_advanced_chemical",
        "legacy_prefixes": (),
    },
    {
        "code": "T_AOC",
        "certificate_type": "COP Advanced Oil",
        "certificate_group": TANKER_DIPLOMA_GROUP,
        "match_terms": ("advanced oil", "adv oil", "oil tanker advanced"),
        "placeholder_prefix": "cop_advanced_oil",
        "legacy_prefixes": (),
    },
    {
        "code": "T_BG",
        "certificate_type": "COP Basic Gas",
        "certificate_group": TANKER_DIPLOMA_GROUP,
        "match_terms": ("basic gas", "gas tanker basic", "liquefied gas basic"),
        "placeholder_prefix": "cop_basic_gas",
        "legacy_prefixes": (),
    },
    {
        "code": "T_AG",
        "certificate_type": "COP Advanced Gas",
        "certificate_group": TANKER_DIPLOMA_GROUP,
        "match_terms": ("advanced gas", "adv gas", "gas tanker advanced"),
        "placeholder_prefix": "cop_advanced_gas",
        "legacy_prefixes": (),
    },
)

ALL_CANONICAL_DIPLOMA_SPECS: tuple[dict[str, Any], ...] = CANONICAL_DIPLOMA_SPECS + CANONICAL_TANKER_DIPLOMA_SPECS

ALL_DIPLOMA_SLOT_CODES: frozenset[str] = frozenset(str(s["code"]) for s in ALL_CANONICAL_DIPLOMA_SPECS)

_NON_DIPLOMA_CERTIFICATE_GROUPS: frozenset[str] = frozenset(
    {
        "Conventional Certificate",
        "ECDIS Certificate",
        "Company Certificate",
        "BWTS Certificate",
    }
)


def _cert_text(cert: Certificate | dict[str, Any]) -> str:
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


def _cert_value(cert: Certificate | dict[str, Any] | None, field: str) -> Any:
    if cert is None:
        return None
    if isinstance(cert, Certificate):
        return getattr(cert, field, None)
    return cert.get(field)


def _diploma_display_label(spec: dict[str, Any]) -> str:
    return str(spec.get("certificate_type") or "").strip()


def _enrich_diploma_dict(
    cert: dict[str, Any],
    spec: dict[str, Any] | None,
    *,
    slot_code_key: str = "diploma_code",
) -> dict[str, Any]:
    label = _diploma_display_label(spec) if spec else str(cert.get("certificate_type") or cert.get("certificate_code") or "").strip()
    slot_code = str(spec.get("code") or "") if spec else str(
        cert.get(slot_code_key) or cert.get("diploma_code") or cert.get("certificate_name_raw") or ""
    )
    enriched = {**cert, "display_code": label, "display_type": label}
    if slot_code:
        enriched[slot_code_key] = slot_code
        if slot_code_key != "diploma_code":
            enriched["diploma_code"] = slot_code
    return enriched


def _pool_for_specs(
    certificates: list[dict[str, Any]],
    specs: tuple[dict[str, Any], ...],
    *,
    match_fn: Callable[[Certificate | dict[str, Any], dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    matcher = match_fn or diploma_matches_spec
    spec_codes = {str(s["code"]) for s in specs}
    groups = {str(s["certificate_group"]) for s in specs}
    pool: list[dict[str, Any]] = []
    for cert in certificates:
        raw = str(cert.get("certificate_name_raw") or "").strip()
        if raw in spec_codes:
            pool.append(cert)
            continue
        group = str(cert.get("certificate_group") or "").strip()
        if group in groups:
            pool.append(cert)
            continue
        if any(matcher(cert, spec) for spec in specs):
            pool.append(cert)
    return pool


def diploma_matches_spec(cert: Certificate | dict[str, Any], spec: dict[str, Any]) -> bool:
    code = str(spec.get("code") or "")
    slot_raw = str(_cert_value(cert, "certificate_name_raw") or "").strip()
    category = str(_cert_value(cert, "certificate_code") or "").strip()
    group = str(_cert_value(cert, "certificate_group") or "").strip()
    if group in _NON_DIPLOMA_CERTIFICATE_GROUPS:
        return False
    dtype = str(_cert_value(cert, "certificate_type") or "").strip().lower()
    canonical = str(spec.get("certificate_type") or "").strip().lower()

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

    text = _cert_text(cert)
    legacy_slots = tuple(spec.get("legacy_slot_codes") or ())
    if slot_raw in legacy_slots:
        if slot_raw == "COC_END":
            if code == "END_COC":
                return "endorsement" in text
            if code == "COC":
                return "endorsement" not in text
        if slot_raw == "COC_GMDSS":
            if code == "END_GMDSS":
                return "endorsement" in text
            if code == "COC_GMDSS":
                return "endorsement" not in text
        if slot_raw == "COC" and code == "COC_NAT":
            return True

    if code == "COC":
        if "endorsement" in text and "competency" not in text and "competence" not in text:
            return False
        if "gmdss" in text:
            return False
        if any(term in text for term in spec.get("match_terms") or ()):
            return True
        if dtype == canonical:
            return True
        return False

    if code == "END_COC":
        if "gmdss" in text:
            return False
        return any(term in text for term in spec.get("match_terms") or ())

    if code == "COC_GMDSS":
        if "endorsement" in text:
            return False
        return any(term in text for term in spec.get("match_terms") or ())

    if code == "END_GMDSS":
        return any(term in text for term in spec.get("match_terms") or ())

    if code == "COC_NAT":
        if "gmdss" in text:
            return False
        if "certificate of competency" in text or "competency" in text or "competence" in text:
            return False
        if "endorsement" in text:
            return False
        if dtype == canonical:
            return any(term in text for term in spec.get("match_terms") or ())
        return any(term in text for term in spec.get("match_terms") or ())

    if code == "COP":
        for other in CANONICAL_DIPLOMA_SPECS:
            if other["code"] == "COP":
                continue
            if other["certificate_type"].lower() in dtype:
                return False
        return any(term in text for term in spec.get("match_terms") or ())

    return any(term in text for term in spec.get("match_terms") or ())


def find_certificate_for_spec(
    certificates: list[Certificate | dict[str, Any]],
    spec: dict[str, Any],
    *,
    excluded_ids: set[int] | None = None,
    match_fn: Callable[[Certificate | dict[str, Any], dict[str, Any]], bool] | None = None,
) -> Certificate | dict[str, Any] | None:
    matcher = match_fn or diploma_matches_spec
    excluded = excluded_ids or set()
    for cert in certificates:
        cert_id = _cert_value(cert, "certificate_id")
        if cert_id is not None and int(cert_id) in excluded:
            continue
        if matcher(cert, spec):
            return cert
    return None


def is_canonical_diploma_record(cert: Certificate | dict[str, Any]) -> bool:
    return any(diploma_matches_spec(cert, spec) for spec in ALL_CANONICAL_DIPLOMA_SPECS)


def ensure_canonical_diplomas(session, candidate_id: int) -> bool:
    existing = session.query(Certificate).filter(Certificate.candidate_id == candidate_id).all()
    claimed: set[int] = set()
    changed = False

    for spec in ALL_CANONICAL_DIPLOMA_SPECS:
        match = find_certificate_for_spec(existing, spec, excluded_ids=claimed)
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
        existing = session.query(Certificate).filter(Certificate.candidate_id == candidate_id).all()
    return changed


def _cert_to_dict(cert: Certificate) -> dict[str, Any]:
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


def order_specs_for_response(
    certificates: list[dict[str, Any]],
    specs: tuple[dict[str, Any], ...],
    *,
    match_fn: Callable[[Certificate | dict[str, Any], dict[str, Any]], bool] | None = None,
    slot_code_key: str = "diploma_code",
    session=None,
    candidate_id: int | None = None,
) -> list[dict[str, Any]]:
    matcher = match_fn or diploma_matches_spec
    remaining = _pool_for_specs(list(certificates), specs, match_fn=matcher)
    ordered: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    created_any = False

    for spec in specs:
        match_idx = None
        for idx, cert in enumerate(remaining):
            cert_id = cert.get("certificate_id")
            if cert_id is not None and int(cert_id) in used_ids:
                continue
            if matcher(cert, spec):
                match_idx = idx
                break
        if match_idx is None:
            if session is not None and candidate_id is not None:
                label = _diploma_display_label(spec)
                row = Certificate(
                    candidate_id=candidate_id,
                    certificate_group=spec["certificate_group"],
                    certificate_code=label,
                    certificate_type=spec["certificate_type"],
                    certificate_name_raw=spec["code"],
                )
                session.add(row)
                session.flush()
                doc = _enrich_diploma_dict(
                    {**_cert_to_dict(row), slot_code_key: spec["code"]},
                    spec,
                    slot_code_key=slot_code_key,
                )
                ordered.append(doc)
                used_ids.add(int(row.certificate_id))
                created_any = True
                continue
            ordered.append(
                _enrich_diploma_dict(
                    {
                        "certificate_id": None,
                        "certificate_group": spec["certificate_group"],
                        "certificate_code": _diploma_display_label(spec),
                        "certificate_type": spec["certificate_type"],
                        slot_code_key: spec["code"],
                        "is_canonical_placeholder": True,
                    },
                    spec,
                    slot_code_key=slot_code_key,
                )
            )
            continue
        cert = _enrich_diploma_dict(
            {**remaining.pop(match_idx), slot_code_key: spec["code"]},
            spec,
            slot_code_key=slot_code_key,
        )
        if cert.get("certificate_id") is not None:
            used_ids.add(int(cert["certificate_id"]))
        ordered.append(cert)

    if created_any and session is not None:
        session.commit()

    return ordered


def partition_certificate_dicts(
    certificates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (general_stcw, all_for_diploma_ordering, all_for_tanker_ordering)."""
    general: list[dict[str, Any]] = []
    for cert in certificates:
        if is_canonical_diploma_record(cert):
            continue
        general.append(cert)
    return general, list(certificates), list(certificates)


def is_working_coc_diploma(cert: Certificate | dict[str, Any]) -> bool:
    """True for the canonical working COC slot (not endorsement / GMDSS / national)."""
    coc_spec = next(s for s in CANONICAL_DIPLOMA_SPECS if s["code"] == "COC")
    return diploma_matches_spec(cert, coc_spec)


def apply_canonical_diploma_placeholders(context: dict[str, Any]) -> None:
    combined = list(context.get("certificates") or [])
    for key in ("diplomas", "tanker_diplomas"):
        for item in context.get(key) or []:
            if item not in combined:
                combined.append(item)

    claimed: set[int] = set()

    def apply_spec(spec: dict[str, Any]) -> None:
        cert_rec = find_certificate_for_spec(combined, spec, excluded_ids=claimed)
        cert_id = _cert_value(cert_rec, "certificate_id")
        if cert_id is not None:
            claimed.add(int(cert_id))
        prefix = spec["placeholder_prefix"]
        cert_dict: dict[str, Any] | None = None
        if isinstance(cert_rec, dict):
            cert_dict = cert_rec
        elif isinstance(cert_rec, Certificate):
            cert_dict = _cert_to_dict(cert_rec)
        context.setdefault(
            f"{prefix}_certificate_number",
            clean_document_number_field(_cert_value(cert_rec, "certificate_number"), cert_dict),
        )
        context.setdefault(f"{prefix}_issue_date", _cert_value(cert_rec, "date_issued") or "")
        context.setdefault(f"{prefix}_expiry_date", _cert_value(cert_rec, "expiry_date") or "")
        context.setdefault(f"{prefix}_issuing_authority", _cert_value(cert_rec, "issuing_authority") or "")
        context.setdefault(f"{prefix}_country_of_issue", _cert_value(cert_rec, "country_of_issue") or "")
        if spec.get("code") == "COC":
            rank = _cert_value(cert_rec, "competency_rank")
            rank_str = "" if rank is None else str(rank).strip()
            context.setdefault("coc_competency_rank", rank_str)
            if rank_str:
                context["coc_rank"] = rank_str
        for legacy_prefix in spec.get("legacy_prefixes") or ():
            context.setdefault(f"{legacy_prefix}_certificate_number", context.get(f"{prefix}_certificate_number") or "")
            context.setdefault(f"{legacy_prefix}_document_number", context.get(f"{prefix}_certificate_number") or "")
            context.setdefault(f"{legacy_prefix}_issue_date", context.get(f"{prefix}_issue_date") or "")
            context.setdefault(f"{legacy_prefix}_expiry_date", context.get(f"{prefix}_expiry_date") or "")
            context.setdefault(f"{legacy_prefix}_issuing_authority", context.get(f"{prefix}_issuing_authority") or "")

    for spec in CANONICAL_DIPLOMA_SPECS:
        apply_spec(spec)
    for spec in CANONICAL_TANKER_DIPLOMA_SPECS:
        apply_spec(spec)

    # Legacy COC fields from working COC slot (do not override if already set on candidate).
    context.setdefault("coc_certificate_number", context.get("coc_certificate_number") or "")
    context.setdefault("coc_issue_date", context.get("coc_issue_date") or "")
    context.setdefault("coc_expiry_date", context.get("coc_expiry_date") or "")


def canonical_diploma_placeholder_tokens() -> list[str]:
    suffixes = ("certificate_number", "issue_date", "expiry_date", "issuing_authority", "country_of_issue")
    tokens: list[str] = []
    for spec in ALL_CANONICAL_DIPLOMA_SPECS:
        prefix = spec["placeholder_prefix"]
        for suffix in suffixes:
            tokens.append(f"{{{{ {prefix}_{suffix} }}}}")
        if spec.get("code") == "COC":
            tokens.append("{{ coc_competency_rank }}")
    return tokens
