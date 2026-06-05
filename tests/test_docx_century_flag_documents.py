from __future__ import annotations

from pathlib import Path

import pytest

from parser.docx_parser import DocxParser

TESTS_DIR = Path(__file__).resolve().parent

CENTURY_BULKER_05A = sorted(TESTS_DIR.glob("*CENTURY*Bulker*CR-RT*05A*.docx"))

# These repo fixtures keep the D. FLAG DOCUMENTS headers but no filled data rows.
_EMPTY_FLAG_TABLE_NAMES = {
    "2O Dubinyak  CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx",
    "2O Yurchenko CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx",
    "3E Khmelevskyi CENTURY Bulker CR-RT 05A - Seaman's Application and Interview Record (3) (1).docx",
}


@pytest.mark.parametrize("docx_path", CENTURY_BULKER_05A, ids=lambda p: p.name)
def test_century_bulker_flag_documents_match_table(docx_path: Path) -> None:
    assert docx_path.is_file(), docx_path
    parser = DocxParser()
    result = parser.parse(docx_path)
    assert isinstance(result["flag_documents"], list)
    n = len(result["flag_documents"])
    if docx_path.name in _EMPTY_FLAG_TABLE_NAMES:
        assert n == 0, docx_path.name
        return

    assert n >= 1, docx_path.name
    fd0 = result["flag_documents"][0]
    assert fd0.get("flag_country")
    issue = fd0.get("date_of_issuance")
    expiry = fd0.get("date_of_expiry")
    assert isinstance(issue, str) or issue is None
    assert isinstance(expiry, str) or expiry is None
    doc_no = fd0.get("doc_number")
    if doc_no is not None:
        assert isinstance(doc_no, str)


def test_volkov_flag_documents_known_values() -> None:
    globs = list(TESTS_DIR.glob("*Volkov*CENTURY*Bulker*CR-RT*05A*.docx"))
    assert globs
    parser = DocxParser()
    result = parser.parse(globs[0])
    fds = result["flag_documents"]
    assert len(fds) >= 1
    fd0 = fds[0]
    assert "Malta" in fd0["flag_country"]
    assert fd0["date_of_issuance"] == "2021-02-08"
    assert fd0["date_of_expiry"] == "2025-06-23"
    assert "13308" in fd0.get("doc_number", "")
