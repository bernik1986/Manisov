"""Import companies and vessels from Vessels.xlsx into Company manager tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.companies_xlsx_import import import_companies_vessels_from_bytes  # noqa: E402
from models.db import SessionLocal, init_db  # noqa: E402
from models.schema import CompanyFolder  # noqa: E402


def _get_or_create_companies_root(db) -> CompanyFolder:
    root = db.query(CompanyFolder).filter(CompanyFolder.parent_id.is_(None)).one_or_none()
    if root:
        return root
    root = CompanyFolder(name="Companies", parent_id=None)
    db.add(root)
    db.flush()
    return root


def import_data(path: Path, *, dry_run: bool = False) -> dict[str, int]:
    content = path.read_bytes()
    if dry_run:
        from app.companies_xlsx_import import parse_workbook_bytes

        companies_order, vessels = parse_workbook_bytes(content)
        return {
            "companies_total": len(companies_order),
            "vessels_total": len(vessels),
            "companies_created": 0,
            "companies_existing": 0,
            "vessels_created": 0,
            "vessels_skipped": 0,
        }

    init_db()
    db = SessionLocal()
    try:
        root = _get_or_create_companies_root(db)
        return import_companies_vessels_from_bytes(db, content, folder_id=root.folder_id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import vessels from Excel into Company manager")
    parser.add_argument(
        "xlsx",
        nargs="?",
        default=str(Path.home() / "Downloads" / "Vessels.xlsx"),
        help="Path to Vessels.xlsx",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse only, do not write to DB")
    args = parser.parse_args()
    path = Path(args.xlsx)
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    stats = import_data(path, dry_run=args.dry_run)
    print(stats)


if __name__ == "__main__":
    main()
