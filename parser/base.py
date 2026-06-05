from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from synonyms import get_canonical_field, normalize_label

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Base parser contract and shared field-mapping helpers."""

    SUPPORTED_FORMATS = {".pdf", ".doc", ".docx", ".xlsx", ".xls", ".csv"}
    REQUIRED_LIST_SECTIONS = (
        "documents",
        "certificates",
        "sea_service",
        "applications",
        "flag_documents",
        "family_contacts",
        "uploaded_files",
    )
    _PERSONAL_DATE_FIELDS = {
        "date_of_birth",
        "passport_issue_date",
        "passport_expiry_date",
        "medical_fitness_issue_date",
        "medical_fitness_expiry_date",
        "yellow_fever_issue_date",
        "yellow_fever_expiry_date",
        "usa_visa_issue_date",
        "usa_visa_expiry_date",
        "date_applied",
        "date_available",
    }
    _SECTION_DATE_FIELDS = {
        "documents": {"date_of_issue", "date_of_expiry", "expiry_date"},
        "certificates": {"date_issued", "expiry_date"},
        "sea_service": {"sign_on_date", "sign_off_date"},
        "applications": {"date_applied", "date_available"},
        "flag_documents": {"date_of_issuance", "date_of_expiry"},
    }

    @abstractmethod
    def parse(self, file_path: str | Path) -> dict[str, Any]:
        """Parse file and return normalized CRM payload."""

    @staticmethod
    def empty_result() -> dict[str, Any]:
        return {
            "personal_data": {},
            "documents": [],
            "certificates": [],
            "sea_service": [],
            "applications": [],
            "flag_documents": [],
            "family_contacts": [],
            "uploaded_files": [],
        }

    @classmethod
    def ensure_result_contract(cls, payload: dict[str, Any] | None) -> dict[str, Any]:
        """Return parser payload with mandatory top-level sections."""
        result = dict(payload or {})
        personal_data = result.get("personal_data")
        result["personal_data"] = personal_data if isinstance(personal_data, dict) else {}
        for section in cls.REQUIRED_LIST_SECTIONS:
            value = result.get(section)
            result[section] = value if isinstance(value, list) else []
        cls._normalize_result_dates(result)
        return result

    @classmethod
    def _normalize_result_dates(cls, result: dict[str, Any]) -> None:
        for key in cls._PERSONAL_DATE_FIELDS:
            value = result["personal_data"].get(key)
            if isinstance(value, str):
                result["personal_data"][key] = cls._normalize_date_string(value)

        for section, fields in cls._SECTION_DATE_FIELDS.items():
            for item in result.get(section, []):
                if not isinstance(item, dict):
                    continue
                for key in fields:
                    value = item.get(key)
                    if isinstance(value, str):
                        item[key] = cls._normalize_date_string(value)

    @staticmethod
    def _normalize_date_string(value: str) -> str | None:
        raw = value.strip()
        if not raw:
            return value
        if raw.lower() in {"-", "--", "n/a", "na", "none", "unlimited", "no expiry", "without expiry"}:
            return None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        return value

    def detect_format(self, file_path: str | Path) -> str:
        """Detect file extension and ensure it is supported."""
        path = Path(file_path)
        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {extension or 'unknown'}")
        return extension

    def normalize_field_label(self, label: str) -> str:
        """Normalize incoming raw field label."""
        return normalize_label(label)

    def map_to_canonical_field(self, label: str) -> str | None:
        """Map raw field label to canonical CRM field name."""
        return get_canonical_field(label)

    def map_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Map raw key/value payload to canonical fields.

        Unknown keys are ignored, known keys are copied as-is.
        """
        mapped: dict[str, Any] = {}
        for raw_key, value in data.items():
            canonical = self.map_to_canonical_field(raw_key)
            if canonical:
                mapped[canonical] = value
            else:
                logger.warning("Unparsed field label: '%s'", raw_key)
        return mapped
