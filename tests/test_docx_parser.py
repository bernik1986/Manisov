from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parser.docx_parser import DocxParser

# You can override these through environment variables when running pytest:
#   DOCX_SAMPLE_PATH
#   DOCX_EXPECTED_SURNAME
#   DOCX_EXPECTED_SEA_SERVICE_COUNT
DEFAULT_DOCX_PATH = Path(
    r"g:\My Drive\Тестирование Костя\Для работы тестовые файлы\New folder\примеры входящих анкет для теста\Century\2O Reshetov CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx"
)
EXPECTED_SURNAME = os.getenv("DOCX_EXPECTED_SURNAME", "Reshetov")
EXPECTED_SEA_SERVICE_COUNT = int(os.getenv("DOCX_EXPECTED_SEA_SERVICE_COUNT", "0"))


def _is_valid_iso_date(value: Any) -> bool:
    if value in (None, ""):
        return True
    if isinstance(value, date):
        return True
    if isinstance(value, str):
        try:
            date.fromisoformat(value.strip())
            return True
        except ValueError:
            return False
    return False


def _assert_dates_are_valid(payload: dict[str, Any]) -> None:
    # Personal data date fields
    for key in (
        "date_of_birth",
        "passport_issue_date",
        "passport_expiry_date",
        "date_applied",
        "date_available",
    ):
        assert _is_valid_iso_date(payload.get("personal_data", {}).get(key)), f"Invalid date in personal_data: {key}"

    # Documents date fields
    for item in payload.get("documents", []):
        for key in ("date_of_issue", "date_of_expiry", "expiry_date"):
            assert _is_valid_iso_date(item.get(key)), f"Invalid date in documents: {key}"

    # Certificates date fields
    for item in payload.get("certificates", []):
        for key in ("date_issued", "expiry_date"):
            assert _is_valid_iso_date(item.get(key)), f"Invalid date in certificates: {key}"

    # Sea service date fields
    for item in payload.get("sea_service", []):
        for key in ("sign_on_date", "sign_off_date"):
            assert _is_valid_iso_date(item.get(key)), f"Invalid date in sea_service: {key}"

    # Applications date fields
    for item in payload.get("applications", []):
        for key in ("date_applied", "date_available"):
            assert _is_valid_iso_date(item.get(key)), f"Invalid date in applications: {key}"


def test_docx_parser_reshetov_questionnaire() -> None:
    docx_path = Path(os.getenv("DOCX_SAMPLE_PATH", str(DEFAULT_DOCX_PATH)))
    if not docx_path.exists():
        pytest.skip(f"Sample questionnaire not found: {docx_path}")

    parser = DocxParser()
    parsed = parser.parse(docx_path)

    assert parsed["personal_data"].get("surname") == EXPECTED_SURNAME
    assert len(parsed["sea_service"]) == EXPECTED_SEA_SERVICE_COUNT
    _assert_dates_are_valid(parsed)
