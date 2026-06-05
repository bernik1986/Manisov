from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    # Windows console often defaults to cp1252; make output resilient for Cyrillic paths.
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from parser.base import BaseParser
from parser.crewwell_pdf_parser import CrewwellPDFParser
from parser.docx_parser import DocxParser
from parser.excel_parser import ExcelParser
from parser.pdf_parser import PDFParser

# Traverse these extensions; `.doc` / `.csv` handled before parsers (skipped, no ошибка).
SUPPORTED_EXTS = {".pdf", ".doc", ".docx", ".xlsx", ".xls", ".csv"}

SKIP_LEGACY_DOC = "skipped_legacy_doc"
SKIP_LEGACY_DOC_RU = "Пропуск: старый .doc без конвертации (LibreOffice soffice не используется)."
SKIP_CSV = "skipped_csv_no_parser"
SKIP_CSV_RU = "Пропуск: .csv пока без отдельного парсера (в проекте только xls/xlsx/excel)."


def _select_parser(path: Path) -> BaseParser:
    ext = path.suffix.lower()
    if ext == ".docx":
        return DocxParser()
    if ext in {".xlsx", ".xls"}:
        return ExcelParser()
    if ext == ".pdf":
        if any("crewwell" in part.lower() for part in path.parts):
            return CrewwellPDFParser()
        return PDFParser()
    raise ValueError(f"Unsupported file extension for direct parse: {ext or 'unknown'}")


def _iter_input_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTS else []
    if root.is_dir():
        return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    return []


def _safe_preview_personal(personal: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "source_form_type",
        "surname",
        "first_name",
        "full_name",
        "date_of_birth",
        "father_name",
        "mother_name",
        "total_sea_service",
        "total_sea_service_in_rank",
        "total_years_of_sea_service",
    )
    return {k: personal.get(k) for k in keys if k in personal}


def _non_empty_personal_values(personal: dict[str, Any]) -> int:
    n = 0
    for v in personal.values():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        n += 1
    return n


def _progress_line(idx: int, total: int, ok: int, skipped: int, bad: int, json_mode: bool) -> None:
    line = f"progress {idx}/{total} ok={ok} skipped={skipped} bad={bad}"
    if json_mode:
        print(line, file=sys.stderr, flush=True)
    else:
        print(line, flush=True)


def _is_low_yield(result: dict[str, Any]) -> bool:
    """Heuristic: parse succeeded but almost nothing extracted (worth checking synonyms/layout)."""
    personal = result.get("personal_data") if isinstance(result.get("personal_data"), dict) else {}
    list_total = sum(len(result.get(k) or []) for k in BaseParser.REQUIRED_LIST_SECTIONS)
    return _non_empty_personal_values(personal) <= 1 and list_total == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke-run parsers on folders/files; .doc skipped without conversion")
    ap.add_argument("paths", nargs="+", help="Files or folders to parse recursively")
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of files (0 = no limit)")
    ap.add_argument(
        "--report-low-yield",
        action="store_true",
        help="Include files that parsed OK but yielded almost empty data (check synonyms/forms)",
    )
    args = ap.parse_args()

    roots = [Path(p) for p in args.paths]
    missing = [str(p) for p in roots if not p.exists()]

    files: list[Path] = []
    for root in roots:
        files.extend(_iter_input_files(root))
    files = sorted(set(files), key=lambda p: str(p).lower())
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    ok = 0
    skipped = 0
    bad = 0
    skipped_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    low_yield: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for idx, fp in enumerate(files, 1):
        ext = fp.suffix.lower()
        if ext == ".doc":
            skipped += 1
            skipped_records.append(
                {
                    "file": str(fp),
                    "reason_code": SKIP_LEGACY_DOC,
                    "message": SKIP_LEGACY_DOC_RU,
                }
            )
            if idx % 25 == 0:
                _progress_line(idx, len(files), ok, skipped, bad, args.json)
            continue

        if ext == ".csv":
            skipped += 1
            skipped_records.append({"file": str(fp), "reason_code": SKIP_CSV, "message": SKIP_CSV_RU})
            if idx % 25 == 0:
                _progress_line(idx, len(files), ok, skipped, bad, args.json)
            continue

        try:
            parser = _select_parser(fp)
            parsed = parser.parse(fp)
            result = BaseParser.ensure_result_contract(parsed)
            personal = result.get("personal_data") or {}
            if args.report_low_yield and _is_low_yield(result):
                low_yield.append(
                    {
                        "file": str(fp),
                        "parser": type(parser).__name__,
                        "non_empty_personal_fields": _non_empty_personal_values(personal),
                    }
                )
            samples.append(
                {
                    "file": str(fp),
                    "parser": type(parser).__name__,
                    "personal_preview": _safe_preview_personal(personal) if isinstance(personal, dict) else {},
                    "counts": {k: len(result.get(k) or []) for k in BaseParser.REQUIRED_LIST_SECTIONS},
                }
            )
            ok += 1
        except Exception as exc:
            bad += 1
            failures.append({"file": str(fp), "error_type": type(exc).__name__, "error": str(exc)})

        if idx % 25 == 0:
            _progress_line(idx, len(files), ok, skipped, bad, args.json)

    summary = {
        "missing_roots": missing,
        "total_files": len(files),
        "ok": ok,
        "skipped": skipped,
        "bad": bad,
        "skipped_files": skipped_records,
        "failures": failures,
        "samples": samples[:20],
    }
    if args.report_low_yield:
        summary["low_yield_warnings"] = low_yield

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("missing_roots", len(missing))
        for item in missing[:20]:
            print("  -", item)
        print("total_files", len(files))
        print("ok", ok, "skipped", skipped, "bad", bad)
        if skipped_records:
            ndoc = sum(1 for r in skipped_records if r.get("reason_code") == SKIP_LEGACY_DOC)
            ncsv = sum(1 for r in skipped_records if r.get("reason_code") == SKIP_CSV)
            print(f"skipped total {len(skipped_records)} (.doc={ndoc}, .csv={ncsv}); --json полный список; текстом первые 5:")
            for rec in skipped_records[:5]:
                short = rec["file"][:120] + ("…" if len(rec["file"]) > 120 else "")
                print("  -", rec.get("reason_code"), short)
        if failures:
            print("failures (first 30):")
            for f in failures[:30]:
                print("-", f["error_type"], f["file"])
                msg = (f.get("error") or "").replace("\n", " ")
                print("  ", msg[:240])
        if args.report_low_yield and low_yield:
            print("low_yield (first 20): возможно нужны синонимы или другая ветка парсера")
            for row in low_yield[:20]:
                print("  -", row["parser"], row["file"][:140])

    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
