from __future__ import annotations

from models.schema import Candidate
from parser.base import BaseParser
from synonyms import _CANONICAL_TO_SYNONYMS


def test_base_parser_empty_result_contains_required_array_sections() -> None:
    result = BaseParser.empty_result()

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


def test_synonyms_cover_all_candidate_columns_except_system_fields() -> None:
    # company_id is an internal foreign key resolved from parsed company names,
    # not a field that external application forms should provide directly.
    system_fields = {"candidate_id", "company_id", "created_at", "updated_at"}
    candidate_columns = {column.name for column in Candidate.__table__.columns}
    mapped_columns = set(_CANONICAL_TO_SYNONYMS.keys())

    missing = sorted((candidate_columns - system_fields) - mapped_columns)
    assert missing == [], f"Missing synonym mappings for: {', '.join(missing)}"
