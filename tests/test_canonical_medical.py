from __future__ import annotations

from app.canonical_medical import (
    CANONICAL_MEDICAL_SPECS,
    apply_canonical_medical_placeholders,
    ensure_canonical_medical,
    is_canonical_medical_record,
    medical_matches_spec,
    order_medical_for_response,
)
from models.db import Base, SessionLocal, engine, init_db
from models.schema import Candidate, Certificate


def test_medical_matches_covid_and_excludes_stcw():
    covid_spec = next(s for s in CANONICAL_MEDICAL_SPECS if s["code"] == "COVID")
    exam_spec = next(s for s in CANONICAL_MEDICAL_SPECS if s["code"] == "MED_EXAM")
    assert medical_matches_spec({"certificate_type": "COVID-19 CERTIFICATE"}, covid_spec)
    assert not medical_matches_spec({"certificate_type": "Medical First Aid"}, exam_spec)
    assert not medical_matches_spec({"certificate_type": "Medical Care"}, exam_spec)


def test_ensure_canonical_medical_creates_slots():
    init_db()
    session = SessionLocal()
    try:
        candidate = Candidate(surname="Med", first_name="Test", current_rank="CO")
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        session.add(
            Certificate(
                candidate_id=candidate.candidate_id,
                certificate_type="COVID-19 vaccination",
                certificate_number="CV-1",
            )
        )
        session.commit()

        changed = ensure_canonical_medical(session, candidate.candidate_id)
        assert changed is True

        rows = session.query(Certificate).filter(Certificate.candidate_id == candidate.candidate_id).all()
        assert len(rows) == len(CANONICAL_MEDICAL_SPECS)

        covid = next(r for r in rows if r.certificate_name_raw == "COVID")
        assert covid.certificate_type == "Covid Certificate"
        assert covid.certificate_code == "Covid Certificate"
        assert covid.certificate_number == "CV-1"
        assert covid.certificate_group == "Medical Document"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_order_medical_for_response_fixed_slots():
    stcw = {
        "certificate_id": 1,
        "certificate_group": "Conventional Certificate",
        "certificate_type": "MFA - Medical First Aid",
        "certificate_name_raw": "MFA",
    }
    ordered = order_medical_for_response([stcw])
    assert len(ordered) == len(CANONICAL_MEDICAL_SPECS)
    assert all(row.get("certificate_id") != 1 for row in ordered)


def test_apply_canonical_medical_placeholders_legacy_fitness():
    context = {
        "certificates": [
            {
                "certificate_id": 1,
                "certificate_type": "Medical Examination",
                "certificate_name_raw": "MED_EXAM",
                "certificate_number": "M-99",
                "date_issued": "2024-06-01",
            }
        ],
        "medical_documents": [],
    }
    apply_canonical_medical_placeholders(context)
    assert context["medical_examination_certificate_number"] == "M-99"
    assert context["medical_fitness_certificate_number"] == "M-99"


def test_is_canonical_medical_record_by_group():
    assert is_canonical_medical_record({"certificate_group": "Medical Document", "certificate_type": "Custom"})
    assert not is_canonical_medical_record({"certificate_group": "Conventional Certificate", "certificate_type": "BST"})
