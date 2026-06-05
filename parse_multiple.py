from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from models.db import get_session, init_db
from models.schema import Candidate
from parser.base import BaseParser
from parser.crewwell_pdf_parser import CrewwellPDFParser
from parser.docx_parser import DocxParser
from parser.excel_parser import ExcelParser
from parser.pdf_parser import PDFParser

SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".xls", ".pdf"}


def _select_parser(file_path: Path) -> BaseParser:
    extension = file_path.suffix.lower()
    if extension == ".docx":
        return DocxParser()
    if extension in {".xlsx", ".xls"}:
        return ExcelParser()
    if extension == ".pdf":
        if any("crewwell" in part.lower() for part in file_path.parts):
            return CrewwellPDFParser()
        return PDFParser()
    raise ValueError(f"Unsupported file type: {extension or 'unknown'}")


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _find_existing_candidate(parsed_data: dict[str, Any], session: Any) -> Candidate | None:
    personal = parsed_data.get("personal_data", {}) or {}

    candidate_id = personal.get("candidate_id")
    if candidate_id not in (None, ""):
        try:
            existing = session.get(Candidate, int(candidate_id))
            if existing is not None:
                return existing
        except (TypeError, ValueError):
            pass

    surname = personal.get("surname")
    dob = _to_date(personal.get("date_of_birth"))
    if surname and dob:
        return (
            session.query(Candidate)
            .filter(Candidate.surname == str(surname), Candidate.date_of_birth == dob)
            .one_or_none()
        )
    return None


def _save_with_parser(
    parser: BaseParser,
    parsed_data: dict[str, Any],
    session: Any,
) -> tuple[Candidate, bool]:
    existing = _find_existing_candidate(parsed_data, session)
    is_created = existing is None

    if hasattr(parser, "_map_and_save_to_db"):
        candidate = parser._map_and_save_to_db(parsed_data, session)  # type: ignore[attr-defined]
        return candidate, is_created

    # Fallback for parsers without DB mapping method.
    candidate = existing if existing is not None else Candidate()
    if existing is None:
        session.add(candidate)

    personal = parsed_data.get("personal_data", {}) or {}
    candidate_columns = {column.name for column in Candidate.__table__.columns}
    for key, value in personal.items():
        if key in candidate_columns and key != "candidate_id":
            setattr(candidate, key, _to_date(value) if key.endswith("_date") else value)

    session.commit()
    session.refresh(candidate)
    return candidate, is_created


def parse_directory(directory: str | Path) -> dict[str, int]:
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Directory does not exist: {root}")

    init_db()
    created = 0
    updated = 0
    errors = 0
    processed = 0

    files = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
    print(f"Found {len(files)} candidate files in: {root}")

    session_generator = get_session()
    session = next(session_generator)
    try:
        for index, file_path in enumerate(files, start=1):
            print(f"[{index}/{len(files)}] Processing: {file_path.name}")
            try:
                parser = _select_parser(file_path)
                parsed_data = parser.parse(file_path)
                candidate, is_created = _save_with_parser(parser, parsed_data, session)
                processed += 1
                if is_created:
                    created += 1
                    print(f"  -> created candidate_id={candidate.candidate_id}")
                else:
                    updated += 1
                    print(f"  -> updated candidate_id={candidate.candidate_id}")
            except Exception as exc:
                errors += 1
                print(f"  -> error: {exc}")
    finally:
        session_generator.close()

    summary = {"processed": processed, "created": created, "updated": updated, "errors": errors}
    print(
        "Completed. "
        f"processed={summary['processed']}, created={summary['created']}, "
        f"updated={summary['updated']}, errors={summary['errors']}"
    )
    return summary


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Parse multiple maritime questionnaires into SQLite DB")
    arg_parser.add_argument("directory", help="Path to directory containing questionnaires")
    args = arg_parser.parse_args()
    parse_directory(args.directory)
