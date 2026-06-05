from __future__ import annotations

from app.canonical_diplomas import (
    CANONICAL_DIPLOMA_SPECS,
    CANONICAL_TANKER_DIPLOMA_SPECS,
    apply_canonical_diploma_placeholders,
    canonical_diploma_placeholder_tokens,
    diploma_matches_spec,
    ensure_canonical_diplomas,
    is_canonical_diploma_record,
    is_working_coc_diploma,
    order_specs_for_response,
)
from models.db import Base, SessionLocal, engine, init_db
from models.schema import Candidate, Certificate


def test_diploma_matches_coc_and_gmdss_slots():
    coc_spec = next(s for s in CANONICAL_DIPLOMA_SPECS if s["code"] == "COC")
    end_coc_spec = next(s for s in CANONICAL_DIPLOMA_SPECS if s["code"] == "END_COC")
    gmdss_spec = next(s for s in CANONICAL_DIPLOMA_SPECS if s["code"] == "COC_GMDSS")
    assert diploma_matches_spec({"certificate_type": "Certificate of Competency"}, coc_spec)
    assert diploma_matches_spec({"certificate_type": "Endorsement COC"}, end_coc_spec)
    assert not diploma_matches_spec({"certificate_type": "GMDSS"}, coc_spec)
    assert diploma_matches_spec({"certificate_type": "GMDSS"}, gmdss_spec)


def test_ensure_canonical_diplomas_creates_all_slots():
    init_db()
    session = SessionLocal()
    try:
        candidate = Candidate(surname="Dip", first_name="Test", current_rank="CO")
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        session.add(
            Certificate(
                candidate_id=candidate.candidate_id,
                certificate_type="Certificate of Competency",
                certificate_number="COC-1",
            )
        )
        session.commit()

        changed = ensure_canonical_diplomas(session, candidate.candidate_id)
        assert changed is True

        rows = session.query(Certificate).filter(Certificate.candidate_id == candidate.candidate_id).all()
        assert len(rows) == len(CANONICAL_DIPLOMA_SPECS) + len(CANONICAL_TANKER_DIPLOMA_SPECS)

        coc = next(r for r in rows if r.certificate_name_raw == "COC")
        assert coc.certificate_type == "COC"
        assert coc.certificate_code == "COC"
        assert coc.certificate_number == "COC-1"
        assert coc.certificate_group == "Diploma"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_is_canonical_diploma_record_filters_stcw():
    assert is_canonical_diploma_record({"certificate_type": "Basic Safety Training"}) is False
    assert is_canonical_diploma_record({"certificate_type": "GMDSS"}) is True


def test_apply_canonical_diploma_placeholders_coc_rank():
    context = {
        "certificates": [
            {
                "certificate_id": 1,
                "certificate_type": "COC",
                "certificate_name_raw": "COC",
                "certificate_code": "COC",
                "certificate_group": "Diploma",
                "certificate_number": "UA-1",
                "competency_rank": "Chief Officer",
                "date_issued": "2020-01-01",
            }
        ],
        "diplomas": [],
        "tanker_diplomas": [],
        "coc_rank": "Old rank from candidate",
    }
    apply_canonical_diploma_placeholders(context)
    assert context["coc_competency_rank"] == "Chief Officer"
    assert context["coc_rank"] == "Chief Officer"
    assert context["coc_certificate_number"] == "UA-1"


def test_is_working_coc_diploma():
    assert is_working_coc_diploma(
        {"certificate_type": "COC", "certificate_name_raw": "COC", "certificate_code": "COC"}
    )
    assert not is_working_coc_diploma({"certificate_type": "Endorsement COC", "certificate_name_raw": "END_COC"})


def test_canonical_diploma_placeholder_tokens_include_coc_rank():
    tokens = canonical_diploma_placeholder_tokens()
    assert "{{ coc_competency_rank }}" in tokens


def test_apply_canonical_diploma_placeholders_legacy_coc():
    context = {
        "certificates": [
            {
                "certificate_id": 1,
                "certificate_type": "COC & Endorsement",
                "certificate_name_raw": "COC_END",
                "certificate_number": "123",
                "date_issued": "2020-01-01",
            }
        ],
        "diplomas": [],
        "tanker_diplomas": [],
    }
    apply_canonical_diploma_placeholders(context)
    assert context["endorsement_coc_certificate_number"] == "123"
    assert context["coc_endorsement_certificate_number"] == "123"


def test_order_specs_for_response_placeholders():
    ordered = order_specs_for_response([], CANONICAL_TANKER_DIPLOMA_SPECS)
    assert len(ordered) == len(CANONICAL_TANKER_DIPLOMA_SPECS)
    assert ordered[0]["is_canonical_placeholder"] is True


def test_sync_coc_competency_rank_to_candidate():
    from app.main import _sync_candidate_coc_rank_from_certificate

    init_db()
    session = SessionLocal()
    try:
        candidate = Candidate(surname="Sync", first_name="Test", certificate_of_competency_rank="Old")
        session.add(candidate)
        session.commit()
        certificate = Certificate(
            candidate_id=candidate.candidate_id,
            certificate_type="COC",
            certificate_name_raw="COC",
            certificate_code="COC",
            certificate_group="Diploma",
            competency_rank="Chief Officer",
        )
        session.add(certificate)
        session.flush()
        _sync_candidate_coc_rank_from_certificate(
            session, candidate.candidate_id, certificate, "Chief Officer"
        )
        session.commit()
        session.refresh(candidate)
        assert candidate.certificate_of_competency_rank == "Chief Officer"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_order_specs_for_response_does_not_append_stcw_rows():
    stcw = {
        "certificate_id": 99,
        "certificate_group": "Conventional Certificate",
        "certificate_type": "Basic Safety - Proficiency in basic safety training",
        "certificate_code": "BST",
        "certificate_name_raw": "BST",
    }
    ordered = order_specs_for_response([stcw], CANONICAL_DIPLOMA_SPECS)
    assert len(ordered) == len(CANONICAL_DIPLOMA_SPECS)
    assert all(row.get("certificate_id") != 99 for row in ordered)
