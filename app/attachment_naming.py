"""Display filenames for candidate document/certificate scans."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from models.schema import Attachment, Candidate, Certificate, Document, FlagDocument

from app.rank_scan_codes import resolve_rank_scan_code
from app.scan_slot_codes import (
    resolve_certificate_slot_code,
    resolve_document_slot_code,
    resolve_flag_document_slot_code,
)

_RELATION_PREFIX = re.compile(
    r"^(document|certificate|flag_document):(\d+)$",
    re.IGNORECASE,
)


def safe_scan_part(value: str) -> str:
    """Single filename segment; keeps spaces, strips forbidden path characters."""
    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "", str(value or "").strip())
    return re.sub(r"\s+", " ", cleaned).strip() or "unknown"


def safe_file_part(value: str) -> str:
    """Legacy underscore-safe segment (ZIP paths, etc.)."""
    cleaned = safe_scan_part(value)
    return re.sub(r"\s+", "_", cleaned).strip("._") or "unknown"


def resolve_rank(candidate: Candidate) -> str:
    """Legacy helper — canonical rank label or raw text."""
    from app.rank_normalization import resolve_canonical_position

    rank = (candidate.current_rank or "").strip()
    if not rank:
        applications = candidate.applications or []
        first = applications[0] if applications else None
        if first is not None:
            rank = (first.rank_applied_for or first.position_applied_for or "").strip()
    if not rank:
        return "rank"
    return resolve_canonical_position(rank) or rank


def resolve_scan_slot_code(db_session: Session, attachment: Attachment) -> str:
    description = (attachment.description or "").strip()
    match = _RELATION_PREFIX.match(description)
    if match:
        kind, raw_id = match.group(1).lower(), match.group(2)
        try:
            relation_id = int(raw_id)
        except ValueError:
            relation_id = None
        if relation_id is not None:
            if kind == "document":
                row = db_session.get(Document, relation_id)
                if row and row.candidate_id == attachment.candidate_id:
                    return resolve_document_slot_code(row)
            elif kind == "certificate":
                row = db_session.get(Certificate, relation_id)
                if row and row.candidate_id == attachment.candidate_id:
                    return resolve_certificate_slot_code(row)
            elif kind == "flag_document":
                row = db_session.get(FlagDocument, relation_id)
                if row and row.candidate_id == attachment.candidate_id:
                    return resolve_flag_document_slot_code(row)
    source = (attachment.source or "").strip()
    if source and source not in {"frontend_upload", "document", "certificate", "flag_document"}:
        return safe_scan_part(source)
    return "SCAN"


def build_scan_filename(
    candidate: Candidate,
    slot_code: str,
    *,
    suffix: str,
) -> str:
    ext = suffix if suffix.startswith(".") else f".{suffix}" if suffix else ""
    parts = [
        safe_scan_part(resolve_rank_scan_code(candidate)),
        safe_scan_part(candidate.surname or ""),
        safe_scan_part(slot_code),
    ]
    return f"{' '.join(parts)}{ext.lower()}"


def attachment_download_filename(
    db_session: Session,
    candidate: Candidate,
    attachment: Attachment,
) -> str:
    suffix = Path(attachment.file_path or attachment.file_name or "").suffix or ".bin"
    slot_code = resolve_scan_slot_code(db_session, attachment)
    return build_scan_filename(candidate, slot_code, suffix=suffix)
