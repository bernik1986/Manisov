"""Canonical STCW / company certificate slots (Certificate rows)."""

from __future__ import annotations

import re
from typing import Any

from models.schema import Certificate

from app.canonical_diplomas import is_canonical_diploma_record
from app.canonical_medical import is_canonical_medical_record
from app.certificate_canonical_slots import (
    apply_slot_placeholders,
    cert_value,
    default_slot_matches_spec,
    ensure_canonical_slots,
    find_slot_for_spec,
    order_slots_for_response,
)

CONVENTIONAL_GROUP = "Conventional Certificate"
ECDIS_GROUP = "ECDIS Certificate"
COMPANY_GROUP = "Company Certificate"
BWTS_GROUP = "BWTS Certificate"


_DASH_SPLIT = re.compile(r"\s*[-–—]\s*")


def _prefix(code: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", code.lower()).strip("_")
    return text


def parse_code_type(line: str) -> tuple[str, str]:
    """Split user label on dash: left = Код, right = Тип; no dash → both equal."""
    normalized = " ".join(str(line or "").split())
    parts = _DASH_SPLIT.split(normalized, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return normalized, normalized


def _spec(
    slot_id: str,
    label_line: str,
    group: str,
    match_terms: tuple[str, ...],
    *,
    legacy_prefixes: tuple[str, ...] = (),
) -> dict[str, Any]:
    display_code, display_type = parse_code_type(label_line)
    return {
        "code": slot_id,
        "display_code": display_code,
        "display_type": display_type,
        "certificate_type": display_type,
        "certificate_group": group,
        "match_terms": match_terms,
        "placeholder_prefix": _prefix(slot_id),
        "legacy_prefixes": legacy_prefixes,
    }


CANONICAL_CONVENTIONAL_SPECS: tuple[dict[str, Any], ...] = (
    _spec("BST", "Basic Safety - Proficiency in basic safety training", CONVENTIONAL_GROUP, ("basic safety", "bst", "proficiency in basic safety")),
    _spec("PSSR", "PSSR - поправка к НБЖС", CONVENTIONAL_GROUP, ("pssr", "поправка к нбжс", "personal safety")),
    _spec("AFF", "AFF - Advanced fire fighting", CONVENTIONAL_GROUP, ("advanced fire fighting", "advanced firefighting", "aff"), legacy_prefixes=("advanced_fire_fighting",)),
    _spec(
        "PSCRB",
        "PSCRB - Proficiency in survival craft and rescue boats (no fast rescue boats)",
        CONVENTIONAL_GROUP,
        ("pscrb", "survival craft", "rescue boats", "proficiency in survival craft"),
        legacy_prefixes=("proficiency_survival_craft",),
    ),
    _spec("MED_CARE", "Medical Care", CONVENTIONAL_GROUP, ("medical care",), legacy_prefixes=("medical_care",)),
    _spec("MFA", "MFA - Medical First Aid", CONVENTIONAL_GROUP, ("medical first aid", "mfa"), legacy_prefixes=("medical_first_aid",)),
    _spec("RADAR_ARPA", "Radar&ARPA", CONVENTIONAL_GROUP, ("radar&arpa", "radar and arpa", "radar arpa", "radar/arpa")),
    _spec("RADAR", "Radar", CONVENTIONAL_GROUP, ("radar",)),
    _spec("ARPA", "ARPA", CONVENTIONAL_GROUP, ("arpa", "automatic radar plotting")),
    _spec("SSO", "SSO - Ship Security Officer", CONVENTIONAL_GROUP, ("ship security officer", "sso"), legacy_prefixes=("sso",)),
    _spec("DSD", "DSD - Designated Security Duties", CONVENTIONAL_GROUP, ("designated security duties", "dsd")),
    _spec(
        "SEC_AWARE",
        "Security Awareness - Security related/awareness training and instruction for all seafarers",
        CONVENTIONAL_GROUP,
        ("security awareness", "security related", "awareness training"),
    ),
    _spec("BRM", "BRM - Bridge Resource Management", CONVENTIONAL_GROUP, ("bridge resource management", "brm"), legacy_prefixes=("brm",)),
    _spec("ERM", "ERM - Engine Resource Management", CONVENTIONAL_GROUP, ("engine resource management", "erm"), legacy_prefixes=("erm",)),
    _spec(
        "ECDIS",
        "ECDIS - The operational use of electronic chart display and information systems",
        CONVENTIONAL_GROUP,
        ("ecdis", "electronic chart display"),
        legacy_prefixes=("ecdis",),
    ),
    _spec("HV", "High Voltage - Shipboard High Voltage", CONVENTIONAL_GROUP, ("high voltage", "shipboard high voltage")),
    _spec(
        "HAZMAT110",
        "HAZMAT 1.10 - Cargo Handling on ships carrying dangerous and hazardous substances in packaged form",
        CONVENTIONAL_GROUP,
        ("hazmat 1.10", "1.10", "packaged form"),
    ),
    _spec(
        "HAZMAT145",
        "HAZMAT 1.45 - Cargo Handling on ships carrying dangerous and hazardous substances in solid form in bulk",
        CONVENTIONAL_GROUP,
        ("hazmat 1.45", "1.45", "solid form in bulk"),
    ),
    _spec("HAZMAT", "HAZMAT", CONVENTIONAL_GROUP, ("hazmat", "hazardous material", "dangerous goods")),
    _spec("GMDSS", "GMDSS - GMDSS certificate", CONVENTIONAL_GROUP, ("gmdss", "general operator", "radio operator"), legacy_prefixes=("gmdss",)),
    _spec("ADV_OIL", "Advanced Oil - Advanced Oil certificate", CONVENTIONAL_GROUP, ("advanced oil", "oil tanker advanced")),
    _spec("ADV_CHEM", "Advanced Chemical - Advanced Chemical certificate", CONVENTIONAL_GROUP, ("advanced chemical", "chemical tanker advanced")),
    _spec("BASIC_OC", "Basic Oil&Chemical - Basic Oil&Chemical certificate", CONVENTIONAL_GROUP, ("basic oil", "oil & chemical", "oil and chemical", "oil/chemical")),
)

CANONICAL_ECDIS_SPECS: tuple[dict[str, Any], ...] = (
    _spec("ECDIS_JRC9201", "ECDIS JAN JRC 9201 / 7201", ECDIS_GROUP, ("jrc 9201", "jrc 7201", "9201", "7201")),
    _spec("ECDIS_JRC901", "ECDIS JAN JRC 901 / 701", ECDIS_GROUP, ("jrc 901", "jrc 701", "901", "701")),
    _spec("ECDIS_FUR_FMD", "ECDIS Furuno FMD", ECDIS_GROUP, ("furuno fmd", "fmd")),
    _spec("ECDIS_FUR_FEA", "ECDIS Furuno FEA", ECDIS_GROUP, ("furuno fea", " fea")),
    _spec("ECDIS_CHART_G2", "ECDIS Chartworld e-Globe G2", ECDIS_GROUP, ("chartworld", "e-globe", "eglobe g2")),
    _spec("ECDIS_TRANSAS", "ECDIS Transas 4000", ECDIS_GROUP, ("transas 4000", "transas")),
    _spec("ECDIS_SIMRAD", "ECDIS Simrad", ECDIS_GROUP, ("simrad",)),
    _spec("ECDIS_DANELEC", "ECDIS Danelec", ECDIS_GROUP, ("danelec",)),
    _spec("ECDIS_SEALL", "ECDIS Seall", ECDIS_GROUP, ("seall",)),
    _spec("ECDIS_SPERRY", "ECDIS Sperry Marine", ECDIS_GROUP, ("sperry marine", "sperry")),
)

CANONICAL_COMPANY_SPECS: tuple[dict[str, Any], ...] = (
    _spec("FRB", "FRB - Fast rescue boats", COMPANY_GROUP, ("fast rescue boat", "frb")),
    _spec("SAFETY_OFF", "Safety Officer", COMPANY_GROUP, ("safety officer", "safety training for personnel"), legacy_prefixes=("safety_officer",)),
    _spec("SHIP_HAND", "Ship Handling - Ship Handling and Maneouvring", COMPANY_GROUP, ("ship handling", "manoeuvring", "maneuvering")),
    _spec("TRAIN_TRAINER", "Train the Trainer", COMPANY_GROUP, ("train the trainer", "trainer training")),
    _spec("RISK_ASSESS", "Risk Assessment", COMPANY_GROUP, ("risk assessment",)),
    _spec("INCIDENT_INV", "Incident Investigation - Marine Incident Investigation", COMPANY_GROUP, ("incident investigation", "marine incident")),
    _spec("NAVTOR", "NAVTOR", COMPANY_GROUP, ("navtor",)),
    _spec("HATCH", "Hatch Cover - Hatch Cover Inspection & Maintenance", COMPANY_GROUP, ("hatch cover",)),
    _spec("PMS", "PMS - Planned Maintenance System Training", COMPANY_GROUP, ("planned maintenance system", "pms")),
    _spec("ME_TRAIN", "ME Training", COMPANY_GROUP, ("me training", "main engine training")),
    _spec("SCRUBBER", "Scrubber - Scrubber system", COMPANY_GROUP, ("scrubber",)),
    _spec("LEADERSHIP", "Leadership - Leadership, teamwork and managerial skills", COMPANY_GROUP, ("leadership", "teamwork", "managerial skills")),
    _spec("EMERG_PREP", "Emergency Preparedness - Emergency Preparedness and Response", COMPANY_GROUP, ("emergency preparedness", "emergency response")),
    _spec("CROSS_CULT", "Cross Cultural", COMPANY_GROUP, ("cross cultural", "cross-cultural")),
    _spec("CULT_AWARE", "Cultural Awareness", COMPANY_GROUP, ("cultural awareness",)),
    _spec("CARGO_OIL", "Cargo Handling Oil - Liquid cargo and ballast handling on oil tankers", COMPANY_GROUP, ("cargo handling oil", "liquid cargo", "oil tanker")),
    _spec("CARGO_CHEM", "Cargo Handling Chemical - Liquid cargo and ballast handling on chemical tankers", COMPANY_GROUP, ("cargo handling chemical", "chemical tanker")),
    _spec("CARGO_GAS", "Cargo Handling Gas - Liquefied natural gas tanker cargo and ballast handling simulator", COMPANY_GROUP, ("cargo handling gas", "lng", "liquefied gas")),
    _spec("MEDIA_RESP", "Media Response", COMPANY_GROUP, ("media response",)),
    _spec("CYBER", "Cyber Security - Maritime Cyber Security Awareness", COMPANY_GROUP, ("cyber security", "maritime cyber")),
    _spec("LIFEBOAT_MAINT", "Operation and Maintenance of Lifeboat", COMPANY_GROUP, ("maintenance of lifeboat", "operation and maintenance of lifeboat")),
    _spec("BWTS", "BWTS - Ballast Water Management", COMPANY_GROUP, ("ballast water management", "bwts")),
    _spec("IHM", "IHM - Inventory of Hazardous Material", COMPANY_GROUP, ("inventory of hazardous material", "ihm")),
    _spec("MENTAL_HEALTH", "Mental Health - Mental Health Awareness", COMPANY_GROUP, ("mental health",)),
    _spec("FREE_FALL_LB", "Free Fall Lifeboats", COMPANY_GROUP, ("free fall lifeboat", "freefall")),
    _spec(
        "MOORING",
        "Mooring Ropes - Mooring ropes inspection procedures, recognition of rope damage & retirement criteria",
        COMPANY_GROUP,
        ("mooring rope", "mooring ropes"),
    ),
    _spec("BCAV", "BCA&V - Behavioural Competency Assessment & Verification", COMPANY_GROUP, ("behavioural competency", "behavioral competency", "bcav")),
    _spec("ENCLOSED_SPACE", "Enclose Space Entry", COMPANY_GROUP, ("enclosed space", "enclose space")),
    _spec("PILOT_LADDERS", "Pilot Ladders", COMPANY_GROUP, ("pilot ladder",)),
    _spec("PSC", "Port State Control - Port State Control Inspections", COMPANY_GROUP, ("port state control", "psc")),
    _spec("RIGHTSHIP", "Rightship - Rightship Inspection Training Course", COMPANY_GROUP, ("rightship",)),
    _spec("WELLNESS", "Wellness at Sea", COMPANY_GROUP, ("wellness at sea",)),
    _spec("ISM", "ISM Code - Safety Management System", COMPANY_GROUP, ("ism code", "safety management system", "ism")),
    _spec("FUMIGATION", "Fumigation Procedures", COMPANY_GROUP, ("fumigation",)),
)

CANONICAL_BWTS_SPECS: tuple[dict[str, Any], ...] = (
    _spec("BWTS_ERMA", "BWTS ERMA", BWTS_GROUP, ("bwts erma", "erma")),
    _spec("BWTS_SUNRUI", "BWTS SunRui", BWTS_GROUP, ("bwts sunrui", "sunrui")),
    _spec("BWTS_HEADWAY", "BWTS Headway", BWTS_GROUP, ("bwts headway", "headway")),
    _spec("BWTS_ECOCHLOR", "BWTS Ecochlor", BWTS_GROUP, ("bwts ecochlor", "ecochlor")),
)

ALL_CANONICAL_CERTIFICATE_SPECS: tuple[dict[str, Any], ...] = (
    CANONICAL_ECDIS_SPECS
    + CANONICAL_BWTS_SPECS
    + CANONICAL_CONVENTIONAL_SPECS
    + CANONICAL_COMPANY_SPECS
)

_ECDIS_SPECIFIC_CODES = frozenset(spec["code"] for spec in CANONICAL_ECDIS_SPECS)
_BWTS_SPECIFIC_CODES = frozenset(spec["code"] for spec in CANONICAL_BWTS_SPECS)
_SPECIFIC_BEFORE_GENERIC: dict[str, tuple[str, ...]] = {
    "RADAR": ("radar&arpa", "radar and arpa", "radar arpa", "radar/arpa"),
    "ARPA": ("radar&arpa", "radar and arpa", "radar arpa", "radar/arpa"),
    "HAZMAT": ("hazmat 1.10", "hazmat 1.45", "1.10", "1.45"),
    "ECDIS": tuple(term for spec in CANONICAL_ECDIS_SPECS for term in spec["match_terms"]),
    "BWTS": tuple(term for spec in CANONICAL_BWTS_SPECS for term in spec["match_terms"]),
}


def _skip_diploma(cert: Certificate | dict[str, Any]) -> bool:
    return is_canonical_diploma_record(cert) or is_canonical_medical_record(cert)


def certificate_matches_spec(cert: Certificate | dict[str, Any], spec: dict[str, Any]) -> bool:
    if _skip_diploma(cert):
        return False
    if not default_slot_matches_spec(cert, spec):
        return False

    code = str(spec.get("code") or "")
    text = " ".join(
        [
            str(cert_value(cert, "certificate_type") or ""),
            str(cert_value(cert, "certificate_name_raw") or ""),
            str(cert_value(cert, "certificate_code") or ""),
        ]
    ).lower()

    if code in _SPECIFIC_BEFORE_GENERIC and any(term in text for term in _SPECIFIC_BEFORE_GENERIC[code]):
        return False
    slot_raw = str(cert_value(cert, "certificate_name_raw") or "").strip()
    if code == "ECDIS" and slot_raw in _ECDIS_SPECIFIC_CODES:
        return False
    if code == "BWTS" and slot_raw in _BWTS_SPECIFIC_CODES:
        return False
    return True


def is_canonical_certificate_record(cert: Certificate | dict[str, Any]) -> bool:
    if _skip_diploma(cert):
        return False
    return any(certificate_matches_spec(cert, spec) for spec in ALL_CANONICAL_CERTIFICATE_SPECS)


def ensure_canonical_certificates(session, candidate_id: int) -> bool:
    return ensure_canonical_slots(
        session,
        candidate_id,
        ALL_CANONICAL_CERTIFICATE_SPECS,
        certificate_matches_spec,
        skip_record=_skip_diploma,
    )


def order_certificates_for_response(
    certificates: list[dict[str, Any]],
    specs: tuple[dict[str, Any], ...],
    *,
    session=None,
    candidate_id: int | None = None,
) -> list[dict[str, Any]]:
    filtered = [cert for cert in certificates if not _skip_diploma(cert)]
    return order_slots_for_response(
        filtered,
        specs,
        certificate_matches_spec,
        session=session,
        candidate_id=candidate_id,
        slot_code_key="certificate_slot_code",
    )


def apply_canonical_certificate_placeholders(context: dict[str, Any]) -> None:
    apply_slot_placeholders(
        context,
        ALL_CANONICAL_CERTIFICATE_SPECS,
        certificate_matches_spec,
        combined_keys=(
            "certificates",
            "conventional_certificates",
            "ecdis_certificates",
            "company_certificates",
            "bwts_certificates",
            "diplomas",
            "tanker_diplomas",
            "medical_documents",
        ),
    )


def canonical_certificate_placeholder_tokens() -> list[str]:
    suffixes = ("certificate_number", "issue_date", "expiry_date", "issuing_authority", "country_of_issue")
    tokens: list[str] = []
    for spec in ALL_CANONICAL_CERTIFICATE_SPECS:
        prefix = spec["placeholder_prefix"]
        for suffix in suffixes:
            tokens.append(f"{{{{ {prefix}_{suffix} }}}}")
    return tokens
