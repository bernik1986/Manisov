"""Import companies and vessels from Excel (Vessels.xlsx layout) into Company manager tables."""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models.schema import Company, CompanyFolder, Vessel

EXCEL_COLUMNS_HINT = "Company, IMO, Vessel name"


class CompaniesXlsxImportError(ValueError):
    """Invalid or unreadable companies/vessels workbook."""


def slugify_entity_name(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "item"


def unique_company_slug(db: Session, base_slug: str, exclude_company_id: int | None = None) -> str:
    slug = base_slug
    suffix = 2
    while True:
        query = db.query(Company).filter(Company.slug == slug)
        if exclude_company_id is not None:
            query = query.filter(Company.company_id != exclude_company_id)
        if query.first() is None:
            return slug
        slug = f"{base_slug}_{suffix}"
        suffix += 1


def unique_vessel_slug(
    db: Session, company_id: int, base_slug: str, exclude_vessel_id: int | None = None
) -> str:
    slug = base_slug
    suffix = 2
    while True:
        query = db.query(Vessel).filter(Vessel.company_id == company_id, Vessel.slug == slug)
        if exclude_vessel_id is not None:
            query = query.filter(Vessel.vessel_id != exclude_vessel_id)
        if query.first() is None:
            return slug
        slug = f"{base_slug}_{suffix}"
        suffix += 1


def _cell_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).replace("\xa0", " ").strip()


def parse_workbook_bytes(content: bytes) -> tuple[list[str], list[dict[str, str | None]]]:
    if not content:
        raise CompaniesXlsxImportError("Файл пустой")
    try:
        df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise CompaniesXlsxImportError(f"Не удалось прочитать Excel: {exc}") from exc
    if df.empty:
        raise CompaniesXlsxImportError(f"В файле нет строк. Ожидаются колонки: {EXCEL_COLUMNS_HINT}")

    companies: list[str] = []
    current: str | None = None
    vessels: list[dict[str, str | None]] = []

    for _, row in df.iterrows():
        company_name = _cell_str(row.get("Company"))
        imo = _cell_str(row.get("IMO")) or None
        name = _cell_str(row.get("Vessel name"))

        if company_name:
            current = company_name
            if current not in companies:
                companies.append(current)

        if not name and not imo:
            continue
        if not current:
            continue

        vessels.append(
            {
                "company": current,
                "name": name or (f"Vessel {imo}" if imo else "Unknown"),
                "imo": imo,
            }
        )

    if not companies and not vessels:
        raise CompaniesXlsxImportError(
            f"Не найдено компаний и судов. Проверьте колонки: {EXCEL_COLUMNS_HINT}"
        )

    return companies, vessels


def get_or_create_company(db: Session, *, folder_id: int, name: str) -> tuple[Company, bool]:
    existing = (
        db.query(Company).filter(Company.folder_id == folder_id, Company.name == name).one_or_none()
    )
    if existing:
        return existing, False

    base_slug = slugify_entity_name(name)
    slug = unique_company_slug(db, base_slug)
    company = Company(folder_id=folder_id, name=name, slug=slug)
    db.add(company)
    db.flush()
    return company, True


def vessel_exists(db: Session, *, company_id: int, name: str, imo: str | None) -> bool:
    query = db.query(Vessel).filter(Vessel.company_id == company_id)
    if imo:
        match = query.filter(Vessel.imo == imo).first()
        if match:
            return True
    return query.filter(Vessel.name == name).first() is not None


def import_companies_vessels_from_bytes(
    db_session: Session,
    content: bytes,
    *,
    folder_id: int,
) -> dict[str, int]:
    companies_order, vessels = parse_workbook_bytes(content)
    stats = {
        "companies_created": 0,
        "companies_existing": 0,
        "vessels_created": 0,
        "vessels_skipped": 0,
        "companies_total": len(companies_order),
        "vessels_total": len(vessels),
    }

    folder = db_session.get(CompanyFolder, folder_id)
    if not folder:
        raise CompaniesXlsxImportError(f"Папка {folder_id} не найдена")

    company_by_name: dict[str, Company] = {}

    for name in companies_order:
        company, created = get_or_create_company(db_session, folder_id=folder_id, name=name)
        company_by_name[name] = company
        if created:
            stats["companies_created"] += 1
        else:
            stats["companies_existing"] += 1

    for item in vessels:
        company = company_by_name.get(item["company"])
        if not company:
            continue
        name = item["name"] or "Unknown"
        imo = item["imo"]
        if vessel_exists(db_session, company_id=company.company_id, name=name, imo=imo):
            stats["vessels_skipped"] += 1
            continue
        base_slug = slugify_entity_name(name)
        slug = unique_vessel_slug(db_session, company.company_id, base_slug)
        db_session.add(
            Vessel(
                company_id=company.company_id,
                name=name,
                slug=slug,
                imo=imo,
                flag=None,
                vessel_type=None,
            )
        )
        stats["vessels_created"] += 1

    db_session.commit()
    return stats
