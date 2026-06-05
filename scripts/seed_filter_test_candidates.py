"""
Seed or remove test candidates for Seamens Data position/fleet filter checks.

All rows use surname FilterTest001 … FilterTest050 (prefix FilterTest).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
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
from models.schema import Application, Candidate, SeaService

SURNAME_PREFIX = "FilterTest"
# Raw strings in application (mix of synonyms for filter testing).
POSITION_RAW = [
    "Master",
    "Capt",
    "Chief Engineer",
    "C/E",
    "Chief Officer",
    "C/O",
    "Second Engineer",
    "2/E",
    "Second Officer",
    "2/O",
    "Third Engineer",
    "3/E",
    "Third Officer",
    "3/O",
    "Fourth Engineer",
    "AB",
    "Oiler",
    "Cook",
    "Deck Cadet",
    "Engine Cadet",
    "Electrician",
    "Pumpman",
    "Fitter",
    "Junior Officer",
    "Chief Officer Trainee",
]
FLEET_RAW = [
    "Bulk Carrier",
    "bulker",
    "Container Vessel",
    "Oil Tanker",
    "VLCC",
    "Chemical Tanker",
    "LNG Carrier",
    "LPG Carrier",
    "General Cargo Vessel",
    "Tanker",
]


def _build_rows(count: int) -> list[dict]:
    rows: list[dict] = []
    for i in range(1, count + 1):
        pos = POSITION_RAW[(i - 1) % len(POSITION_RAW)]
        fleet = FLEET_RAW[(i - 1) % len(FLEET_RAW)]
        rows.append(
            {
                "surname": f"{SURNAME_PREFIX}{i:03d}",
                "first_name": "Filter",
                "position_raw": pos,
                "fleet_raw": fleet,
            }
        )
    return rows


def seed_candidates(*, count: int) -> list[int]:
    session = SessionLocal()
    created_ids: list[int] = []
    try:
        existing = (
            session.query(Candidate.candidate_id)
            .filter(Candidate.surname.like(f"{SURNAME_PREFIX}%"))
            .count()
        )
        if existing:
            raise SystemExit(
                f"Already {existing} candidates with surname {SURNAME_PREFIX}*. "
                f"Run with --delete first."
            )
        now = datetime.now(timezone.utc)
        for spec in _build_rows(count):
            cand = Candidate(
                surname=spec["surname"],
                first_name=spec["first_name"],
                record_status="active",
                source_form_type="filter_test_seed",
                cv_imported=False,
                created_at=now,
                updated_at=now,
            )
            session.add(cand)
            session.flush()
            session.add(
                Application(
                    candidate_id=cand.candidate_id,
                    position_applied_for=spec["position_raw"],
                    proposed_vessel=f"TBN-{spec['surname']}",
                    date_applied=date.today(),
                )
            )
            session.add(
                SeaService(
                    candidate_id=cand.candidate_id,
                    vessel_type=spec["fleet_raw"],
                    vessel_name=f"MV {spec['surname']}",
                    rank_on_vessel="AB",
                )
            )
            created_ids.append(cand.candidate_id)
        session.commit()
        return created_ids
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_candidates() -> int:
    session = SessionLocal()
    try:
        rows = (
            session.query(Candidate)
            .filter(Candidate.surname.like(f"{SURNAME_PREFIX}%"))
            .order_by(Candidate.candidate_id)
            .all()
        )
        n = len(rows)
        for row in rows:
            session.delete(row)
        session.commit()
        return n
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_candidates() -> None:
    session = SessionLocal()
    try:
        rows = (
            session.query(Candidate)
            .filter(Candidate.surname.like(f"{SURNAME_PREFIX}%"))
            .order_by(Candidate.surname)
            .all()
        )
        if not rows:
            print(f"No candidates with surname {SURNAME_PREFIX}*")
            return
        print(f"{'id':>6}  {'surname':<14}  application position (raw)")
        for c in rows:
            app = c.applications[0] if c.applications else None
            pos = (app.position_applied_for if app else "") or "-"
            print(f"{c.candidate_id:>6}  {c.surname:<14}  {pos}")
        print(f"Total: {len(rows)}")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or remove FilterTest* candidates for UI filter QA.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help="Create test candidates.")
    group.add_argument("--delete", action="store_true", help="Remove all FilterTest* candidates.")
    group.add_argument("--list", action="store_true", help="List existing FilterTest* candidates.")
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        metavar="N",
        help="How many to create with --seed (default: 50).",
    )
    args = parser.parse_args()

    if args.list:
        list_candidates()
        return

    if args.delete:
        n = delete_candidates()
        print(f"Deleted {n} candidates ({SURNAME_PREFIX}*).")
        return

    if args.count < 1 or args.count > 500:
        raise SystemExit("--count must be between 1 and 500")

    ids = seed_candidates(count=args.count)
    report = PROJECT_ROOT / "reports" / "filter_test_seed_ids.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(str(i) for i in ids) + "\n", encoding="utf-8")
    print(f"Created {len(ids)} candidates ({SURNAME_PREFIX}001–{SURNAME_PREFIX}{args.count:03d}).")
    print(f"IDs saved to: {report}")
    print("Positions cycle:", ", ".join(POSITION_RAW[:8]), "…")
    print("Fleet types cycle:", ", ".join(FLEET_RAW[:5]), "…")
    print(f"Canonical ranks in filter dropdown: {len(RANK_OPTIONS)} options")
    print(f"Canonical fleet in filter dropdown: {len(FLEET_OPTIONS)} options")
    print()
    print("Remove later:")
    print("  python scripts/seed_filter_test_candidates.py --delete")


if __name__ == "__main__":
    main()
