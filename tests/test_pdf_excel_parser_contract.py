from __future__ import annotations

from pathlib import Path

import pandas as pd

from parser.excel_parser import ExcelParser
from parser.pdf_parser import PDFParser


def _assert_parser_result_contract(result: dict) -> None:
    assert "personal_data" in result
    assert isinstance(result["personal_data"], dict)
    for key in (
        "documents",
        "certificates",
        "sea_service",
        "applications",
        "flag_documents",
        "family_contacts",
        "uploaded_files",
    ):
        assert key in result
        assert isinstance(result[key], list)


def _write_minimal_pdf(path: Path) -> None:
    # Small valid one-page PDF with no extractable text.
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000056 00000 n \n"
        b"0000000113 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n170\n%%EOF\n"
    )


def test_pdf_parser_returns_contract_on_minimal_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "minimal.pdf"
    _write_minimal_pdf(pdf_path)

    parser = PDFParser()
    result = parser.parse(pdf_path)

    _assert_parser_result_contract(result)


def test_excel_parser_returns_contract_on_minimal_workbook(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "minimal.xlsx"
    df = pd.DataFrame(
        [
            ["Surname", "Petrov"],
            ["First Name", "Ivan"],
            ["Date of Birth", "1992-02-10"],
        ]
    )
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Sheet1")

    parser = ExcelParser()
    result = parser.parse(xlsx_path)

    _assert_parser_result_contract(result)
    assert result["personal_data"].get("first_name") == "Ivan"
