"""Sea contract tab: saved JSON on candidate and docxtpl placeholders."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.vessel_specs import VESSEL_FIELD_SPECS, vessel_placeholder_suffix, vessel_placeholder_value
from models.schema import Company, Vessel

CONTRACTS_FOLDER_NAMES: frozenset[str] = frozenset({"контракты", "contracts"})

# Editable fields stored in contract_json (keys match placeholder names).
CONTRACT_EDITABLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("contract_sign_date", "Дата подписания контракта"),
    ("contract_period", "Срок контракта / Period of employment"),
    ("contract_embarkation_date", "Дата посадки"),
    ("contract_embarkation_port", "Порт посадки"),
    ("contract_number", "Номер контракта"),
    ("contract_remarks", "Примечания"),
)

CONTRACT_DEPARTURE_FIELDS: tuple[tuple[str, str], ...] = (
    ("contract_departure_date", "Дата вылета"),
)

CONTRACT_AIRPORT_FIELDS: tuple[tuple[str, str], ...] = (
    ("contract_home_airport", "Home airport"),
    ("contract_departure_airport", "Departure airport"),
)

CONTRACT_ALL_EDITABLE_FIELDS: tuple[tuple[str, str], ...] = (
    *CONTRACT_EDITABLE_FIELDS,
    *CONTRACT_DEPARTURE_FIELDS,
    *CONTRACT_AIRPORT_FIELDS,
)

CONTRACT_SELECTION_KEYS = ("company_id", "company_name", "vessel_id", "vessel_name", "rank")

# Candidate profile fields in docxtpl context (CRM card, not contract_json).
CANDIDATE_PERSONAL_PLACEHOLDER_FIELDS: tuple[tuple[str, str], ...] = (
    ("current_date", "Current date"),
    ("surname", "Фамилия"),
    ("first_name", "Имя"),
    ("middle_name", "Отчество"),
    ("full_name", "Полное имя"),
    ("latin_full_name", "Latin Full Name"),
    ("native_full_name", "Native Full Name"),
    ("date_of_birth", "Дата рождения"),
    ("place_of_birth", "Место рождения"),
    ("country_of_birth", "Страна рождения"),
    ("nationality", "Национальность"),
    ("citizenship", "Гражданство"),
    ("age", "Возраст"),
    ("gender", "Пол"),
    ("marital_status", "Семейное положение"),
    ("father_name", "Имя отца"),
    ("mother_name", "Имя матери"),
    ("primary_phone", "Основной телефон"),
    ("mobile_phone", "Мобильный"),
    ("email", "Email"),
    ("home_address", "Домашний адрес"),
    ("permanent_address", "Постоянный адрес"),
    ("city", "Город"),
    ("country", "Страна"),
    ("current_rank", "Текущая должность"),
    ("passport_number", "Номер паспорта"),
    ("passport_issue_date", "Дата выдачи паспорта"),
    ("passport_expiry_date", "Срок действия паспорта"),
    ("passport_place_of_issue", "Кем / где выдан паспорт"),
    ("seaman_book_number", "Seaman's Book — номер"),
    ("seaman_book_issue_date", "Seaman's Book — дата выдачи"),
    ("seaman_book_expiry_date", "Seaman's Book — срок действия"),
)


def parse_contract_json(raw: str | None) -> dict[str, Any]:
    import json

    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def build_saved_contract_payload(
    *,
    company_id: int,
    company_name: str,
    vessel_id: int | None,
    vessel_name: str | None,
    rank: str,
    editable: dict[str, Any],
    username: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "company_id": company_id,
        "company_name": company_name,
        "vessel_id": vessel_id,
        "vessel_name": vessel_name or "",
        "rank": rank.strip(),
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "updated_by": username or "",
    }
    for key, _label in CONTRACT_ALL_EDITABLE_FIELDS:
        value = editable.get(key)
        payload[key] = "" if value is None else str(value).strip()
    return payload


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip() if isinstance(value, str) else str(value)


def contract_placeholders_from_saved(
    data: dict[str, Any],
    db_session: Session | None = None,
) -> dict[str, str]:
    if not data:
        return {}

    placeholders: dict[str, str] = {
        "contract_company_name": _fmt(data.get("company_name")),
        "contract_vessel_name": _fmt(data.get("vessel_name")),
        "contract_rank": _fmt(data.get("rank")),
    }
    for key, _label in CONTRACT_ALL_EDITABLE_FIELDS:
        placeholders[key] = _fmt(data.get(key))

    home_airport = _fmt(data.get("contract_home_airport"))
    departure_airport = _fmt(data.get("contract_departure_airport"))
    departure_date = _fmt(data.get("contract_departure_date"))
    if home_airport:
        placeholders["home_airport"] = home_airport
    if departure_airport:
        placeholders["departure_airport"] = departure_airport
    if departure_date:
        placeholders["departure_date"] = departure_date

    company_id = data.get("company_id")
    vessel_id = data.get("vessel_id")
    if db_session is not None and company_id:
        company = db_session.get(Company, int(company_id))
        if company:
            placeholders["contract_company_name"] = company.name or ""
            placeholders["contract_company_slug"] = company.slug or ""

    if db_session is not None and vessel_id:
        vessel = db_session.get(Vessel, int(vessel_id))
        if vessel:
            placeholders["contract_vessel_name"] = vessel.name or placeholders["contract_vessel_name"]
            for field_key, _label in VESSEL_FIELD_SPECS:
                suffix = vessel_placeholder_suffix(field_key)
                placeholders[f"contract_vessel_{suffix}"] = vessel_placeholder_value(vessel, field_key)
            if company_id:
                company = db_session.get(Company, int(company_id))
                if company:
                    prefix = f"company_{company.slug}_{vessel.slug}"
                    for field_key, _label in VESSEL_FIELD_SPECS:
                        suffix = vessel_placeholder_suffix(field_key)
                        placeholders[f"{prefix}_{suffix}"] = vessel_placeholder_value(vessel, field_key)

    return placeholders


def candidate_personal_placeholder_lines() -> list[str]:
    return [f"{{{{ {key} }}}}" for key, _label in CANDIDATE_PERSONAL_PLACEHOLDER_FIELDS]


def contract_placeholder_lines() -> list[str]:
    lines = [
        "{{ contract_company_name }}",
        "{{ contract_company_slug }}",
        "{{ contract_vessel_name }}",
        "{{ contract_rank }}",
    ]
    for key, _label in CONTRACT_ALL_EDITABLE_FIELDS:
        lines.append(f"{{{{ {key} }}}}")
    lines.extend(["{{ home_airport }}", "{{ departure_airport }}", "{{ departure_date }}"])
    for field_key, _label in VESSEL_FIELD_SPECS:
        suffix = vessel_placeholder_suffix(field_key)
        lines.append(f"{{{{ contract_vessel_{suffix} }}}}")
    return lines
