"""Salary calculator: matrix lookup, validation, and template placeholders."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.schema import Company, SalaryComponentTemplate

FIXED_COMPONENT_KEYS = (
    "basic_monthly_wage",
    "monthly_overtime",
    "sepf",
    "imtf",
    "leave",
    "leave_sub",
    "various_extra_overtime",
)

DISPLAY_ONLY_KEYS = ("overtime_rate",)

ALL_COMPONENT_KEYS = FIXED_COMPONENT_KEYS + DISPLAY_ONLY_KEYS

MSG_SELECT_COMPANY = "Please select Company."
MSG_SELECT_RANK = "Please select Rank / Position."
MSG_ENTER_TOTAL_WAGE = "Please enter Total Wage."
MSG_TOTAL_WAGE_TOO_LOW = "Total Wage cannot be lower than fixed salary components."
MSG_TEMPLATE_NOT_FOUND = "No salary components configured for this Company and Rank."


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def components_from_template(template: SalaryComponentTemplate) -> dict[str, float]:
    return {
        "basic_monthly_wage": _to_float(template.basic_monthly_wage),
        "monthly_overtime": _to_float(template.monthly_overtime),
        "overtime_rate": _to_float(template.overtime_rate),
        "sepf": _to_float(template.sepf),
        "imtf": _to_float(template.imtf),
        "leave": _to_float(template.leave),
        "leave_sub": _to_float(template.leave_sub),
        "various_extra_overtime": _to_float(template.various_extra_overtime),
    }


def fixed_components_total(components: dict[str, float]) -> float:
    return round(sum(_to_float(components.get(key)) for key in FIXED_COMPONENT_KEYS), 2)


def owners_bonus(total_wage: float, fixed_total: float) -> float:
    return round(_to_float(total_wage) - _to_float(fixed_total), 2)


def get_template(db_session: Session, *, company_id: int, rank: str) -> SalaryComponentTemplate | None:
    rank_clean = (rank or "").strip()
    if not rank_clean:
        return None
    return (
        db_session.query(SalaryComponentTemplate)
        .filter(
            SalaryComponentTemplate.company_id == company_id,
            SalaryComponentTemplate.rank == rank_clean,
        )
        .one_or_none()
    )


def list_ranks_for_company(db_session: Session, company_id: int) -> list[str]:
    rows = (
        db_session.query(SalaryComponentTemplate.rank)
        .filter(SalaryComponentTemplate.company_id == company_id)
        .order_by(SalaryComponentTemplate.rank.asc())
        .all()
    )
    return [row[0] for row in rows if row[0]]


def calculate_salary(
    db_session: Session,
    *,
    company_id: int,
    rank: str,
    total_wage: Any,
    period_of_employment: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if not company_id:
        errors.append(MSG_SELECT_COMPANY)
    rank_clean = (rank or "").strip()
    if not rank_clean:
        errors.append(MSG_SELECT_RANK)
    total = _to_float(total_wage)
    if total_wage is None or total_wage == "":
        errors.append(MSG_ENTER_TOTAL_WAGE)

    company = db_session.get(Company, company_id) if company_id else None
    if company_id and not company:
        errors.append("Company not found.")

    components: dict[str, float] = {key: 0.0 for key in ALL_COMPONENT_KEYS}
    template = None
    if company_id and rank_clean and not errors:
        template = get_template(db_session, company_id=company_id, rank=rank_clean)
        if not template:
            errors.append(MSG_TEMPLATE_NOT_FOUND)
        else:
            components = components_from_template(template)

    fixed_total = fixed_components_total(components)
    bonus = owners_bonus(total, fixed_total) if not errors else 0.0
    if not errors and total < fixed_total:
        errors.append(MSG_TOTAL_WAGE_TOO_LOW)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "company_id": company_id,
        "company_name": company.name if company else "",
        "rank": rank_clean,
        "total_wage": total,
        "period_of_employment": (period_of_employment or "").strip(),
        "components": components,
        "fixed_components_total": fixed_total,
        "owners_bonus": bonus,
        "template_id": template.template_id if template else None,
    }


def build_saved_calculation_payload(
    calc: dict[str, Any],
    *,
    username: str | None,
) -> dict[str, Any]:
    components = calc.get("components") or {}
    return {
        "company_id": calc.get("company_id"),
        "company_name": calc.get("company_name") or "",
        "rank": calc.get("rank") or "",
        "total_wage": calc.get("total_wage"),
        "period_of_employment": calc.get("period_of_employment") or "",
        "basic_monthly_wage": components.get("basic_monthly_wage", 0),
        "monthly_overtime": components.get("monthly_overtime", 0),
        "overtime_rate": components.get("overtime_rate", 0),
        "sepf": components.get("sepf", 0),
        "imtf": components.get("imtf", 0),
        "leave": components.get("leave", 0),
        "leave_sub": components.get("leave_sub", 0),
        "various_extra_overtime": components.get("various_extra_overtime", 0),
        "fixed_components_total": calc.get("fixed_components_total", 0),
        "owners_bonus": calc.get("owners_bonus", 0),
        "calculation_date": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "calculated_by": username or "",
    }


def parse_saved_calculation(raw: str | None) -> dict[str, Any]:
    import json

    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def salary_placeholders_from_saved(data: dict[str, Any]) -> dict[str, str]:
    if not data:
        return {}

    def fmt_num(key: str) -> str:
        val = data.get(key)
        if val is None or val == "":
            return ""
        try:
            num = float(val)
            if num == int(num):
                return str(int(num))
            return str(num)
        except (TypeError, ValueError):
            return str(val)

    return {
        "salary_company": str(data.get("company_name") or ""),
        "salary_rank": str(data.get("rank") or ""),
        "salary_total_wage": fmt_num("total_wage"),
        "salary_period_of_employment": str(data.get("period_of_employment") or ""),
        "salary_basic_monthly_wage": fmt_num("basic_monthly_wage"),
        "salary_monthly_overtime": fmt_num("monthly_overtime"),
        "salary_overtime_rate": fmt_num("overtime_rate"),
        "salary_sepf": fmt_num("sepf"),
        "salary_imtf": fmt_num("imtf"),
        "salary_leave": fmt_num("leave"),
        "salary_leave_sub": fmt_num("leave_sub"),
        "salary_various_extra_overtime": fmt_num("various_extra_overtime"),
        "salary_fixed_components_total": fmt_num("fixed_components_total"),
        "salary_owners_bonus": fmt_num("owners_bonus"),
    }
