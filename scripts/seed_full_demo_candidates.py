"""
Seed full demo candidates (profile, application, sea service, docs, scans).

Surname prefix: DemoSeaman001 … DemoSeaman050
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_root = str(PROJECT_ROOT)
while _root in sys.path:
    sys.path.remove(_root)
sys.path.insert(0, _root)
for _name in list(sys.modules):
    if _name == "app" or _name.startswith("app."):
        _mod = sys.modules.get(_name)
        _mod_file = getattr(_mod, "__file__", None) if _mod is not None else None
        if _mod_file and not str(Path(_mod_file).resolve()).startswith(_root):
            del sys.modules[_name]

from app.fleet_normalization import FLEET_OPTIONS
from app.rank_normalization import RANK_OPTIONS
from models.db import SessionLocal
from models.schema import (
    Application,
    Attachment,
    Candidate,
    Certificate,
    Document,
    FamilyContact,
    FlagDocument,
    SeaService,
)

SURNAME_PREFIX = "DemoSeaman"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
REPORT_PATH = PROJECT_ROOT / "reports" / "demo_seed_manifest.json"

FIRST_NAMES = [
    "Oleksandr",
    "Dmytro",
    "Ivan",
    "Mykhailo",
    "Andriy",
    "Serhii",
    "Viktor",
    "Pavlo",
    "Yurii",
    "Roman",
    "Bohdan",
    "Taras",
    "Ihor",
    "Volodymyr",
    "Petro",
]
MIDDLE_NAMES = ["Petrovych", "Ivanovych", "Mykolayovych", "Vasylkovych", "Andriyovych"]
CITIES = ["Odesa", "Mykolaiv", "Kherson", "Kyiv", "Lviv", "Mariupol", "Kharkiv"]
NATIONALITIES = ["Ukrainian", "Filipino", "Indian", "Georgian", "Romanian"]
VESSEL_NAMES = [
    "MV Atlantic Star",
    "MV Baltic Fortune",
    "MV Ocean Pride",
    "MV Northern Wind",
    "MV Southern Cross",
    "MV Eastern Horizon",
    "MV Western Glory",
    "MV Global Trader",
]
EMPLOYERS = ["Crewwell Maritime", "Blue Ocean Crewing", "Global Ship Management", "Neptune Manning"]
DOC_TYPES = [
    ("Travel", "Passport"),
    ("Identity", "Seaman's Book"),
    ("Medical", "Medical Fitness"),
    ("Visa", "Schengen Visa C"),
]
CERT_TYPES = [
    ("STCW", "Basic Safety Training"),
    ("STCW", "Advanced Fire Fighting"),
    ("STCW", "Proficiency in Survival Craft"),
    ("Tanker", "Oil Tanker Familiarization"),
    ("Navigation", "ECDIS Generic"),
]
FLAG_COUNTRIES = ["Panama", "Liberia", "Marshall Islands", "Malta", "Cyprus"]


def _d(y: int, m: int, d: int) -> date:
    return date(y, m, d)


def _minimal_pdf_bytes(label: str) -> bytes:
    body = f"%PDF-1.4\n% Demo scan: {label}\n"
    return body.encode("utf-8")


def _write_scan_file(label: str) -> tuple[Path, int]:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"demo_seed_{uuid.uuid4().hex}.pdf"
    path = UPLOADS_DIR / name
    content = _minimal_pdf_bytes(label)
    path.write_bytes(content)
    return path, len(content)


def _add_scan(
    session,
    *,
    candidate_id: int,
    source: str,
    relation_id: int,
    display_name: str,
    manifest: list[dict],
) -> None:
    path, size = _write_scan_file(display_name)
    manifest.append({"path": str(path), "attachment_for": f"{source}:{relation_id}"})
    session.add(
        Attachment(
            candidate_id=candidate_id,
            file_name=f"{display_name}.pdf",
            file_type="application/pdf",
            file_path=str(path),
            file_size_bytes=size,
            source=source,
            description=f"{source}:{relation_id}",
        )
    )


def _build_candidate_fields(i: int, rank: str, fleet: str) -> dict:
    fn = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
    mn = MIDDLE_NAMES[(i - 1) % len(MIDDLE_NAMES)]
    surname = f"{SURNAME_PREFIX}{i:03d}"
    city = CITIES[(i - 1) % len(CITIES)]
    nat = NATIONALITIES[(i - 1) % len(NATIONALITIES)]
    dob = _d(1980 + (i % 20), (i % 12) + 1, (i % 27) + 1)
    age = date.today().year - dob.year
    full = f"{surname} {fn} {mn}"
    email = f"demo.seaman{i:03d}@example.test"
    phone = f"+38050{1000000 + i:07d}"
    now = datetime.now(timezone.utc)
    return {
        "surname": surname,
        "first_name": fn,
        "middle_name": mn,
        "full_name": full,
        "latin_full_name": full,
        "native_full_name": full,
        "date_of_birth": dob,
        "place_of_birth": city,
        "country_of_birth": "Ukraine",
        "nationality": nat,
        "citizenship": nat,
        "age": age,
        "gender": "Male" if i % 3 else "Female",
        "marital_status": "Married" if i % 2 else "Single",
        "father_name": f"{surname} Senior",
        "mother_name": f"{surname} Maria",
        "primary_phone": phone,
        "mobile_phone": phone,
        "telephone_no": phone,
        "email": email,
        "secondary_email": f"alt.{email}",
        "skype_id": f"demo.seaman{i:03d}",
        "permanent_address": f"{city}, vul. Morska {i}, apt. {i % 40 + 1}",
        "home_address": f"{city}, vul. Portova {i}",
        "current_address": f"{city}, vul. Portova {i}",
        "city": city,
        "region": city,
        "postal_code": f"65{(i % 900) + 100:03d}",
        "country": "Ukraine",
        "spouse_name": f"Spouse {fn}",
        "number_of_children": i % 3,
        "children_under_18_count": i % 2,
        "dependants_count": i % 3,
        "sons_count": i % 2,
        "daughters_count": i % 2,
        "beneficiary_full_name": f"Beneficiary {surname}",
        "beneficiary_relationship": "Spouse",
        "beneficiary_address": f"{city}, vul. Sadova {i}",
        "beneficiary_phone": phone,
        "next_of_kin_relationship": "Brother",
        "next_of_kin_surname": surname,
        "next_of_kin_first_name": "Mykola",
        "next_of_kin_full_name": f"{surname} Mykola",
        "next_of_kin_address": f"{city}, vul. Kin {i}",
        "next_of_kin_phone": phone,
        "highest_educational_attainment": "Maritime Academy Bachelor",
        "school_name": f"{city} Maritime Academy",
        "graduation_year": 2000 + (i % 15),
        "education_notes": "Deck/Engine foundation courses completed.",
        "native_language": "Ukrainian",
        "english_level": "Intermediate" if i % 2 else "Advanced",
        "english_certificate": "Marlins 80%" if i % 2 else "CES 4.0",
        "other_languages": "Russian: fluent; English: working",
        "height_cm": 170.0 + (i % 20),
        "height_m": round((170.0 + (i % 20)) / 100, 2),
        "weight_kg": 70.0 + (i % 25),
        "distinctive_marks": "Scar on left hand" if i % 5 == 0 else None,
        "current_rank": rank,
        "certificate_of_competency_rank": rank,
        "certificate_of_competency_number": f"COC-{10000 + i}",
        "watchkeeping_capacity": "OOW" if "Officer" in rank else "Rating",
        "total_sea_service": f"{5 + (i % 15)} years",
        "total_sea_service_in_rank": f"{3 + (i % 10)} years",
        "years_in_rank": float(3 + (i % 10)),
        "years_in_this_type_of_vessel": float(2 + (i % 8)),
        "years_in_all_types_of_tankers": float(i % 6),
        "years_as_watch_officer": float(i % 7),
        "total_years_of_sea_service": float(5 + (i % 15)),
        "rank_experience_summary": f"Experienced {rank} on {fleet} trades.",
        "bulk_carrier_years_in_rank": float(i % 5),
        "bulk_carrier_years_in_vessel_type": float(i % 6),
        "tanker_years_in_rank": float(i % 4),
        "tanker_years_in_this_tanker_type": float(i % 4),
        "tanker_years_in_all_tanker_types": float(i % 5),
        "watch_officer_since_year": 2010 + (i % 10),
        "oil_tanker_experience": i % 3 == 0,
        "chemical_tanker_experience": i % 4 == 0,
        "gas_tanker_experience": i % 5 == 0,
        "lng_experience": i % 6 == 0,
        "lpg_experience": i % 7 == 0,
        "container_experience": i % 2 == 0,
        "bulk_carrier_experience": True,
        "general_cargo_experience": i % 2 == 1,
        "offshore_experience": i % 8 == 0,
        "medical_fitness_certificate_number": f"MED-{20000 + i}",
        "medical_fitness_issue_date": _d(2024, 1, 1),
        "medical_fitness_expiry_date": _d(2026, 12, 31),
        "yellow_fever_issue_date": _d(2023, 6, 1),
        "yellow_fever_expiry_date": _d(2033, 6, 1),
        "yellow_fever_unlimited": False,
        "usa_visa_number": f"USV-{30000 + i}",
        "usa_visa_issue_date": _d(2022, 3, 15),
        "usa_visa_expiry_date": _d(2027, 3, 14),
        "usa_visa_place_of_issue": "Kyiv",
        "visa_status_note": "C1/D valid",
        "home_airport": f"{city} International",
        "desirable_salary_usd": float(3000 + (i % 20) * 100),
        "rejoin_bonus_usd": float(500 + (i % 5) * 100),
        "submission_contract_duration_text": f"{4 + (i % 3)} +/- 1 months",
        "ecdis_systems_text": "Transas, JRC, Furuno",
        "vaccination_summary": "COVID x3, Yellow Fever",
        "leaving_reason": "Completion of contract",
        "employer_reference_note": "Positive reference on file",
        "passport_visa_status_note": "Passport valid; visas OK",
        "coc_gmdss_expiry_note": "CoC valid until 2028",
        "coc_has_qr_codes": True,
        "seaman_book_number": f"SB-{40000 + i}",
        "passport_number": f"P{50000 + i}",
        "passport_issue_date": _d(2019, 1, 10),
        "passport_expiry_date": _d(2029, 1, 9),
        "passport_place_of_issue": city,
        "erp_no": f"ERP-{60000 + i}",
        "e_registration_no": f"ER-{70000 + i}",
        "application_form_no": f"AF-{80000 + i}",
        "cv_prepared_by": "Demo Seed Script",
        "record_status": "active",
        "source_form_type": "demo_full_seed",
        "source_file_name": f"demo_{surname}.pdf",
        "cv_imported": True,
        "ukr_contract_json": json.dumps(
            {
                "ukr_surname": surname,
                "ukr_first_name": fn,
                "ukr_rank": rank,
                "ukr_vessel": VESSEL_NAMES[i % len(VESSEL_NAMES)],
            },
            ensure_ascii=False,
        ),
        "created_at": now,
        "updated_at": now,
    }


def _seed_one(session, i: int, manifest: list[dict]) -> int:
    rank = RANK_OPTIONS[(i - 1) % len(RANK_OPTIONS)]
    fleet = FLEET_OPTIONS[(i - 1) % len(FLEET_OPTIONS)]
    cand = Candidate(**_build_candidate_fields(i, rank, fleet))
    session.add(cand)
    session.flush()

    today = date.today()
    session.add(
        Application(
            candidate_id=cand.candidate_id,
            position_applied_for=rank,
            rank_applied_for=rank,
            willing_to_accept_lower_rank=i % 4 == 0,
            proposed_vessel=VESSEL_NAMES[i % len(VESSEL_NAMES)],
            date_applied=today - timedelta(days=30 + i),
            date_available=today + timedelta(days=14),
            last_salary_usd=float(2800 + (i % 15) * 150),
            applicant_type="New" if i % 2 else "Rejoin",
            recommended_by_ex_crew=i % 3 == 0,
            recommended_by_ex_crew_name="Ex Crew Referral" if i % 3 == 0 else None,
            recommended_by_others=False,
            notes=f"Demo application notes for {cand.surname}",
        )
    )

    for j in range(3):
        sign_on = today - timedelta(days=365 * (j + 1) + 30 * j)
        sign_off = sign_on + timedelta(days=120 + 10 * j)
        vt = fleet if j == 0 else FLEET_OPTIONS[(i + j) % len(FLEET_OPTIONS)]
        session.add(
            SeaService(
                candidate_id=cand.candidate_id,
                vessel_name=VESSEL_NAMES[(i + j) % len(VESSEL_NAMES)],
                vessel_type=vt,
                vessel_subtype="Handysize" if j == 0 else None,
                flag=FLAG_COUNTRIES[(i + j) % len(FLAG_COUNTRIES)],
                imo_number=f"IMO{9000000 + i * 10 + j}",
                year_built=2005 + (i % 15),
                dwt=float(35000 + (i % 20) * 1000),
                grt=float(20000 + (i % 10) * 500),
                main_engine="MAN B&W 6S50MC",
                engine_power="9480 kW",
                rank_on_vessel=rank,
                sign_on_date=sign_on,
                sign_off_date=sign_off,
                contract_duration="4 months",
                employer=EMPLOYERS[(i + j) % len(EMPLOYERS)],
                manning_agency="Demo Manning Agency",
                trade_area="Worldwide",
                cargo_type="Bulk" if "Bulk" in vt else "General",
                remarks=f"Contract {j + 1} demo remarks",
            )
        )

    for j, (cat, dtype) in enumerate(DOC_TYPES):
        doc = Document(
            candidate_id=cand.candidate_id,
            document_category=cat,
            document_type=dtype,
            document_name_raw=dtype,
            document_number=f"DOC-{cand.candidate_id}-{j + 1}",
            issuing_authority=f"{cand.city} Authority",
            place_of_issue=cand.city,
            date_of_issue=_d(2020 + j, 1, 1),
            date_of_expiry=_d(2028 + j, 12, 31),
            validity_status="Valid",
            unlimited_validity=False,
            country_of_issue="Ukraine",
            remarks="Demo document",
            verified=True,
        )
        session.add(doc)
        session.flush()
        _add_scan(
            session,
            candidate_id=cand.candidate_id,
            source="document",
            relation_id=doc.document_id,
            display_name=f"{rank}_{cand.surname}_{dtype.replace(' ', '_')}",
            manifest=manifest,
        )

    for j, (grp, ctype) in enumerate(CERT_TYPES):
        cert = Certificate(
            candidate_id=cand.candidate_id,
            certificate_group=grp,
            certificate_type=ctype,
            certificate_name_raw=ctype,
            certificate_code=f"STCW-{j + 1}",
            certificate_number=f"CERT-{cand.candidate_id}-{j + 1}",
            issuing_authority="Demo Training Center",
            date_issued=_d(2021 + j, 3, 1),
            expiry_date=_d(2026 + j, 3, 1),
            unlimited_validity=False,
            country_of_issue="Ukraine",
            is_present=True,
            remarks="Demo certificate",
        )
        session.add(cert)
        session.flush()
        _add_scan(
            session,
            candidate_id=cand.candidate_id,
            source="certificate",
            relation_id=cert.certificate_id,
            display_name=f"{rank}_{cand.surname}_{ctype.replace(' ', '_')}",
            manifest=manifest,
        )

    for j in range(2):
        flag = FlagDocument(
            candidate_id=cand.candidate_id,
            flag_country=FLAG_COUNTRIES[(i + j) % len(FLAG_COUNTRIES)],
            flag_document_type="Endorsement" if j == 0 else "Certificate of Competency",
            rank=rank,
            doc_number=f"FLAG-{cand.candidate_id}-{j + 1}",
            date_of_issuance=_d(2022, 5, 1),
            date_of_expiry=_d(2027, 5, 1),
            remarks="Demo flag document",
        )
        session.add(flag)
        session.flush()
        _add_scan(
            session,
            candidate_id=cand.candidate_id,
            source="flag_document",
            relation_id=flag.flag_document_id,
            display_name=f"{rank}_{cand.surname}_Flag_{j + 1}",
            manifest=manifest,
        )

    session.add(
        FamilyContact(
            candidate_id=cand.candidate_id,
            contact_type="Emergency",
            surname=cand.surname,
            first_name="Mykola",
            full_name=f"{cand.surname} Mykola",
            relationship_to_candidate="Brother",
            phone=cand.primary_phone,
            email=cand.email,
            address=cand.permanent_address,
            is_emergency_contact=True,
        )
    )
    session.add(
        FamilyContact(
            candidate_id=cand.candidate_id,
            contact_type="Beneficiary",
            surname=cand.surname,
            first_name="Olena",
            full_name=f"{cand.surname} Olena",
            relationship_to_candidate="Spouse",
            phone=cand.primary_phone,
            email=cand.secondary_email,
            address=cand.home_address,
            beneficiary_full_name=f"{cand.surname} Olena",
            beneficiary_relationship="Spouse",
            is_emergency_contact=False,
        )
    )

    return cand.candidate_id


def seed_all(*, count: int) -> list[int]:
    session = SessionLocal()
    manifest: list[dict] = []
    ids: list[int] = []
    try:
        existing = (
            session.query(Candidate.candidate_id)
            .filter(Candidate.surname.like(f"{SURNAME_PREFIX}%"))
            .count()
        )
        if existing:
            raise SystemExit(
                f"Already {existing} demo candidates ({SURNAME_PREFIX}*). Run --delete first."
            )
        for i in range(1, count + 1):
            ids.append(_seed_one(session, i, manifest))
            if i % 10 == 0:
                session.commit()
        session.commit()
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps({"candidate_ids": ids, "files": manifest}, indent=2),
            encoding="utf-8",
        )
        return ids
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_all() -> tuple[int, int]:
    session = SessionLocal()
    files_removed = 0
    try:
        if REPORT_PATH.is_file():
            data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            for entry in data.get("files", []):
                p = Path(entry.get("path", ""))
                if p.is_file():
                    p.unlink(missing_ok=True)
                    files_removed += 1
            REPORT_PATH.unlink(missing_ok=True)
        rows = (
            session.query(Candidate)
            .filter(Candidate.surname.like(f"{SURNAME_PREFIX}%"))
            .all()
        )
        n = len(rows)
        for row in rows:
            session.delete(row)
        session.commit()
        for orphan in UPLOADS_DIR.glob("demo_seed_*.pdf"):
            if orphan.is_file():
                orphan.unlink(missing_ok=True)
                files_removed += 1
        return n, files_removed
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_all() -> None:
    session = SessionLocal()
    try:
        rows = (
            session.query(Candidate)
            .filter(Candidate.surname.like(f"{SURNAME_PREFIX}%"))
            .order_by(Candidate.surname)
            .all()
        )
        if not rows:
            print(f"No {SURNAME_PREFIX}* candidates.")
            return
        print(f"{'id':>6}  {'surname':<16}  {'rank':<22}  docs")
        for c in rows:
            app = c.applications[0] if c.applications else None
            pos = (app.position_applied_for if app else "") or "-"
            print(
                f"{c.candidate_id:>6}  {c.surname:<16}  {pos:<22}  "
                f"d={len(c.documents)} c={len(c.certificates)} f={len(c.flag_documents)}"
            )
        print(f"Total: {len(rows)}")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or remove full demo CRM candidates.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true")
    group.add_argument("--delete", action="store_true")
    group.add_argument("--list", action="store_true")
    parser.add_argument("--count", type=int, default=50, metavar="N")
    args = parser.parse_args()

    if args.list:
        list_all()
        return
    if args.delete:
        n, files = delete_all()
        print(f"Deleted {n} candidates ({SURNAME_PREFIX}*) and {files} scan file(s).")
        return
    if args.count < 1 or args.count > 200:
        raise SystemExit("--count must be 1..200")
    ids = seed_all(count=args.count)
    print(f"Created {len(ids)} full demo candidates ({SURNAME_PREFIX}001–{SURNAME_PREFIX}{args.count:03d}).")
    print(f"Manifest: {REPORT_PATH}")
    print("Search in Seamens Data: DemoSeaman")
    print("Remove: python scripts/seed_full_demo_candidates.py --delete")


if __name__ == "__main__":
    main()
