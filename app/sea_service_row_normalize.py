"""Normalize parsed sea-service rows: EOC default, flag/kW column hygiene."""

from __future__ import annotations

import re
from typing import Any

from parser.pdf_parser import _MARIRIME_VESSEL_FLAGS

_KW_SUFFIX_RE = re.compile(
    r"^(?P<engine>.+?)\s+(?P<power>\d[\d.,]*\s*(?:kw|bhp|hp|ps))\s*$",
    re.IGNORECASE,
)
_KW_ONLY_RE = re.compile(r"^\d[\d.,]*\s*(?:kw|bhp|hp|ps)$", re.IGNORECASE)
_CRANE_REMARKS_RE = re.compile(r"^\d+\s*(?:crane|cranes|grab|grabs)\b", re.IGNORECASE)
_VALID_DISCHARGE = frozenset(
    {
        "eoc",
        "transfer",
        "promotion",
        "relief",
        "dismissal",
        "sign off",
        "sign-off",
        "completion of contract",
        "end of contract",
    }
)
_VESSEL_TYPE_REMARKS_RE = re.compile(
    r"\b(bulk|oil|crude|chemical|product|container|general cargo|tanker|carrier|vessel)\b",
    re.IGNORECASE,
)


def _flag_names_lower() -> frozenset[str]:
    return frozenset(f.lower() for f in _MARIRIME_VESSEL_FLAGS)


def _looks_like_flag_text(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    low = text.lower()
    if low in _flag_names_lower():
        return True
    return any(name in low for name in _flag_names_lower() if len(name) > 4)


def split_engine_and_power(main_engine: str | None, engine_power: str | None) -> tuple[str | None, str | None]:
    engine = (main_engine or "").strip() or None
    power = (engine_power or "").strip() or None
    if power or not engine:
        return engine, power
    match = _KW_SUFFIX_RE.match(engine)
    if match:
        eng = match.group("engine").strip() or None
        pwr = match.group("power").strip() or None
        return eng, pwr
    tokens = engine.split()
    if len(tokens) >= 2 and _KW_ONLY_RE.match(tokens[-1]):
        return " ".join(tokens[:-1]).strip() or None, tokens[-1]
    return engine, power


def sanitize_discharge_remarks(remarks: str | None) -> str:
    text = (remarks or "").strip()
    if not text:
        return "EOC"
    low = text.lower()
    if low in _VALID_DISCHARGE:
        return "EOC" if low == "eoc" else text
    if _CRANE_REMARKS_RE.match(text):
        return "EOC"
    if _looks_like_flag_text(text):
        return "EOC"
    if _VESSEL_TYPE_REMARKS_RE.search(text) and len(text.split()) <= 6:
        return "EOC"
    if re.fullmatch(r"\d{4,6}", text):
        return "EOC"
    return text


def extract_flag_from_text(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    for name in sorted(_MARIRIME_VESSEL_FLAGS, key=len, reverse=True):
        pos = low.find(name.lower())
        if pos >= 0:
            return name
    return None


def normalize_sea_service_row(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply cross-parser fixes before DB persist."""
    row = dict(payload)
    engine, power = split_engine_and_power(row.get("main_engine"), row.get("engine_power"))
    row["main_engine"] = engine
    row["engine_power"] = power

    remarks = row.get("remarks")
    flag = (row.get("flag") or "").strip() or None
    if not flag and isinstance(remarks, str) and _looks_like_flag_text(remarks):
        row["flag"] = remarks.strip()
        remarks = None
    row["remarks"] = sanitize_discharge_remarks(remarks if isinstance(remarks, str) else None)

    if not (row.get("flag") or "").strip():
        for key in ("employer", "manning_agency", "vessel_name"):
            found = extract_flag_from_text(row.get(key))
            if found:
                row["flag"] = found
                break

    return row
