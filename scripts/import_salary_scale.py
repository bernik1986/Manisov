#!/usr/bin/env python3
"""One-shot CLI: import Salary Scale.xlsx into salary_component_templates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.salary_scale_xlsx_import import import_salary_scale_xlsx  # noqa: E402
from models.db import SessionLocal, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import salary matrix from Excel")
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path(r"C:\Users\berni\Downloads\Salary Scale.xlsx"),
        help="Path to Salary Scale.xlsx",
    )
    parser.add_argument(
        "--company",
        action="append",
        dest="companies",
        help="Limit to company slug(s), e.g. drylog chandris",
    )
    args = parser.parse_args()
    path = args.path
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    init_db()
    content = path.read_bytes()
    slugs = set(args.companies) if args.companies else None
    db = SessionLocal()
    try:
        result = import_salary_scale_xlsx(db, content, company_slugs=slugs)
    finally:
        db.close()

    print(f"Created: {result['created']}, updated: {result['updated']}")
    if result["skipped"]:
        for msg in result["skipped"]:
            print(f"Skipped: {msg}")
    for row in result["rows"]:
        print(f"  [{row['action']}] {row['company']} / {row['rank']} — fixed ${row['fixed_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
