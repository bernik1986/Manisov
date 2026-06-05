from __future__ import annotations

from app.canonical_certificates import (
    ALL_CANONICAL_CERTIFICATE_SPECS,
    CANONICAL_CONVENTIONAL_SPECS,
    apply_canonical_certificate_placeholders,
    certificate_matches_spec,
    ensure_canonical_certificates,
    is_canonical_certificate_record,
    order_certificates_for_response,
    parse_code_type,
)
from models.db import Base, SessionLocal, engine, init_db
from models.schema import Candidate, Certificate


def test_parse_code_type_with_and_without_dash():
    assert parse_code_type("Basic Safety - Proficiency in basic safety training") == (
        "Basic Safety",
        "Proficiency in basic safety training",
    )
    assert parse_code_type("Radar&ARPA") == ("Radar&ARPA", "Radar&ARPA")
    assert parse_code_type("PSSR – поправка к НБЖС") == ("PSSR", "поправка к НБЖС")


def test_certificate_matches_aff():
    spec = next(s for s in CANONICAL_CONVENTIONAL_SPECS if s["code"] == "AFF")
    assert certificate_matches_spec({"certificate_type": "Advanced Fire Fighting"}, spec)


def test_ensure_canonical_certificates_creates_slots():
    init_db()
    session = SessionLocal()
    try:
        candidate = Candidate(surname="Cert", first_name="Test", current_rank="CO")
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        session.add(
            Certificate(
                candidate_id=candidate.candidate_id,
                certificate_type="Advanced Fire Fighting",
                certificate_number="AFF-1",
            )
        )
        session.commit()

        changed = ensure_canonical_certificates(session, candidate.candidate_id)
        assert changed is True

        rows = session.query(Certificate).filter(Certificate.candidate_id == candidate.candidate_id).all()
        assert len(rows) == len(ALL_CANONICAL_CERTIFICATE_SPECS)

        aff = next(r for r in rows if r.certificate_name_raw == "AFF")
        assert aff.certificate_number == "AFF-1"
        assert aff.certificate_code == "AFF"
        assert aff.certificate_type == "Advanced fire fighting"
        assert aff.certificate_group == "Conventional Certificate"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_is_canonical_certificate_record():
    assert is_canonical_certificate_record({"certificate_type": "BRM — Bridge Resource Management"})
    assert not is_canonical_certificate_record({"certificate_type": "Random course"})


def test_parse_code_type_split():
    from app.canonical_certificates import parse_code_type

    assert parse_code_type("Basic Safety - Proficiency in basic safety training") == (
        "Basic Safety",
        "Proficiency in basic safety training",
    )
    assert parse_code_type("Medical Care") == ("Medical Care", "Medical Care")


def test_apply_canonical_certificate_placeholders_legacy():
    context = {
        "conventional_certificates": [
            {
                "certificate_id": 1,
                "certificate_name_raw": "AFF",
                "certificate_code": "AFF",
                "certificate_type": "Advanced fire fighting",
                "certificate_number": "X1",
                "date_issued": "2019-05-01",
            }
        ],
        "certificates": [],
    }
    apply_canonical_certificate_placeholders(context)
    assert context["aff_certificate_number"] == "X1"
    assert context["advanced_fire_fighting_document_number"] == "X1"


def test_order_certificates_for_response_placeholders():
    ordered = order_certificates_for_response([], CANONICAL_CONVENTIONAL_SPECS)
    assert len(ordered) == len(CANONICAL_CONVENTIONAL_SPECS)
    assert ordered[0]["is_canonical_placeholder"] is True
    assert ordered[0]["display_code"] == "Basic Safety"
    assert ordered[0]["display_type"] == "Proficiency in basic safety training"
