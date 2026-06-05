from __future__ import annotations

from app.canonical_visas import (
    CANONICAL_VISA_SPECS,
    apply_canonical_visa_placeholders,
    deduplicate_canonical_visa_rows,
    document_is_visa,
    ensure_canonical_visas,
    order_visas_for_response,
    partition_documents_and_visas,
    visa_matches_spec,
)
from models.db import Base, SessionLocal, engine, init_db
from models.schema import Candidate, Document


def test_visa_matches_legacy_usa_visa_type():
    spec = CANONICAL_VISA_SPECS[0]
    assert visa_matches_spec({"document_type": "USA Visa"}, spec)


def test_partition_documents_and_visas():
    docs = [
        {"document_id": 1, "document_type": "Travel Passport"},
        {"document_id": 2, "document_type": "USA Visa", "document_number": "V1"},
    ]
    non_visa, visas = partition_documents_and_visas(docs)
    assert len(non_visa) == 1
    assert len(visas) == 1
    assert document_is_visa(visas[0])


def test_ensure_canonical_visas_creates_rows():
    init_db()
    session = SessionLocal()
    try:
        candidate = Candidate(surname="Visa", first_name="Test", current_rank="CO")
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        added = ensure_canonical_visas(session, candidate.candidate_id)
        assert added is True
        rows = session.query(Document).filter(Document.candidate_id == candidate.candidate_id).all()
        assert len(rows) == len(CANONICAL_VISA_SPECS)
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_apply_canonical_visa_placeholders():
    context = {
        "visas": [
            {
                "document_id": 1,
                "document_type": "USA Visa",
                "document_number": "VISA-1",
                "date_of_issue": "2020-01-01",
            }
        ]
    }
    apply_canonical_visa_placeholders(context)
    assert context["usa_visa_document_number"] == "VISA-1"
    assert context["usa_visa_issue_date"] == "2020-01-01"
    assert context["usa_visa_number"] == "VISA-1"


def test_deduplicate_legacy_usa_visa_and_empty_slot():
    init_db()
    session = SessionLocal()
    try:
        candidate = Candidate(surname="Dup", first_name="Visa", current_rank="CO")
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        session.add(
            Document(
                candidate_id=candidate.candidate_id,
                document_type="USA Visa",
                document_number="US123",
            )
        )
        session.add(
            Document(
                candidate_id=candidate.candidate_id,
                document_category="Visa USA",
                document_type="Visa USA",
            )
        )
        session.commit()

        assert deduplicate_canonical_visa_rows(session, candidate.candidate_id) is True
        rows = session.query(Document).filter(Document.candidate_id == candidate.candidate_id).all()
        assert len(rows) == 1
        assert rows[0].document_number == "US123"
        assert rows[0].document_type == "Visa USA"
        assert rows[0].document_category == "Visa USA"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_order_visas_for_response_no_duplicate_usa_visa():
    ordered = order_visas_for_response(
        [
            {
                "document_id": 1,
                "document_category": "Visa USA",
                "document_type": "Visa USA",
            },
            {
                "document_id": 2,
                "document_type": "USA Visa",
                "document_number": "US-99",
            },
        ]
    )
    usa_rows = [row for row in ordered if row.get("visa_code") == "Visa USA"]
    assert len(usa_rows) == 1
    assert usa_rows[0]["document_number"] == "US-99"


def test_order_visas_for_response_includes_parser_row():
    ordered = order_visas_for_response(
        [
            {
                "document_id": 10,
                "document_type": "Visa Canada",
                "document_category": "Visa Canada",
                "document_number": "CA-1",
            }
        ]
    )
    canada = next(row for row in ordered if row.get("visa_code") == "Visa Canada")
    assert canada["document_number"] == "CA-1"
