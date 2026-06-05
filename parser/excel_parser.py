from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from parser.base import BaseParser


class ExcelParser(BaseParser):
    """Parser for XLS/XLSX files using pandas."""

    _SHEET_MARKERS: dict[str, str] = {
        "DOCUMENTS": "documents",
        "CERTIFICATES": "certificates",
        "SEA SERVICE": "sea_service",
    }

    def parse(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        extension = self.detect_format(path)
        if extension not in {".xls", ".xlsx"}:
            raise ValueError("ExcelParser supports only .xls/.xlsx files")

        result = self.empty_result()
        excel_data = pd.read_excel(path, sheet_name=None)

        for _, df in excel_data.items():
            parsed_sheet = self._parse_sheet(df)
            self._merge_results(result, parsed_sheet)

        return self.ensure_result_contract(result)

    def _parse_sheet(self, df: pd.DataFrame) -> dict[str, Any]:
        parsed = self.empty_result()
        if df.empty:
            return parsed

        section_name, marker_row = self._detect_marker_section(df)
        if section_name:
            parsed[section_name].extend(self._parse_marker_table(df, marker_row))
            return parsed

        parsed["personal_data"].update(self._parse_key_value_sheet(df))
        return parsed

    def _detect_marker_section(self, df: pd.DataFrame) -> tuple[str | None, int]:
        values = df.fillna("").astype(str).values.tolist()
        for row_idx, row in enumerate(values):
            for cell in row:
                cell_text = str(cell).strip().upper()
                if cell_text in self._SHEET_MARKERS:
                    return self._SHEET_MARKERS[cell_text], row_idx
        return None, -1

    def _parse_marker_table(self, df: pd.DataFrame, marker_row: int) -> list[dict[str, Any]]:
        values = df.fillna("").astype(str).values.tolist()
        header_row_idx = self._find_next_non_empty_row(values, marker_row + 1)
        if header_row_idx == -1:
            return []

        raw_headers = [cell.strip() for cell in values[header_row_idx]]
        canonical_headers = [self.map_to_canonical_field(header) if header else None for header in raw_headers]
        if not any(canonical_headers):
            return []

        rows: list[dict[str, Any]] = []
        for row in values[header_row_idx + 1 :]:
            if not any(str(cell).strip() for cell in row):
                continue
            item: dict[str, Any] = {}
            for idx, value in enumerate(row):
                cell_value = str(value).strip()
                if not cell_value:
                    continue
                canonical = canonical_headers[idx] if idx < len(canonical_headers) else None
                if canonical:
                    item[canonical] = cell_value
            if item:
                rows.append(item)
        return rows

    def _parse_key_value_sheet(self, df: pd.DataFrame) -> dict[str, Any]:
        personal: dict[str, Any] = {}
        values = df.fillna("").astype(str).values.tolist()

        for row in values:
            cleaned = [str(cell).strip() for cell in row]
            if not any(cleaned):
                continue

            # Try common "field - value" shape across row pairs.
            for idx in range(0, len(cleaned) - 1, 2):
                raw_key = cleaned[idx]
                raw_value = cleaned[idx + 1]
                if not raw_key or not raw_value:
                    continue
                canonical = self.map_to_canonical_field(raw_key)
                if canonical:
                    personal[canonical] = raw_value

            # Fallback for rows that look like "field, value, ...".
            if len(cleaned) >= 2:
                raw_key = cleaned[0]
                raw_value = cleaned[1]
                canonical = self.map_to_canonical_field(raw_key)
                if canonical and raw_value:
                    personal[canonical] = raw_value

        return personal

    @staticmethod
    def _find_next_non_empty_row(rows: list[list[str]], start_idx: int) -> int:
        for idx in range(start_idx, len(rows)):
            if any(str(cell).strip() for cell in rows[idx]):
                return idx
        return -1

    def _merge_results(self, target: dict[str, Any], source: dict[str, Any]) -> None:
        target["personal_data"].update(source["personal_data"])
        target["documents"].extend(source["documents"])
        target["certificates"].extend(source["certificates"])
        target["sea_service"].extend(source["sea_service"])
        target["applications"].extend(source["applications"])
        target["flag_documents"].extend(source["flag_documents"])
        target["family_contacts"].extend(source["family_contacts"])
        target["uploaded_files"].extend(source["uploaded_files"])
