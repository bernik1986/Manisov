from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CANDIDATE_UPPERCASE_NAME_FIELDS = frozenset(
    {
        "surname",
        "first_name",
        "middle_name",
        "full_name",
        "latin_full_name",
        "native_full_name",
    }
)


def uppercase_candidate_name(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    return stripped.upper() if stripped else ""


def normalize_candidate_name_mapping(
    values: Mapping[str, Any],
    *,
    compose_full_names: bool = False,
) -> dict[str, Any]:
    normalized = dict(values)
    for field in CANDIDATE_UPPERCASE_NAME_FIELDS:
        if field in normalized:
            normalized[field] = uppercase_candidate_name(normalized[field])

    if compose_full_names:
        parts = [normalized.get("surname"), normalized.get("first_name")]
        composed = " ".join(str(part).strip() for part in parts if str(part or "").strip())
        if composed:
            normalized["full_name"] = composed.upper()
            normalized["latin_full_name"] = composed.upper()
    return normalized


def normalize_candidate_name_instance(candidate: Any) -> None:
    for field in CANDIDATE_UPPERCASE_NAME_FIELDS:
        value = getattr(candidate, field, None)
        if isinstance(value, str):
            setattr(candidate, field, uppercase_candidate_name(value))
