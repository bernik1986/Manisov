"""
One-time data migration: write canonical rank and fleet labels into DB fields.

Uses the same resolvers as the API (rank_normalization, fleet_normalization).
Default mode is dry-run (no commits). Use --apply to persist changes.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_root = str(PROJECT_ROOT)
while _root in sys.path:
    sys.path.remove(_root)
sys.path.insert(0, _root)
# Another repo on PYTHONPATH may expose a different top-level `app` package.
for _name in list(sys.modules):
    if _name == "app" or _name.startswith("app."):
        _mod = sys.modules.get(_name)
        _mod_file = getattr(_mod, "__file__", None) if _mod is not None else None
        if _mod_file and not str(Path(_mod_file).resolve()).startswith(_root):
            del sys.modules[_name]

from sqlalchemy.orm import Session

from app.fleet_normalization import resolve_canonical_fleet
from app.rank_normalization import resolve_canonical_position
from models.db import SessionLocal
from models.schema import Application, Candidate, SeaService

@dataclass
class NormalizationStats:
    candidates_scanned: int = 0
    applications_scanned: int = 0
    sea_services_scanned: int = 0
    updated: int = 0
    unchanged: int = 0
    unmapped: int = 0
    empty: int = 0
    skipped_length: int = 0
    by_action: Counter[str] = field(default_factory=Counter)

    def merge(self, other: NormalizationStats) -> None:
        self.candidates_scanned += other.candidates_scanned
        self.applications_scanned += other.applications_scanned
        self.sea_services_scanned += other.sea_services_scanned
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.unmapped += other.unmapped
        self.empty += other.empty
        self.skipped_length += other.skipped_length
        self.by_action.update(other.by_action)


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def evaluate_field(
    raw: str | None,
    resolver: Callable[[str], str | None],
    *,
    max_length: int,
) -> tuple[str, str | None]:
    """
    Returns (action, canonical_value).
    canonical_value is set only when action is 'updated' or 'skipped_length'.
    """
    text = _strip_or_none(raw)
    if not text:
        return "empty", None
    canon = resolver(text)
    if canon is None:
        return "unmapped", None
    if canon == text:
        return "unchanged", None
    if len(canon) > max_length:
        return "skipped_length", canon
    return "updated", canon


def _inc_stats(stats: NormalizationStats, action: str) -> None:
    stats.by_action[action] += 1
    if action == "updated":
        stats.updated += 1
    elif action == "unchanged":
        stats.unchanged += 1
    elif action == "unmapped":
        stats.unmapped += 1
    elif action == "empty":
        stats.empty += 1
    elif action == "skipped_length":
        stats.skipped_length += 1


def _maybe_report(
    writer: csv.writer | None,
    *,
    entity: str,
    entity_id: int,
    field_name: str,
    old_value: str,
    action: str,
    new_value: str | None,
) -> None:
    if writer is None:
        return
    if action not in {"updated", "unmapped", "skipped_length"}:
        return
    writer.writerow(
        [
            entity,
            entity_id,
            field_name,
            old_value,
            new_value or "",
            action,
        ]
    )


def _process_rank_field(
    stats: NormalizationStats,
    writer: csv.writer | None,
    *,
    entity: str,
    entity_id: int,
    field_name: str,
    raw: str | None,
    max_length: int,
    apply: bool,
    row: object,
) -> bool:
    """Returns True if a DB change was queued (for batch counting)."""
    action, canon = evaluate_field(raw, resolve_canonical_position, max_length=max_length)
    _inc_stats(stats, action)
    old_display = (raw or "").strip()
    if action == "updated" and canon is not None:
        _maybe_report(
            writer,
            entity=entity,
            entity_id=entity_id,
            field_name=field_name,
            old_value=old_display,
            action=action,
            new_value=canon,
        )
        if apply:
            setattr(row, field_name, canon)
        return True
    if action in {"unmapped", "skipped_length"}:
        _maybe_report(
            writer,
            entity=entity,
            entity_id=entity_id,
            field_name=field_name,
            old_value=old_display,
            action=action,
            new_value=canon,
        )
    return False


def _process_fleet_field(
    stats: NormalizationStats,
    writer: csv.writer | None,
    *,
    entity_id: int,
    raw: str | None,
    apply: bool,
    row: SeaService,
) -> bool:
    action, canon = evaluate_field(raw, resolve_canonical_fleet, max_length=100)
    _inc_stats(stats, action)
    old_display = (raw or "").strip()
    if action == "updated" and canon is not None:
        _maybe_report(
            writer,
            entity="sea_services",
            entity_id=entity_id,
            field_name="vessel_type",
            old_value=old_display,
            action=action,
            new_value=canon,
        )
        if apply:
            row.vessel_type = canon
        return True
    if action in {"unmapped", "skipped_length"}:
        _maybe_report(
            writer,
            entity="sea_services",
            entity_id=entity_id,
            field_name="vessel_type",
            old_value=old_display,
            action=action,
            new_value=canon,
        )
    return False


def iter_candidate_ids(session: Session, *, limit: int | None) -> Iterator[int]:
    query = session.query(Candidate.candidate_id).order_by(Candidate.candidate_id)
    if limit is not None:
        query = query.limit(limit)
    for (candidate_id,) in query.all():
        yield candidate_id


def run_normalization(
    session: Session,
    *,
    apply: bool = False,
    limit: int | None = None,
    batch_size: int = 200,
    report_writer: csv.writer | None = None,
) -> NormalizationStats:
    stats = NormalizationStats()
    pending_changes = 0

    for candidate_id in iter_candidate_ids(session, limit=limit):
        candidate = session.get(Candidate, candidate_id)
        if candidate is None:
            continue
        stats.candidates_scanned += 1

        if _process_rank_field(
            stats,
            report_writer,
            entity="candidates",
            entity_id=candidate.candidate_id,
            field_name="current_rank",
            raw=candidate.current_rank,
            max_length=100,
            apply=apply,
            row=candidate,
        ):
            pending_changes += 1
        if _process_rank_field(
            stats,
            report_writer,
            entity="candidates",
            entity_id=candidate.candidate_id,
            field_name="certificate_of_competency_rank",
            raw=candidate.certificate_of_competency_rank,
            max_length=100,
            apply=apply,
            row=candidate,
        ):
            pending_changes += 1

        applications = (
            session.query(Application)
            .filter(Application.candidate_id == candidate_id)
            .order_by(Application.application_id)
            .all()
        )
        for app in applications:
            stats.applications_scanned += 1
            if _process_rank_field(
                stats,
                report_writer,
                entity="applications",
                entity_id=app.application_id,
                field_name="position_applied_for",
                raw=app.position_applied_for,
                max_length=150,
                apply=apply,
                row=app,
            ):
                pending_changes += 1
            if _process_rank_field(
                stats,
                report_writer,
                entity="applications",
                entity_id=app.application_id,
                field_name="rank_applied_for",
                raw=app.rank_applied_for,
                max_length=100,
                apply=apply,
                row=app,
            ):
                pending_changes += 1

        sea_rows = (
            session.query(SeaService)
            .filter(SeaService.candidate_id == candidate_id)
            .order_by(SeaService.sea_service_id)
            .all()
        )
        for sea in sea_rows:
            stats.sea_services_scanned += 1
            if _process_rank_field(
                stats,
                report_writer,
                entity="sea_services",
                entity_id=sea.sea_service_id,
                field_name="rank_on_vessel",
                raw=sea.rank_on_vessel,
                max_length=100,
                apply=apply,
                row=sea,
            ):
                pending_changes += 1
            if _process_fleet_field(
                stats,
                report_writer,
                entity_id=sea.sea_service_id,
                raw=sea.vessel_type,
                apply=apply,
                row=sea,
            ):
                pending_changes += 1

        if apply and pending_changes >= batch_size:
            session.commit()
            pending_changes = 0

    if apply:
        if pending_changes > 0 or session.new or session.dirty:
            session.commit()
    else:
        session.rollback()

    return stats


def _open_report_writer(path: Path | None) -> tuple[csv.writer | None, object | None]:
    if path is None:
        return None, None
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", newline="", encoding="utf-8")
    writer = csv.writer(handle)
    writer.writerow(["entity", "id", "field", "old", "new", "action"])
    return writer, handle


def print_summary(stats: NormalizationStats, *, apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== Normalization {mode} summary ===")
    print(f"Candidates scanned:    {stats.candidates_scanned}")
    print(f"Applications scanned:  {stats.applications_scanned}")
    print(f"Sea services scanned:  {stats.sea_services_scanned}")
    print(f"Updated:               {stats.updated}")
    print(f"Unchanged (canonical): {stats.unchanged}")
    print(f"Unmapped:              {stats.unmapped}")
    print(f"Empty/skipped field:   {stats.empty}")
    print(f"Skipped (length):      {stats.skipped_length}")
    if not apply:
        print("No database changes were committed (dry-run).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize rank and fleet fields in the database to canonical labels."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report only, do not commit (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Persist canonical values to the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N candidates (by candidate_id).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        metavar="N",
        help="Commit every N field updates when using --apply (default: 200).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write CSV report (updated, unmapped, skipped_length rows).",
    )
    args = parser.parse_args()
    apply = bool(args.apply)
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1")

    report_path = args.report
    if report_path is None and not apply:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = PROJECT_ROOT / "reports" / f"normalize_{stamp}.csv"

    writer, handle = _open_report_writer(report_path)
    session = SessionLocal()
    try:
        stats = run_normalization(
            session,
            apply=apply,
            limit=args.limit,
            batch_size=args.batch_size,
            report_writer=writer,
        )
        print_summary(stats, apply=apply)
        if report_path is not None:
            print(f"Report written to: {report_path}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if handle is not None:
            handle.close()


if __name__ == "__main__":
    main()
