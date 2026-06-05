from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Boolean, Date, Float, Integer

from models.db import SessionLocal, init_db
from models.schema import Application, Candidate, Certificate, Document, SeaService
from parser.docx_parser import DocxParser


PROVIDED_DOCX_FILES = [
    Path(
        r"g:\My Drive\Тестирование Костя\Для работы тестовые файлы\New folder\примеры входящих анкет для теста\Century\2O Ulianov CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx"
    ),
    Path(
        r"g:\My Drive\Тестирование Костя\Для работы тестовые файлы\New folder\примеры входящих анкет для теста\Century\2O Volkov CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx"
    ),
    Path(
        r"g:\My Drive\Тестирование Костя\Для работы тестовые файлы\New folder\примеры входящих анкет для теста\Century\2O Kasko CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx"
    ),
]


def _columns(model: Any) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _filter_model_data(data: dict[str, Any], model: Any) -> dict[str, Any]:
    valid = _columns(model)
    return {key: value for key, value in data.items() if key in valid}


def _coerce_model_types(data: dict[str, Any], model: Any) -> dict[str, Any]:
    """Align with app save path: Float/Integer/Boolean must not stay as human strings (e.g. '1 year 9 months')."""
    coerced: dict[str, Any] = {}
    model_columns = {column.name: column for column in model.__table__.columns}
    for key, value in data.items():
        column = model_columns.get(key)
        if column is None:
            continue
        if value in (None, ""):
            coerced[key] = None
            continue
        ctype = column.type
        if isinstance(ctype, Date) and isinstance(value, str):
            try:
                coerced[key] = date.fromisoformat(value)
            except ValueError:
                coerced[key] = value
            continue
        if isinstance(ctype, Float):
            coerced[key] = DocxParser._to_float(value)
            continue
        if isinstance(ctype, Integer):
            coerced[key] = DocxParser._to_int(value)
            continue
        if isinstance(ctype, Boolean):
            coerced[key] = DocxParser._to_bool(value)
            continue
        coerced[key] = value
    return coerced


def _persist_parsed_payload(parsed: dict[str, Any]) -> int:
    init_db()
    session = SessionLocal()
    try:
        candidate_data = _coerce_model_types(_filter_model_data(parsed["personal_data"], Candidate), Candidate)
        candidate = Candidate(**candidate_data)
        session.add(candidate)
        session.flush()

        for app in parsed["applications"]:
            app_data = _coerce_model_types(_filter_model_data(app, Application), Application)
            app_data["candidate_id"] = candidate.candidate_id
            session.add(Application(**app_data))

        for doc in parsed["documents"]:
            doc_data = _coerce_model_types(_filter_model_data(doc, Document), Document)
            doc_data["candidate_id"] = candidate.candidate_id
            if "document_type" not in doc_data:
                doc_data["document_type"] = doc.get("document_type") or "Unknown document"
            session.add(Document(**doc_data))

        for cert in parsed["certificates"]:
            cert_data = _coerce_model_types(_filter_model_data(cert, Certificate), Certificate)
            cert_data["candidate_id"] = candidate.candidate_id
            if "certificate_type" not in cert_data:
                cert_data["certificate_type"] = cert.get("certificate_type") or "Unknown certificate"
            session.add(Certificate(**cert_data))

        for service in parsed["sea_service"]:
            service_data = _coerce_model_types(_filter_model_data(service, SeaService), SeaService)
            service_data["candidate_id"] = candidate.candidate_id
            session.add(SeaService(**service_data))

        session.commit()
        return candidate.candidate_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.mark.parametrize("docx_path", PROVIDED_DOCX_FILES)
def test_provided_docx_extract_and_save(docx_path: Path) -> None:
    if not docx_path.exists():
        pytest.skip(f"File not available: {docx_path}")

    parser = DocxParser()
    parsed = parser.parse(docx_path)

    assert isinstance(parsed["personal_data"], dict)
    assert isinstance(parsed["documents"], list)
    assert isinstance(parsed["certificates"], list)
    assert isinstance(parsed["sea_service"], list)
    assert isinstance(parsed["applications"], list)

    candidate_id = _persist_parsed_payload(parsed)
    assert isinstance(candidate_id, int)
    assert candidate_id > 0
