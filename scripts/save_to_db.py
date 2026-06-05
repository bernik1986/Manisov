from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
from typing import Any

from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.db import get_session, init_db
from models.schema import Candidate, Certificate, Document, FamilyContact, SeaService
from parser.base import BaseParser
from parser.crewwell_pdf_parser import CrewwellPDFParser
from parser.docx_parser import DocxParser
from parser.excel_parser import ExcelParser
from parser.pdf_parser import PDFParser


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


def _select_parser(path: Path) -> BaseParser:
    ext = path.suffix.lower()
    if ext in {".docx", ".doc"}:
        return DocxParser()
    if ext in {".xlsx", ".xls"}:
        return ExcelParser()
    if ext == ".pdf":
        if any("crewwell" in part.lower() for part in path.parts):
            return CrewwellPDFParser()
        return PDFParser()
    raise ValueError(f"Unsupported file extension: {ext or 'unknown'}")


def parse_file(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    parser = _select_parser(path)
    return parser.parse(path)


def save_candidate(data: dict[str, Any], session: Session) -> Candidate:
    personal = data.get("personal_data", {}) or {}
    documents = data.get("documents", []) or []
    certificates = data.get("certificates", []) or []
    sea_service = data.get("sea_service", []) or []
    family_contacts = data.get("family_contacts", []) or []

    candidate: Candidate | None = None
    candidate_id = personal.get("candidate_id")
    if candidate_id not in (None, ""):
        try:
            candidate = session.get(Candidate, int(candidate_id))
        except (TypeError, ValueError):
            candidate = None

    if candidate is None:
        surname = personal.get("surname")
        dob = _to_date(personal.get("date_of_birth"))
        if surname and dob:
            candidate = (
                session.query(Candidate)
                .filter(Candidate.surname == str(surname), Candidate.date_of_birth == dob)
                .one_or_none()
            )

    if candidate is None:
        candidate = Candidate()
        session.add(candidate)

    candidate_columns = {column.name for column in Candidate.__table__.columns}
    for key, value in personal.items():
        if key not in candidate_columns or key == "candidate_id":
            continue
        if key in {"date_of_birth", "passport_issue_date", "passport_expiry_date"}:
            setattr(candidate, key, _to_date(value))
        else:
            setattr(candidate, key, value)

    session.flush()

    session.query(Document).filter(Document.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
    session.query(Certificate).filter(Certificate.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
    session.query(SeaService).filter(SeaService.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
    session.query(FamilyContact).filter(FamilyContact.candidate_id == candidate.candidate_id).delete(synchronize_session=False)

    doc_columns = {column.name for column in Document.__table__.columns}
    cert_columns = {column.name for column in Certificate.__table__.columns}
    service_columns = {column.name for column in SeaService.__table__.columns}
    family_columns = {column.name for column in FamilyContact.__table__.columns}

    for raw in documents:
        payload = {k: v for k, v in raw.items() if k in doc_columns}
        payload["candidate_id"] = candidate.candidate_id
        if "document_type" not in payload:
            payload["document_type"] = raw.get("document_type") or "Unknown document"
        for date_key in ("date_of_issue", "date_of_expiry"):
            if date_key in payload:
                payload[date_key] = _to_date(payload[date_key])
        session.add(Document(**payload))

    for raw in certificates:
        payload = {k: v for k, v in raw.items() if k in cert_columns}
        payload["candidate_id"] = candidate.candidate_id
        if "certificate_type" not in payload:
            payload["certificate_type"] = raw.get("certificate_type") or "Unknown certificate"
        for date_key in ("date_issued", "expiry_date"):
            if date_key in payload:
                payload[date_key] = _to_date(payload[date_key])
        session.add(Certificate(**payload))

    for raw in sea_service:
        payload = {k: v for k, v in raw.items() if k in service_columns}
        payload["candidate_id"] = candidate.candidate_id
        for date_key in ("sign_on_date", "sign_off_date"):
            if date_key in payload:
                payload[date_key] = _to_date(payload[date_key])
        session.add(SeaService(**payload))

    for raw in family_contacts:
        payload = {k: v for k, v in raw.items() if k in family_columns}
        payload["candidate_id"] = candidate.candidate_id
        if "full_name" not in payload:
            payload["full_name"] = raw.get("full_name") or "Unknown contact"
        session.add(FamilyContact(**payload))

    session.commit()
    session.refresh(candidate)
    return candidate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse one file and save candidate payload into database")
    parser.add_argument("file_path", help="Path to questionnaire file")
    args = parser.parse_args()

    init_db()
    parsed = parse_file(args.file_path)

    session_gen = get_session()
    session = next(session_gen)
    try:
        candidate = save_candidate(parsed, session)
        print(f"Saved candidate_id={candidate.candidate_id}")
    finally:
        session_gen.close()
