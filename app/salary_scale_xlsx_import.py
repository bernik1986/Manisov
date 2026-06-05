"""Import salary component matrix from Salary Scale.xlsx (DryLog / Chandris sheets)."""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.rank_normalization import resolve_canonical_position
from models.schema import Company, SalaryComponentTemplate

# Sheet name substring -> company slug in CRM
SHEET_COMPANY_SLUGS: dict[str, str] = {
    "drylog": "drylog",
    "chandris": "chandris",
}


class SalaryScaleXlsxImportError(ValueError):
    """Invalid or unreadable salary scale workbook."""


def _cell_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).replace("\xa0", " ").strip()


def _parse_amount(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _cell_str(value)
    if not text:
        return 0.0
    text = text.replace(" ", "").replace(",", ".")
    text = re.sub(r"[^\d.\-]", "", text)
    if not text or text in (".", "-"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _find_column(columns: list[str], *needles: str) -> str | None:
    lowered = [(c, (c or "").lower()) for c in columns]
    for needle in needles:
        n = needle.lower()
        for col, low in lowered:
            if n in low:
                return col
    return None


def _rank_column(columns: list[str]) -> str:
    for col in columns:
        if col and ("unnamed" in col.lower() or col.lower() in ("rank", "position")):
            return col
    return columns[0]


def _parse_drylog_row(row: pd.Series, columns: list[str]) -> dict[str, Any] | None:
    rank_raw = _cell_str(row.get(_rank_column(columns)))
    if not rank_raw:
        return None
    rank = resolve_canonical_position(rank_raw) or rank_raw
    return {
        "rank": rank,
        "basic_monthly_wage": _parse_amount(row.get(_find_column(columns, "basic pay"))),
        "monthly_overtime": _parse_amount(row.get(_find_column(columns, "guaranteed o/t", "103 hrs"))),
        "various_extra_overtime": _parse_amount(
            row.get(_find_column(columns, "extra o/t", "57 hrs"))
        ),
        "leave": _parse_amount(row.get(_find_column(columns, "leave pay"))),
        "leave_sub": _parse_amount(row.get(_find_column(columns, "leave sub"))),
        "overtime_rate": _parse_amount(row.get(_find_column(columns, "o/t rate", "per hour"))),
        "sepf": 0.0,
        "imtf": 0.0,
    }


def _parse_chandris_row(row: pd.Series, columns: list[str]) -> dict[str, Any] | None:
    rank_raw = _cell_str(row.get(_rank_column(columns)))
    if not rank_raw:
        return None
    rank = resolve_canonical_position(rank_raw) or rank_raw
    fixed_ot = _find_column(columns, "fixed ot", "86%")
    guaranteed_ot = _find_column(columns, "103 hrs guaranteed")
    monthly_ot_col = fixed_ot
    if monthly_ot_col is None or _parse_amount(row.get(monthly_ot_col)) == 0.0:
        monthly_ot_col = guaranteed_ot
    return {
        "rank": rank,
        "basic_monthly_wage": _parse_amount(row.get(_find_column(columns, "basic monthly wage"))),
        "monthly_overtime": _parse_amount(row.get(monthly_ot_col)),
        "various_extra_overtime": _parse_amount(
            row.get(_find_column(columns, "various", "extra overtime", "57 hrs"))
        ),
        "sepf": _parse_amount(row.get(_find_column(columns, "sepf"))),
        "imtf": _parse_amount(row.get(_find_column(columns, "imtf"))),
        "leave": _parse_amount(row.get(_find_column(columns, "leave:", "9 days"))),
        "leave_sub": _parse_amount(row.get(_find_column(columns, "leave sub"))),
        "overtime_rate": _parse_amount(
            row.get(_find_column(columns, "overtime rate", "excess of 103"))
        ),
    }


def _sheet_slug(sheet_name: str) -> str | None:
    low = (sheet_name or "").lower()
    for key, slug in SHEET_COMPANY_SLUGS.items():
        if key in low:
            return slug
    return None


def parse_workbook_bytes(content: bytes) -> list[dict[str, Any]]:
    if not content:
        raise SalaryScaleXlsxImportError("Файл пустой")
    try:
        xl = pd.ExcelFile(io.BytesIO(content))
    except Exception as exc:
        raise SalaryScaleXlsxImportError(f"Не удалось прочитать Excel: {exc}") from exc

    rows_out: list[dict[str, Any]] = []
    for sheet_name in xl.sheet_names:
        slug = _sheet_slug(sheet_name)
        if not slug:
            continue
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name)
        if df.empty:
            continue
        columns = list(df.columns)
        parser = _parse_drylog_row if slug == "drylog" else _parse_chandris_row
        for _, row in df.iterrows():
            parsed = parser(row, columns)
            if parsed:
                parsed["company_slug"] = slug
                parsed["sheet"] = sheet_name
                rows_out.append(parsed)
    if not rows_out:
        raise SalaryScaleXlsxImportError(
            "Нет данных: ожидаются листы DryLog и Chandris (как в Salary Scale.xlsx)"
        )
    return rows_out


def import_salary_scale_xlsx(
    db: Session,
    content: bytes,
    *,
    company_slugs: set[str] | None = None,
) -> dict[str, Any]:
    """Upsert salary_component_templates from workbook. Returns summary stats."""
    parsed_rows = parse_workbook_bytes(content)
    if company_slugs:
        parsed_rows = [r for r in parsed_rows if r["company_slug"] in company_slugs]

    companies_by_slug = {c.slug: c for c in db.query(Company).all() if c.slug}
    created = 0
    updated = 0
    skipped: list[str] = []
    details: list[dict[str, Any]] = []

    for row in parsed_rows:
        slug = row["company_slug"]
        company = companies_by_slug.get(slug)
        if not company:
            skipped.append(f"{slug}: компания не найдена в CRM")
            continue
        rank = row["rank"]
        existing = (
            db.query(SalaryComponentTemplate)
            .filter(
                SalaryComponentTemplate.company_id == company.company_id,
                SalaryComponentTemplate.rank == rank,
            )
            .one_or_none()
        )
        fields = {
            "basic_monthly_wage": row["basic_monthly_wage"],
            "monthly_overtime": row["monthly_overtime"],
            "overtime_rate": row["overtime_rate"],
            "sepf": row["sepf"],
            "imtf": row["imtf"],
            "leave": row["leave"],
            "leave_sub": row["leave_sub"],
            "various_extra_overtime": row["various_extra_overtime"],
            "updated_at": datetime.utcnow(),
        }
        if existing:
            for key, val in fields.items():
                setattr(existing, key, val)
            updated += 1
            action = "updated"
        else:
            db.add(
                SalaryComponentTemplate(
                    company_id=company.company_id,
                    rank=rank,
                    **fields,
                )
            )
            created += 1
            action = "created"
        details.append(
            {
                "company": company.name,
                "rank": rank,
                "action": action,
                "fixed_total": round(
                    sum(
                        fields[k]
                        for k in (
                            "basic_monthly_wage",
                            "monthly_overtime",
                            "sepf",
                            "imtf",
                            "leave",
                            "leave_sub",
                            "various_extra_overtime",
                        )
                    ),
                    2,
                ),
            }
        )

    db.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "rows": details,
    }
