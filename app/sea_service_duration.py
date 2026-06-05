"""Sea service helpers: contract duration and default field values."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

DEFAULT_DISCHARGE_REASON = "EOC"


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
    iso = text[:10] if len(text) >= 10 and text[4] == "-" else None
    if iso:
        try:
            return date.fromisoformat(iso)
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


def contract_duration_ymd(sign_on: Any, sign_off: Any) -> str | None:
    """Return 'Y/M/D' with both sign-on and sign-off days counted."""
    start = _as_date(sign_on)
    end = _as_date(sign_off)
    if not start or not end or end < start:
        return None

    end_exclusive = end + timedelta(days=1)
    years = end_exclusive.year - start.year
    months = end_exclusive.month - start.month
    days = end_exclusive.day - start.day

    if days < 0:
        months -= 1
        prev_month_end = (end_exclusive.replace(day=1) - timedelta(days=1)).day
        days += prev_month_end
    if months < 0:
        years -= 1
        months += 12

    return f"{years}/{months}/{days}"


def apply_sea_service_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Duration from dates; Reason of Discharge defaults to EOC when empty."""
    from app.sea_service_row_normalize import normalize_sea_service_row

    payload = normalize_sea_service_row(dict(payload))
    if not str(payload.get("remarks") or "").strip():
        payload["remarks"] = DEFAULT_DISCHARGE_REASON
    sign_on = payload.get("sign_on_date")
    sign_off = payload.get("sign_off_date")
    computed = contract_duration_ymd(sign_on, sign_off)
    if computed:
        payload["contract_duration"] = computed
    return payload


def apply_contract_duration_to_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return apply_sea_service_defaults(payload)


def normalize_sea_service_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a sea-service dict for API responses (display-only fixes)."""
    return apply_sea_service_defaults(dict(row))
