"""One-off: dump Century main-table rows mentioning parents / total sea (debug)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document as DocxDocument

from synonyms import normalize_label

# Allow: python scripts/debug_century_row_dump.py <docx> [--all]
#        python scripts/debug_century_row_dump.py --parse <docx>


def norm_cell(t: str) -> str:
    return normalize_label(t)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--all"]
    if args and args[0] == "--parse":
        from parser.docx_parser import DocxParser

        p = Path(args[1])
        r = DocxParser().parse(p)
        pd = r.get("personal_data") or {}
        keys = (
            "father_name",
            "mother_name",
            "total_sea_service",
            "total_sea_service_in_rank",
            "total_years_of_sea_service",
        )
        print(json.dumps({k: pd.get(k) for k in keys}, ensure_ascii=False, indent=2))
        return

    path = Path(args[0]) if args else Path("tests/2O Volkov CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx")
    doc = DocxDocument(str(path))
    for ti, table in enumerate(doc.tables):
        blob = " ".join(norm_cell(c.text) for r in table.rows for c in r.cells)
        if "seaman s personal details" not in blob:
            continue
        print("table", ti, "rows", len(table.rows))
        for ri, row in enumerate(table.rows):
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            line = " | ".join(cells)
            low = " ".join(norm_cell(c) for c in cells if c.strip())
            if "--all" in sys.argv[1:]:
                print(ri, line[:300])
                continue
            if any(
                k in low
                for k in (
                    "father",
                    "mother",
                    "total sea",
                    "sea service in rank",
                    "previous sea",
                )
            ):
                print(ri, line[:500])
        break


if __name__ == "__main__":
    main()
