"""Certificate validity: +5 calendar years, unlimited, manual dates."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

VALIDITY_YEARS = 5


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    parts = text.replace("/", "-").replace(".", "-").split("-")
    if len(parts) == 3 and len(parts[2]) == 4:
        try:
            dd, mm, yyyy = int(parts[0]), int(parts[1]), int(parts[2])
            return date(yyyy, mm, dd)
        except ValueError:
            return None
    return None


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _sub_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def _has_both_dates(payload: dict[str, Any]) -> bool:
    return _as_date(payload.get("date_issued")) is not None and _as_date(payload.get("expiry_date")) is not None


def apply_plus5_years(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["unlimited_validity"] = False
    issued = _as_date(payload.get("date_issued"))
    expiry = _as_date(payload.get("expiry_date"))
    if issued and not expiry:
        payload["expiry_date"] = _add_years(issued, VALIDITY_YEARS)
    elif expiry and not issued:
        payload["date_issued"] = _sub_years(expiry, VALIDITY_YEARS)
    elif issued and expiry:
        payload["expiry_date"] = _add_years(issued, VALIDITY_YEARS)
    return payload


def apply_certificate_validity_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Fill missing certificate dates when not a complete pair from import.
    Does not overwrite when both date_issued and expiry_date are already set.
    """
    payload = dict(payload)
    if payload.get("unlimited_validity") is True:
        payload["expiry_date"] = None
        return payload

    if _has_both_dates(payload):
        return payload

    return apply_plus5_years(payload)
