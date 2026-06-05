"""Vessel field metadata for API placeholders and Companies UI."""

from __future__ import annotations

# (attribute name on Vessel model, Russian label for UI / placeholder list)
VESSEL_FIELD_SPECS: tuple[tuple[str, str], ...] = (
    ("name", "Название"),
    ("imo", "ИМО"),
    ("flag", "Флаг"),
    ("port_of_registry", "Port of Registry"),
    ("vessel_type", "Тип судна"),
    ("registry_address", "Адрес судна (регистрация)"),
    ("official_number", "Official No"),
    ("call_sign", "CALL SIGN"),
    ("grt", "GRT"),
    ("deadweight", "Dead Weight"),
    ("year_built", "Year of Built"),
    ("engine_type", "Engine Type"),
    ("engine_hp", "H.P."),
    ("classification_society", "Classification society"),
)

VESSEL_OPTIONAL_STRING_FIELDS = frozenset(
    key
    for key, _ in VESSEL_FIELD_SPECS
    if key not in {"name", "year_built"}
)

VESSEL_PLACEHOLDER_KEYS = frozenset(key for key, _ in VESSEL_FIELD_SPECS if key != "name")


def vessel_placeholder_suffix(field_key: str) -> str:
    """Docx placeholder suffix (vessel_type maps to legacy ``_type``)."""
    return "type" if field_key == "vessel_type" else field_key


def vessel_placeholder_token(prefix: str, field_key: str) -> str:
    return f"{{{{ {prefix}_{vessel_placeholder_suffix(field_key)} }}}}"


def vessel_placeholder_value(vessel, field_key: str) -> str:
    if field_key == "name":
        return vessel.name or ""
    if field_key == "vessel_type":
        return vessel.vessel_type or ""
    if field_key == "year_built":
        return str(vessel.year_built) if vessel.year_built is not None else ""
    value = getattr(vessel, field_key, None)
    if value is None:
        return ""
    return str(value).strip() if isinstance(value, str) else str(value)
