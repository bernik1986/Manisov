"""Short rank codes for scan filenames (Rank Surname SlotCode.pdf)."""

from __future__ import annotations

from models.schema import Candidate

from app.rank_normalization import resolve_canonical_position

# Canonical rank label -> scan code (see docs/SCAN_FILENAME_CONVENTION.md).
RANK_SCAN_CODES: dict[str, str] = {
    "Master": "MST",
    "Chief Officer": "CO",
    "Chief Officer Trainee": "CO Tr",
    "Second Officer": "2O",
    "Second Officer Trainee": "2O Tr",
    "Third Officer": "3O",
    "Junior Officer": "JO",
    "Deck Cadet": "DC",
    "Boatswain": "BSN",
    "Able Seaman": "AB",
    "Ordinary Seaman": "OS",
    "Chief Engineer": "CE",
    "Chief Engineer Trainee": "CE Tr",
    "Second Engineer": "2E",
    "Second Engineer Trainee": "2E Tr",
    "Third Engineer": "3E",
    "Fourth Engineer": "4E",
    "Engine Cadet": "JE",
    "Electro Technical Officer": "ETO",
    "Gas Engineer": "GE",
    "Electrician": "ELEC",
    "Pumpman": "PMPN",
    "Oiler": "OLR",
    "Wiper": "WPR",
    "Fitter": "FTR",
    "Motorman": "MM",
    "Cook": "CCK",
}


def _rank_from_candidate(candidate: Candidate) -> str:
    rank = (candidate.current_rank or "").strip()
    if rank:
        return rank
    applications = candidate.applications or []
    first = applications[0] if applications else None
    if first is not None:
        rank = (first.rank_applied_for or first.position_applied_for or "").strip()
        if rank:
            return rank
    return ""


def resolve_rank_scan_code(candidate: Candidate) -> str:
    raw = _rank_from_candidate(candidate)
    if not raw:
        return "RANK"
    canon = resolve_canonical_position(raw)
    if canon and canon in RANK_SCAN_CODES:
        return RANK_SCAN_CODES[canon]
    if canon and "trainee" in canon.lower():
        base_label = canon.replace(" Trainee", "").strip()
        base_code = RANK_SCAN_CODES.get(base_label)
        if base_code:
            return f"{base_code} Tr"
    compact = raw.upper().replace(".", "").strip()
    if 1 < len(compact) <= 10 and " " not in raw:
        return compact
    if canon:
        return canon[:12].replace(" ", "")
    return raw[:12].replace(" ", "_")
