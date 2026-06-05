from __future__ import annotations

from app.canonical_documents import (
    CANONICAL_DOCUMENT_SPECS,
    apply_canonical_document_placeholders,
    document_matches_spec,
    ensure_canonical_documents,
    order_documents_for_response,
)
from models.db import Base, SessionLocal, engine, init_db
from models.schema import Candidate, Document


def test_document_matches_parser_passport_to_tp_slot():
    tp_spec = CANONICAL_DOCUMENT_SPECS[2]
    tp_bio_spec = CANONICAL_DOCUMENT_SPECS[1]
    assert document_matches_spec({"document_type": "Passport"}, tp_spec)
    assert not document_matches_spec({"document_type": "Passport"}, CANONICAL_DOCUMENT_SPECS[6])
    assert document_matches_spec(
        {"document_type": "Travel Passport (Ukraine)", "document_category": "TP Bio"},
        tp_bio_spec,
    )
    assert not document_matches_spec({"document_type": "Travel Passport (Ukraine)"}, tp_spec)


def test_ensure_canonical_documents_creates_missing_rows():
    init_db()
    session = SessionLocal()
    try:
        candidate = Candidate(surname="Doc", first_name="Test", current_rank="CO")
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        session.add(
            Document(
                candidate_id=candidate.candidate_id,
                document_type="Passport",
                document_number="AB123",
            )
        )
        session.commit()

        added = ensure_canonical_documents(session, candidate.candidate_id)
        assert added is True

        rows = session.query(Document).filter(Document.candidate_id == candidate.candidate_id).all()
        assert len(rows) == len(CANONICAL_DOCUMENT_SPECS)

        ordered = order_documents_for_response(
            [
                {
                    "document_id": d.document_id,
                    "document_type": d.document_type,
                    "document_category": d.document_category,
                    "document_number": d.document_number,
                }
                for d in rows
            ]
        )
        assert len(ordered) == len(CANONICAL_DOCUMENT_SPECS)
        assert ordered[2]["document_number"] == "AB123"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_apply_canonical_document_placeholders_passport_alias():
    context = {
        "documents": [
            {
                "document_id": 1,
                "document_type": "Travel Passport",
                "document_number": "P-1",
                "date_of_issue": "2020-01-01",
            }
        ]
    }
    apply_canonical_document_placeholders(context)
    assert context["passport_number"] == "P-1"
