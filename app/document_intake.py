"""Private draft, preview and approval endpoints for candidate scans."""

from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from hashlib import sha256
from os import fstat
from pathlib import Path
from secrets import token_urlsafe
from sqlite3 import SQLITE_BUSY
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Event, Thread
import json
import logging
import re
from typing import Annotated, Literal
import unicodedata
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import DataError, IntegrityError, InvalidRequestError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import defer
from starlette.concurrency import run_in_threadpool

from app.attachment_convert import prepare_attachment_bytes
from app.attachment_naming import attachment_download_filename
from app.document_intake_catalog import CANONICAL, intake_catalog
from app.document_intake_pdf import render_preview_page
from app.document_intake_runtime import recognize_document_bounded
from app.document_upload import (
    MAX_BATCH, MAX_FILE, MAX_FILES, MAX_PAGES, MAX_PENDING_SUBMISSIONS, MEDIA_TYPES, PUBLIC_HEADERS, SIGNATURES,
    clean_upload_name, parse_upload_form, prepare_submission_files, read_submission_manifest,
)
from models.schema import Attachment, AuditLog, Candidate, Document, DocumentIntakeFile, DocumentUploadLink, DocumentUploadSubmission

logger = logging.getLogger(__name__)
MAX_DRAFT_BYTES = 512 * 1024 * 1024
MAX_PUBLIC_DRAFT_BYTES = 256 * 1024 * 1024
MAX_CANDIDATE_PUBLIC_DRAFT_BYTES = 64 * 1024 * 1024
DRAFT_TTL = timedelta(days=7)
PRIVATE_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
SWITCH_FILE = ".document-intake-enabled"
PUBLIC_SWITCH_FILE = ".document-upload-enabled"
RECEIVED, IN_REVIEW, CLOSED = "received", "in_review", "closed"
PORTAL_TYPES = {item.key: item for item in CANONICAL}


def _marker_enabled(marker: Path) -> bool:
    try:
        return marker.is_file() and not marker.is_symlink()
    except OSError:
        return False


def _uploads_path(uploads_dir):
    return uploads_dir() if callable(uploads_dir) else uploads_dir


def pilot_enabled(uploads_dir) -> bool:
    return _marker_enabled(_uploads_path(uploads_dir) / SWITCH_FILE)


def public_upload_enabled(uploads_dir) -> bool:
    path = _uploads_path(uploads_dir)
    return pilot_enabled(path) and _marker_enabled(path / PUBLIC_SWITCH_FILE)


class Approval(BaseModel):
    file_ids: list[Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]] = Field(min_length=1, max_length=MAX_FILES)
    type_key: str = Field(max_length=500)
    fields: dict[Annotated[str, Field(max_length=40)], Annotated[str, Field(max_length=4000)] | bool | None] = Field(max_length=20)
    action: Literal["create", "update"]
    existing_id: int | None = None
    existing_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    confirm_holder: bool = False
    confirm_type_mismatch: bool = Field(default=False, strict=True)


class Approvals(BaseModel):
    documents: list[Approval] = Field(min_length=1, max_length=MAX_FILES)
    bulk: bool = False
    finish_submission: bool = False


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize(value):
    return "".join(char for char in unicodedata.normalize("NFKC", str(value or "")).casefold() if char.isalnum())


def _name_words(name):
    text = unicodedata.normalize("NFKD", str(name or "").casefold())
    return re.findall(r"[^\W\d_]+", "".join(c for c in text if not unicodedata.combining(c)))


def _script(text):
    return {unicodedata.name(char, "").split(" ")[0] for char in text if char.isalpha()}


def holder_warning(candidate, holder):
    known = _name_words(candidate.first_name) + _name_words(candidate.surname)
    observed = _name_words(holder)
    if len(known) < 2 or len(observed) < 2 or _script("".join(known)) != _script("".join(observed)):
        return "holder_unreadable"
    if all(any(SequenceMatcher(None, word, token).ratio() >= 0.8 for token in observed) for word in known):
        return None
    return "holder_mismatch"


def _candidate(db, candidate_id, *, lock=False):
    stmt = select(Candidate).where(Candidate.candidate_id == candidate_id)
    candidate = db.scalar(stmt.with_for_update() if lock else stmt)
    if candidate is None:
        raise HTTPException(404, "candidate_not_found")
    return candidate


def _external_state(*statuses):
    return select(DocumentUploadSubmission.submission_id).where(
        DocumentUploadSubmission.submission_id == DocumentIntakeFile.batch_id,
        DocumentUploadSubmission.candidate_id == DocumentIntakeFile.candidate_id,
        DocumentUploadSubmission.status.in_(statuses),
    ).exists()


def _query(candidate_id, owner_id, *, include_closed=False):
    statuses = (IN_REVIEW, CLOSED) if include_closed else (IN_REVIEW,)
    return select(DocumentIntakeFile).where(
        DocumentIntakeFile.candidate_id == candidate_id,
        or_(
            and_(DocumentIntakeFile.owner_id == owner_id, DocumentIntakeFile.created_at >= _now() - DRAFT_TTL),
            and_(DocumentIntakeFile.owner_id.is_(None), _external_state(*statuses)),
        ),
    )


def _draft_bytes(db):
    return db.scalar(select(func.coalesce(func.sum(func.length(DocumentIntakeFile.content)), 0)).where(
        or_(DocumentIntakeFile.owner_id.is_(None), DocumentIntakeFile.created_at >= _now() - DRAFT_TTL),
    ))


def _check_public_storage(db, candidate_id, incoming_bytes):
    size = func.coalesce(func.sum(func.length(DocumentIntakeFile.content)), 0)
    public_drafts = select(size).where(DocumentIntakeFile.owner_id.is_(None))
    if db.scalar(public_drafts.where(DocumentIntakeFile.candidate_id == candidate_id)) + incoming_bytes > MAX_CANDIDATE_PUBLIC_DRAFT_BYTES:
        raise HTTPException(409, "submission_limit", headers=PUBLIC_HEADERS)
    if db.scalar(public_drafts) + incoming_bytes > MAX_PUBLIC_DRAFT_BYTES or _draft_bytes(db) + incoming_bytes > MAX_DRAFT_BYTES:
        raise HTTPException(409, "draft_storage_limit", headers=PUBLIC_HEADERS)


def _check_public_quota(db, candidate_id, incoming_bytes):
    if db.scalar(select(func.count()).select_from(DocumentUploadSubmission).where(
        DocumentUploadSubmission.candidate_id == candidate_id,
        DocumentUploadSubmission.status.in_((RECEIVED, IN_REVIEW)),
    )) >= MAX_PENDING_SUBMISSIONS:
        raise HTTPException(409, "submission_limit", headers=PUBLIC_HEADERS)
    _check_public_storage(db, candidate_id, incoming_bytes)


def _cleanup_drafts(db, now):
    expired_submissions = select(DocumentUploadSubmission.submission_id).where(
        DocumentUploadSubmission.closed_at < now - DRAFT_TTL,
    )
    db.execute(delete(DocumentIntakeFile).where(or_(
        and_(DocumentIntakeFile.owner_id.is_not(None), DocumentIntakeFile.created_at < now - DRAFT_TTL),
        and_(DocumentIntakeFile.owner_id.is_(None), DocumentIntakeFile.batch_id.in_(expired_submissions)),
    )))
    db.execute(delete(DocumentUploadSubmission).where(DocumentUploadSubmission.closed_at < now - DRAFT_TTL))


def _submission(db, candidate_id, batch_id):
    return db.scalar(select(DocumentUploadSubmission).where(
        DocumentUploadSubmission.candidate_id == candidate_id,
        DocumentUploadSubmission.submission_id == batch_id,
    ).with_for_update())


def _serialize_submission(submission):
    return {
        "submission_id": submission.submission_id,
        "file_count": submission.file_count,
        "created_at": submission.created_at.isoformat(timespec="seconds") + "Z",
        "status": submission.status,
        "can_review": True,
    }


def _finish_submission(db, candidate_id, batch_id, *, discard=False, finish_selected=False):
    """Close a shared review and remove any bytes that were not saved to CRM."""
    # Same lock order as _approve and the state transitions in the upload inbox.
    if not db.scalar(select(DocumentUploadSubmission.submission_id).where(
        DocumentUploadSubmission.candidate_id == candidate_id, DocumentUploadSubmission.submission_id == batch_id,
    )):
        return False
    _candidate(db, candidate_id, lock=True)
    submission = _submission(db, candidate_id, batch_id)
    if submission is None:
        return False
    if submission.status == CLOSED:
        return True
    if not discard and submission.status != IN_REVIEW:
        return False
    unsaved = (
        DocumentIntakeFile.candidate_id == candidate_id, DocumentIntakeFile.batch_id == batch_id,
        DocumentIntakeFile.owner_id.is_(None), DocumentIntakeFile.saved_key.is_(None),
    )
    if not discard:
        pending = select(DocumentIntakeFile.file_id).where(*unsaved)
        if finish_selected:
            pending = pending.where(_pending())
        if db.scalar(pending.limit(1)):
            return False
    db.execute(delete(DocumentIntakeFile).where(*unsaved))
    submission.status = CLOSED
    submission.closed_at = _now()
    db.commit()
    return True


def _visible_records(records, candidate):
    attached = {a.description for a in candidate.attachments}
    return [
        (kind, key, row) for kind, key, row in records
        if any(value is not None and value != "" and value is not False
               for name, value in kind.get_fields(row).items() if name != "code")
        or f"{_relation(kind)}:{key}" in attached or row.scan_file
    ]


def _relation(kind):
    if kind.model is Document:
        return "document"
    return "flag_document" if kind.kind == "flag_document" else "certificate"


def _record_version(fields, row, attachments):
    scans = sorted(
        (a.attachment_id, a.checksum, a.file_path, a.file_name, a.file_type, a.file_size_bytes)
        for a in attachments
    )
    return sha256(json.dumps([fields, row.scan_file, scans], sort_keys=True, default=date.isoformat).encode()).hexdigest()


def _locked_attachments(db, candidate_id, relation, record_id):
    return db.scalars(select(Attachment).where(
        Attachment.candidate_id == candidate_id, Attachment.source == relation,
        Attachment.description == f"{relation}:{record_id}",
    ).execution_options(populate_existing=True).with_for_update()).all()


def _serialize_existing(item, key, row, scans):
    fields = item.get_fields(row)
    return {"id": key, "type_key": item.key, "label": item.label, "fields": fields, "version": _record_version(fields, row, scans)}


def _serialize_file(row):
    if row.saved_key:
        return {"file_id": row.file_id, "saved": True, **row.result, "name": row.name}
    return {
        "file_id": row.file_id, "name": row.name, "content_type": row.content_type,
        **row.result, "retryable": _can_retry(row),
    }


def _can_retry(row):
    retry_warnings = {"ocr_timeout", "ocr_failed", "ocr_unavailable", "recognition_time_limit"}
    return bool(not row.saved_key and row.content_type and (
        row.result.get("error") or retry_warnings.intersection(row.result.get("warnings", []))
    ))


def _serialize_batch(rows):
    processed = sum(not row.result.get("pending") for row in rows)
    return {
        "batch_id": rows[0].batch_id,
        **({"external": True} if rows[0].owner_id is None else {}),
        "name": rows[0].name,
        "processed": processed,
        "total": len(rows),
        "items": [_serialize_file(row) for row in rows] if processed == len(rows) else [],
    }


def _group(rows):
    matches = defaultdict(list)
    for row in rows:
        item = row.result
        number = _normalize(item.get("fields", {}).get("number"))
        if not row.saved_key and item.get("type_key") and number and row.content_type in {"image/jpeg", "image/png"}:
            matches[(item["type_key"], number)].append(row)
    for group in matches.values():
        names = {_normalize(r.result["fields"].get("holder_name")) for r in group}
        if len(group) > 1 and len(names - {""}) <= 1:
            key = uuid4().hex
            for row in group:
                row.result = {**row.result, "group_key": key}


def _pending():
    return DocumentIntakeFile.result["pending"].as_boolean().is_(True)


class _RecognitionResult(BaseModel):
    type_key: str | None = None
    fields: dict[str, str | bool | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    page_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def persistable_strings(self):
        # JSONB rejects NUL; UTF-8 drivers also reject lone surrogates. Check
        # dictionary keys as well as values before attempting a DB write.
        for value in (self.type_key, *self.fields, *self.fields.values(), *self.warnings):
            if isinstance(value, str):
                if "\x00" in value:
                    raise ValueError("Unpersistable recognition text")
                value.encode("utf-8")
        return self


class _RecognitionWorker:
    def __init__(self, sessions, uploads_dir, recognize=None):
        self.sessions, self.uploads_dir, self.recognize = sessions, uploads_dir, recognize
        self.wake = Event()
        self.stopping = Event()
        self.thread = None

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stopping.clear()
            self.thread = Thread(target=self.run, name="document-intake", daemon=True)
            self.thread.start()

    def stop(self):
        self.stopping.set()
        self.wake.set()
        if self.thread is not None:
            self.thread.join(timeout=12)

    def run(self):
        while not self.stopping.is_set():
            self.wake.clear()
            try:
                if pilot_enabled(self.uploads_dir) and self.process_next():
                    continue
            except Exception:
                logger.error("Document intake worker could not advance the queue")
            self.wake.wait(timeout=2)

    def process_next(self):
        with self.sessions() as db:
            file_id = db.scalar(select(DocumentIntakeFile.file_id).where(
                _pending(), or_(
                    DocumentIntakeFile.created_at >= _now() - DRAFT_TTL,
                    and_(DocumentIntakeFile.owner_id.is_(None), _external_state(IN_REVIEW)),
                ),
            ).order_by(DocumentIntakeFile.created_at, DocumentIntakeFile.batch_id, DocumentIntakeFile.position).limit(1))
            if file_id is None:
                return False

        # Leave the row pending and release the DB connection during OCR.
        # If the process exits, the next worker can retry it from the stored bytes.
        type_hint = None
        try:
            # Preparation is part of the job: a bad candidate/catalog must not
            # pin the oldest draft at the front of the queue forever.
            with self.sessions() as db:
                row = db.get(DocumentIntakeFile, file_id)
                if row is None or not row.result.get("pending"):
                    return True
                content, suffix = row.content, Path(row.name).suffix.lower()
                type_hint = row.result.get("type_hint")
                candidate = db.get(Candidate, row.candidate_id)
                catalog = [item.public() for item in intake_catalog(candidate)[0].values()] if candidate else []
            if candidate is None or not content or suffix not in MEDIA_TYPES:
                raise ValueError("Missing draft input")
            with TemporaryDirectory(prefix="parcer-intake-") as folder:
                path = Path(folder) / f"input{suffix}"
                path.write_bytes(content)
                # Injected recognizers are trusted in-process test/provider adapters.
                # The production default isolates native code in a killable process.
                recognized = (self.recognize(path, catalog) if self.recognize is not None else
                              recognize_document_bounded(path, catalog, stop_event=self.stopping))
                result = _RecognitionResult.model_validate(recognized, strict=True).model_dump()
            if type_hint:
                if result["type_key"] and result["type_key"] != type_hint:
                    result["warnings"].append("type_hint_mismatch")
                result["type_key"] = type_hint
            warning = holder_warning(candidate, result.get("fields", {}).get("holder_name"))
            if warning:
                result["warnings"] = [*result.get("warnings", []), warning]
        except InterruptedError:
            # Shutdown leaves the original pending for the next worker startup.
            return False
        except TimeoutError:
            result = {**_RecognitionResult().model_dump(), "error": "recognition_timeout"}
        except DataError:
            result = {**_RecognitionResult().model_dump(), "error": "invalid_scan"}
        except SQLAlchemyError:
            # Database outages are retryable, not evidence of a corrupt scan.
            raise
        except ValueError:
            result = {**_RecognitionResult().model_dump(), "error": "invalid_scan"}
        except Exception:
            logger.error("Document intake recognition failed")
            result = {**_RecognitionResult().model_dump(), "error": "recognition_failed"}

        try:
            with self.sessions() as db:
                row = db.get(DocumentIntakeFile, file_id, with_for_update=True)
                if row is not None and row.result.get("pending"):
                    row.result = {**result, **({"type_hint": type_hint} if type_hint else {})}
                    batch = db.scalars(select(DocumentIntakeFile).where(
                        DocumentIntakeFile.candidate_id == row.candidate_id,
                        DocumentIntakeFile.owner_id == row.owner_id,
                        DocumentIntakeFile.batch_id == row.batch_id,
                    )).all()
                    if not any(item.result.get("pending") for item in batch):
                        _group(batch)
                    db.commit()
        except DataError:
            # Discard the rejected OCR result, not the uploaded original.
            logger.error("Document intake result could not be stored")
            with self.sessions() as db:
                db.execute(update(DocumentIntakeFile).where(
                    DocumentIntakeFile.file_id == file_id, _pending(),
                ).values(result={
                    **_RecognitionResult().model_dump(), "error": "recognition_failed",
                    **({"type_hint": type_hint} if type_hint else {}),
                }))
                db.commit()
        return True


def _field_updates(spec, fields, row):
    result = {}
    for name, value in fields.items():
        if name not in spec.mapping or value is None or value == "":
            continue
        if name == "expiry_date" and "unlimited_validity" in spec.mapping and fields.get("unlimited_validity") is True:
            continue
        column = spec.mapping[name]
        if name in {"issue_date", "expiry_date"}:
            try:
                value = date.fromisoformat(value)
            except (ValueError, TypeError):
                raise HTTPException(400, "invalid_date") from None
        elif name == "unlimited_validity":
            if not isinstance(value, bool):
                raise HTTPException(400, "invalid_fields")
        else:
            maximum = getattr(spec.model.__table__.c[column].type, "length", None) or 4000
            if not isinstance(value, str) or len(value) > maximum:
                raise HTTPException(400, "invalid_fields")
            value = value.strip()
            if not value:
                continue
        result[column] = value
    if "unlimited_validity" in spec.mapping and fields.get("unlimited_validity") is True:
        result[spec.mapping["expiry_date"]] = None
    effective = {**(spec.get_fields(row) if row is not None else {}), **{
        name: result[column] for name, column in spec.mapping.items() if column in result
    }}
    if effective.get("issue_date") and effective.get("expiry_date") and effective["issue_date"] > effective["expiry_date"]:
        raise HTTPException(400, "expiry_before_issue")
    if spec.kind == "flag_document" and not effective.get("country"):
        raise HTTPException(400, "country_required")
    return result


def _lock_approval_candidate(db, candidate_id):
    if db.get_bind().dialect.name == "sqlite":
        # FOR UPDATE is ignored by SQLite. Take its write lock before reading
        # drafts, records or versions. Keep the candidate timestamp unchanged.
        with db.no_autoflush:
            for attempt in range(2):
                try:
                    db.execute(update(Candidate).where(Candidate.candidate_id == candidate_id).values(
                        updated_at=Candidate.updated_at,
                    ).execution_options(synchronize_session=False))
                    break
                except OperationalError as exc:
                    if attempt or getattr(exc.orig, "sqlite_errorcode", 0) & 0xFF != SQLITE_BUSY:
                        raise
                    # Authentication may already hold a read snapshot. Release
                    # it before retrying, so it cannot block the current writer.
                    db.rollback()
        db.expire_all()
    return _candidate(db, candidate_id, lock=True)


def _attachment_available(attachment):
    try:
        path = Path(attachment.file_path)
        if not path.is_file():
            return False
        with path.open("rb") as stream:
            return bool(stream.read(1)) and (
                attachment.file_size_bytes is None
                or fstat(stream.fileno()).st_size == attachment.file_size_bytes
            )
    except OSError:
        return False


def _approve(db, candidate_id, user, batch_id, payload, *, allow_holder_override, uploads_dir, sync_rank):
    file_ids = payload.file_ids
    if len(set(file_ids)) != len(file_ids):
        raise HTTPException(400, "duplicate_file")
    approved = payload.model_dump()
    if not approved["confirm_type_mismatch"]:
        approved.pop("confirm_type_mismatch")  # Keep pre-upgrade idempotency keys valid.
    key = sha256(json.dumps(approved, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    candidate = _lock_approval_candidate(db, candidate_id)
    if db.scalar(_query(candidate_id, user.user_id).where(
        DocumentIntakeFile.batch_id == batch_id, _pending(),
    ).with_only_columns(DocumentIntakeFile.file_id).limit(1)):
        raise HTTPException(409, "batch_processing")
    query = _query(candidate_id, user.user_id, include_closed=True).where(
        DocumentIntakeFile.batch_id == batch_id, DocumentIntakeFile.file_id.in_(file_ids),
    )
    files = {row.file_id: row for row in db.scalars(query.with_for_update())}
    if len(files) != len(file_ids):
        raise HTTPException(404, "file_not_found")
    if all(row.saved_key == key for row in files.values()):
        return False
    if any(row.saved_key for row in files.values()):
        raise HTTPException(409, "file_already_saved")
    if any(not row.content_type or row.result.get("error") for row in files.values()):
        raise HTTPException(400, "file_not_reviewable")
    if any("type_hint_mismatch" in row.result.get("warnings", []) for row in files.values()):
        if not (allow_holder_override and payload.confirm_type_mismatch):
            raise HTTPException(409, "type_hint_mismatch")
    holder_values = [row.result.get("fields", {}).get("holder_name") for row in files.values()]
    holder_values.append(payload.fields.get("holder_name"))
    if any(holder_warning(candidate, value) == "holder_mismatch" for value in holder_values):
        if not (allow_holder_override and payload.confirm_holder):
            raise HTTPException(409, "holder_mismatch")
    catalog, records = intake_catalog(candidate)
    spec = catalog.get(payload.type_key)
    if spec is None:
        raise HTTPException(400, "type_required")
    relevant = [(record_id, row) for item, record_id, row in records if item.key == spec.key]
    visible = {record_id for item, record_id, _ in _visible_records(records, candidate) if item.key == spec.key}
    submitted_number = _normalize(payload.fields.get("number"))
    exact = {
        record_id for record_id, row in relevant
        if submitted_number and _normalize(spec.get_fields(row).get("number")) == submitted_number
    }
    relation = _relation(spec)
    attachments = None
    if payload.action == "update":
        row = dict(relevant).get(payload.existing_id)
        if row is None:
            raise HTTPException(409, "record_changed")
        try:
            db.refresh(row, with_for_update=True)
        except InvalidRequestError as exc:
            raise HTTPException(409, "record_changed") from exc
        attachments = _locked_attachments(db, candidate_id, relation, payload.existing_id)
        if payload.existing_version != _record_version(spec.get_fields(row), row, attachments):
            raise HTTPException(409, "record_changed")
        if exact and payload.existing_id not in exact:
            raise HTTPException(409, "existing_duplicate")
    else:
        if payload.existing_id is not None:
            raise HTTPException(400, "invalid_fields")
        if exact:
            raise HTTPException(409, "existing_duplicate")
        if spec.kind == "visa" and visible:
            # This CRM retains only one record per canonical visa slot.
            raise HTTPException(409, "existing_duplicate")
        row = next((item for record_id, item in relevant if record_id not in visible), None)
    changes = _field_updates(spec, payload.fields, row)
    written = []
    replaced_paths = set()
    commit_attempted = False
    try:
        claim = db.execute(update(DocumentIntakeFile).where(
            DocumentIntakeFile.file_id.in_(file_ids), DocumentIntakeFile.saved_key.is_(None),
        ).values(saved_key=key).execution_options(synchronize_session=False))
        if claim.rowcount != len(file_ids):
            raise HTTPException(409, "file_already_saved")
        if row is None:
            row = spec.model(candidate_id=candidate_id, **{**spec.identity, **changes})
            db.add(row)
        else:
            for name, value in changes.items():
                setattr(row, name, value)
        db.flush()
        if relation == "certificate" and "competency_rank" in changes:
            sync_rank(db, candidate_id, row, changes["competency_rank"])
        record_id = getattr(row, f"{relation}_id")
        description = f"{relation}:{record_id}"
        if attachments is None:
            attachments = _locked_attachments(db, candidate_id, relation, record_id)
        incoming_hashes = {sha256(files[file_id].content).hexdigest() for file_id in file_ids}
        missing = defaultdict(list)
        for attachment in attachments:
            if not _attachment_available(attachment):
                missing[attachment.checksum].append(attachment)
        known_hashes = {attachment.checksum for attachment in attachments} - missing.keys()
        for file_id in file_ids:
            draft = files[file_id]
            original = draft.content
            digest = sha256(original).hexdigest()
            if digest not in known_hashes:
                content, suffix, media_type = prepare_attachment_bytes(Path(draft.name).suffix, original)
                target = uploads_dir / f"{uuid4().hex}{suffix}"
                with target.open("xb") as stream:
                    written.append(target)
                    stream.write(content)
                # Repair metadata only after writing a new exclusive file. Never
                # overwrite the old path, which may be shared or reappear later.
                restored = missing.get(digest) or [Attachment(
                    candidate_id=candidate_id, file_name="", checksum=digest,
                    source=relation, description=description,
                )]
                for attachment in restored:
                    attachment.file_path = str(target)
                    attachment.file_type = media_type
                    attachment.file_size_bytes = len(content)
                    attachment.file_name = attachment_download_filename(db, candidate, attachment)
                    db.add(attachment)
                known_hashes.add(digest)
            draft.content = None
            draft.content_type = None
            draft.result = {"type_key": payload.type_key, "fields": {}, "warnings": [], "page_count": 0}
        if payload.action == "update":
            for attachment in attachments:
                if attachment.checksum not in incoming_hashes:
                    replaced_paths.add(Path(attachment.file_path))
                    db.delete(attachment)
        db.add(AuditLog(
            user_id=user.user_id, username=user.username, role_name=user.role.name if user.role else None,
            action=f"document_intake.{payload.action}", entity_type=relation, entity_id=str(record_id),
            details=f"candidate_id={candidate_id};file_count={len(file_ids)}",
        ))
        db.flush()
        commit_attempted = True
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            logger.error("Document intake rollback failed; attachment bytes retained")
            try:
                db.invalidate()
            except Exception:
                logger.error("Document intake session invalidation failed")
            raise HTTPException(409, "save_outcome_unknown") from None
        if commit_attempted:
            # COMMIT may have succeeded before the connection failed. Never
            # delete bytes that a committed Attachment might now reference.
            # The same approval can be retried against the saved_key claim.
            logger.error("Document intake commit outcome unknown; attachment bytes retained")
            raise HTTPException(409, "save_outcome_unknown") from None
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.error("Failed to remove rolled-back intake attachment")
        raise
    # File cleanup follows a confirmed commit so a failed replacement keeps
    # the previous scan usable, including when the commit outcome is unknown.
    for path in replaced_paths:
        try:
            if not db.scalar(select(Attachment.attachment_id).where(Attachment.file_path == str(path)).limit(1)):
                path.unlink(missing_ok=True)
        except Exception:
            db.rollback()
            logger.exception("Failed to remove replaced intake attachment file")
    return True


def intake_router(get_db, require_writer, uploads_dir, sync_notifications, sync_rank, *, sessions, recognize=None):
    prefix = "/candidates/{candidate_id}/document-intake"
    worker = _RecognitionWorker(sessions, uploads_dir, recognize)
    @asynccontextmanager
    async def lifespan(_app):
        worker.start()
        try:
            yield
        finally:
            worker.stop()

    router = APIRouter(lifespan=lifespan)
    upload_slot = BoundedSemaphore()

    @router.get(prefix + "/status")
    def status(response: Response, _user=Depends(require_writer)):
        response.headers.update(PRIVATE_HEADERS)
        return {"enabled": pilot_enabled(uploads_dir)}

    def require_enabled(_user=Depends(require_writer)):
        if not pilot_enabled(uploads_dir):
            raise HTTPException(404, "intake_disabled", headers=PRIVATE_HEADERS)

    def reserve_upload_slot(_enabled=Depends(require_enabled)):
        if not upload_slot.acquire(blocking=False):
            raise HTTPException(429, "batch_busy", headers={**PRIVATE_HEADERS, "Retry-After": "30"})
        try:
            yield
        finally:
            upload_slot.release()

    routes = APIRouter(prefix=prefix, dependencies=[Depends(require_enabled)])

    public_slot = BoundedSemaphore(2)

    def public_candidate_id(db, token):
        if not public_upload_enabled(uploads_dir) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise HTTPException(404, "upload_link_unavailable", headers=PUBLIC_HEADERS)
        candidate_id = db.scalar(select(DocumentUploadLink.candidate_id).join(Candidate).where(
            DocumentUploadLink.token == token,
        ))
        if candidate_id is None:
            raise HTTPException(404, "upload_link_unavailable", headers=PUBLIC_HEADERS)
        return candidate_id

    def lookup_public_link(token):
        with sessions() as db:
            return public_candidate_id(db, token)

    def store_public_upload(candidate_id, token, manifest, files, pages):
        def previous_upload(db):
            return db.scalar(select(DocumentUploadSubmission).where(
                DocumentUploadSubmission.candidate_id == candidate_id,
                DocumentUploadSubmission.request_id == manifest.request_id,
            ))

        def receipt(row):
            return {"submission_id": row.submission_id, "file_count": row.file_count}

        with sessions() as db:
            public_candidate_id(db, token)
            previous = previous_upload(db)
            if previous:
                return receipt(previous), True
            # Photo conversion may shrink the input. Only reject based on a
            # lower bound here; recheck exact prepared bytes under the lock.
            _check_public_quota(db, candidate_id, sum(file.size or 0 for file in files) + len(manifest.documents))

        prepared = prepare_submission_files(manifest, files, pages, {key: spec.label for key, spec in PORTAL_TYPES.items()})
        if not upload_slot.acquire(blocking=False):
            raise HTTPException(429, "batch_busy", headers={**PUBLIC_HEADERS, "Retry-After": "10"})
        try:
            with sessions() as db:
                # Serialize against revocation and other submissions for this candidate.
                if db.scalar(select(Candidate.candidate_id).where(
                    Candidate.candidate_id == candidate_id,
                ).with_for_update()) is None:
                    raise HTTPException(404, "upload_link_unavailable", headers=PUBLIC_HEADERS)
                if public_candidate_id(db, token) != candidate_id:
                    raise HTTPException(404, "upload_link_unavailable", headers=PUBLIC_HEADERS)
                previous = previous_upload(db)
                if previous:
                    return receipt(previous), True
                _check_public_quota(db, candidate_id, sum(len(content) for _, _, content, _ in prepared))
                now = _now()
                _cleanup_drafts(db, now)
                submission = DocumentUploadSubmission(
                    candidate_id=candidate_id, submission_id=uuid4().hex, request_id=manifest.request_id,
                    created_at=now, file_count=len(prepared), status=RECEIVED,
                )
                db.add(submission)
                db.add_all([
                    DocumentIntakeFile(
                        candidate_id=candidate_id, owner_id=None, batch_id=submission.submission_id,
                        file_id=uuid4().hex, position=index, created_at=now, name=name,
                        content_type=media_type, content=content, result={"type_hint": hint} if hint else {},
                    )
                    for index, (name, media_type, content, hint) in enumerate(prepared)
                ])
                result = receipt(submission)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    previous = previous_upload(db)
                    if previous:
                        return receipt(previous), True
                    raise
                return result, False
        finally:
            upload_slot.release()

    @router.get("/public/document-upload")
    def public_upload_catalog(request: Request, response: Response):
        lookup_public_link(request.headers.get("X-Document-Upload-Token", ""))
        response.headers.update(PUBLIC_HEADERS)
        return {
            "catalog": [{"key": item.key, "kind": item.kind, "label": item.label} for item in PORTAL_TYPES.values()],
            "limits": {
                "max_files": MAX_FILES, "max_file_bytes": MAX_FILE,
                "max_batch_bytes": MAX_BATCH, "max_pages": MAX_PAGES,
            },
        }

    @router.post("/public/document-upload", status_code=201)
    async def public_upload(request: Request, response: Response):
        token = request.headers.get("X-Document-Upload-Token", "")
        candidate_id = await run_in_threadpool(lookup_public_link, token)
        if not public_slot.acquire(blocking=False):
            raise HTTPException(429, "batch_busy", headers={**PUBLIC_HEADERS, "Retry-After": "10"})
        try:
            form = await parse_upload_form(request)
            try:
                manifest, files, pages = read_submission_manifest(form)
                receipt, duplicate = await run_in_threadpool(store_public_upload, candidate_id, token, manifest, files, pages)
            finally:
                await form.close()
        finally:
            public_slot.release()
        response.headers.update(PUBLIC_HEADERS)
        if duplicate:
            response.status_code = 200
        return receipt

    @router.get("/document-upload/notifications")
    def upload_notifications(response: Response, db=Depends(get_db), _user=Depends(require_writer)):
        response.headers.update(PRIVATE_HEADERS)
        if not pilot_enabled(uploads_dir):
            return {"enabled": False, "items": []}
        stmt = (
            select(DocumentUploadSubmission, Candidate.first_name, Candidate.surname)
            .join(Candidate)
            .where(DocumentUploadSubmission.status.in_((RECEIVED, IN_REVIEW)))
            .order_by(DocumentUploadSubmission.created_at.desc(), DocumentUploadSubmission.submission_id)
        )
        items = [
            {
                **_serialize_submission(item), "candidate_id": item.candidate_id,
                "candidate_name": " ".join(filter(None, (first_name, surname))),
            }
            for item, first_name, surname in db.execute(stmt)
        ]
        return {"enabled": public_upload_enabled(uploads_dir) or bool(items), "items": items}

    @routes.post("/upload-link")
    def create_upload_link(candidate_id: int, response: Response, db=Depends(get_db)):
        response.headers.update(PUBLIC_HEADERS)
        _candidate(db, candidate_id, lock=True)
        if not public_upload_enabled(uploads_dir):
            raise HTTPException(404, "upload_link_unavailable", headers=PUBLIC_HEADERS)
        link = db.get(DocumentUploadLink, candidate_id)
        if link is not None:
            return {"token": link.token}
        token = token_urlsafe(32)
        db.add(DocumentUploadLink(candidate_id=candidate_id, token=token))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            link = db.get(DocumentUploadLink, candidate_id)
            if link is None:
                raise
            token = link.token
        return {"token": token}

    @routes.delete("/upload-link", status_code=204)
    def revoke_upload_link(candidate_id: int, db=Depends(get_db)):
        _candidate(db, candidate_id, lock=True)
        db.execute(delete(DocumentUploadLink).where(DocumentUploadLink.candidate_id == candidate_id))
        db.commit()
        return Response(status_code=204, headers=PUBLIC_HEADERS)

    @routes.get("/submissions")
    def list_submissions(candidate_id: int, response: Response, db=Depends(get_db)):
        response.headers.update(PRIVATE_HEADERS)
        _candidate(db, candidate_id)
        rows = db.scalars(select(DocumentUploadSubmission).where(
            DocumentUploadSubmission.candidate_id == candidate_id,
            DocumentUploadSubmission.status.in_((RECEIVED, IN_REVIEW)),
        ).order_by(DocumentUploadSubmission.created_at.desc(), DocumentUploadSubmission.submission_id))
        return {
            "upload_enabled": public_upload_enabled(uploads_dir),
            "items": [_serialize_submission(row) for row in rows],
        }

    @routes.post("/submissions/{batch_id}/recognize", status_code=202)
    def recognize_submission(candidate_id: int, batch_id: str, response: Response, db=Depends(get_db)):
        response.headers.update(PRIVATE_HEADERS)
        _candidate(db, candidate_id, lock=True)
        submission = _submission(db, candidate_id, batch_id)
        if submission is None or submission.status == CLOSED:
            raise HTTPException(404, "file_not_found")
        rows = db.scalars(select(DocumentIntakeFile).where(
            DocumentIntakeFile.candidate_id == candidate_id, DocumentIntakeFile.batch_id == batch_id,
            DocumentIntakeFile.owner_id.is_(None),
        ).order_by(DocumentIntakeFile.position).with_for_update()).all()
        if not rows:
            raise HTTPException(404, "file_not_found")
        if submission.status == RECEIVED:
            for row in rows:
                row.result = {**row.result, "pending": True}
            submission.status = IN_REVIEW
            output = _serialize_batch(rows)
            db.commit()
            worker.wake.set()
            return output
        return _serialize_batch(rows)

    @routes.delete("/submissions/{batch_id}", status_code=204)
    def discard_submission(candidate_id: int, batch_id: str, db=Depends(get_db)):
        if not _finish_submission(db, candidate_id, batch_id, discard=True):
            raise HTTPException(404, "file_not_found")
        return Response(status_code=204, headers=PRIVATE_HEADERS)

    @routes.get("")
    def list_intake(candidate_id: int, response: Response, db=Depends(get_db), user=Depends(require_writer)):
        response.headers.update(PRIVATE_HEADERS)
        candidate = _candidate(db, candidate_id)
        catalog, records = intake_catalog(candidate)
        scans = defaultdict(list)
        for attachment in candidate.attachments:
            scans[attachment.source, attachment.description].append(attachment)
        batches = defaultdict(list)
        stmt = _query(candidate_id, user.user_id).order_by(
            DocumentIntakeFile.created_at, DocumentIntakeFile.position
        )
        for row in db.scalars(stmt):
            batches[row.batch_id].append(row)
        return {
            "candidate_name": " ".join(filter(None, (candidate.first_name, candidate.surname))),
            "catalog": [item.public() for item in catalog.values()],
            "existing": [
                _serialize_existing(item, key, row, scans[_relation(item), f"{_relation(item)}:{key}"])
                for item, key, row in _visible_records(records, candidate)
            ],
            "batches": [_serialize_batch(rows) for rows in batches.values()],
        }

    @routes.post("", status_code=202, dependencies=[Depends(reserve_upload_slot)])
    def upload_batch(candidate_id: int, response: Response, files: list[UploadFile] = File(...),
                     db=Depends(get_db), user=Depends(require_writer)):
        response.headers.update(PRIVATE_HEADERS)
        _candidate(db, candidate_id)
        if not 1 <= len(files) <= MAX_FILES:
            raise HTTPException(400, "batch_file_limit")
        batch_size = sum(file.size or 0 for file in files)
        if batch_size > MAX_BATCH:
            raise HTTPException(413, "batch_size_limit")
        if _draft_bytes(db) + batch_size > MAX_DRAFT_BYTES:
            raise HTTPException(409, "draft_storage_limit")
        owner_id = user.user_id
        batch_id = uuid4().hex
        rows = []
        now = _now()
        for index, file in enumerate(files):
            name, suffix = clean_upload_name(file.filename)
            result = {"type_key": None, "fields": {}, "warnings": [], "page_count": 0}
            row = DocumentIntakeFile(
                candidate_id=candidate_id, owner_id=owner_id, batch_id=batch_id, position=index,
                file_id=uuid4().hex, created_at=now, name=name, result=result,
            )
            rows.append(row)
            if suffix not in MEDIA_TYPES:
                result["error"] = "unsupported_file"
                continue
            content = file.file.read(MAX_FILE + 1)
            if not content or len(content) > MAX_FILE:
                result["error"] = "file_size_limit" if content else "empty_file"
                continue
            if not content.startswith(SIGNATURES[suffix]):
                result["error"] = "invalid_scan"
                continue
            result["pending"] = True
            row.content_type = MEDIA_TYPES[suffix]
            row.content = content
        _cleanup_drafts(db, now)
        db.add_all(rows)
        output = _serialize_batch(rows)
        db.commit()
        worker.wake.set()
        return output

    @routes.get("/{batch_id}/files/{file_id}")
    def preview(candidate_id: int, batch_id: str, file_id: str, page: int = 1,
                db=Depends(get_db), user=Depends(require_writer)):
        row = db.scalar(_query(candidate_id, user.user_id).where(
            DocumentIntakeFile.batch_id == batch_id, DocumentIntakeFile.file_id == file_id,
        ))
        if not row or row.result.get("pending") or not row.content_type or not row.content:
            raise HTTPException(404, "file_not_found")
        content, media_type = row.content, row.content_type
        if media_type == "application/pdf":
            if not 1 <= page <= row.result.get("page_count", 0):
                raise HTTPException(404, "page_not_found")
            try:
                content = render_preview_page(content, page)
            except Exception:
                raise HTTPException(400, "preview_failed") from None
            media_type = "image/png"
        return Response(content, media_type=media_type, headers={
            **PRIVATE_HEADERS, "Content-Security-Policy": "sandbox; default-src 'none'",
        })

    @routes.delete("/{batch_id}", status_code=204)
    def discard(candidate_id: int, batch_id: str, db=Depends(get_db), user=Depends(require_writer)):
        if _finish_submission(db, candidate_id, batch_id, discard=True):
            return Response(status_code=204)
        db.execute(delete(DocumentIntakeFile).where(
            DocumentIntakeFile.candidate_id == candidate_id, DocumentIntakeFile.owner_id == user.user_id,
            DocumentIntakeFile.batch_id == batch_id, DocumentIntakeFile.saved_key.is_(None),
        ))
        db.commit()
        return Response(status_code=204)

    @routes.post("/{batch_id}/retry", status_code=202)
    def retry_batch(candidate_id: int, batch_id: str, response: Response,
                    db=Depends(get_db), user=Depends(require_writer)):
        response.headers.update(PRIVATE_HEADERS)
        _candidate(db, candidate_id, lock=True)
        rows = db.scalars(_query(candidate_id, user.user_id).where(
            DocumentIntakeFile.batch_id == batch_id,
        ).options(defer(DocumentIntakeFile.content)).order_by(DocumentIntakeFile.position).with_for_update()).all()
        if not rows:
            raise HTTPException(404, "file_not_found")
        if any(row.result.get("pending") for row in rows):
            raise HTTPException(409, "batch_processing")
        failed = [row for row in rows if _can_retry(row)]
        if not failed:
            raise HTTPException(409, "nothing_to_retry")
        for row in failed:
            row.result = {"pending": True, **({"type_hint": row.result["type_hint"]} if row.result.get("type_hint") else {})}
        output = _serialize_batch(rows)
        db.commit()
        worker.wake.set()
        return output

    @routes.post("/{batch_id}/save")
    def save(candidate_id: int, batch_id: str, payload: Approvals, response: Response,
             db=Depends(get_db), user=Depends(require_writer)):
        response.headers.update(PRIVATE_HEADERS)
        results = []
        changed = False
        for approval in payload.documents:
            status = {"file_ids": approval.file_ids}
            try:
                changed |= _approve(db, candidate_id, user, batch_id, approval,
                                    allow_holder_override=not payload.bulk and len(payload.documents) == 1,
                                    uploads_dir=_uploads_path(uploads_dir), sync_rank=sync_rank)
                results.append({**status, "status": "saved"})
            except HTTPException as exc:
                if exc.detail != "save_outcome_unknown":
                    db.rollback()
                results.append({**status, "status": "error", "error": exc.detail})
            except Exception:
                db.rollback()
                logger.error("Document intake approval failed for candidate_id=%s", candidate_id)
                results.append({**status, "status": "error", "error": "save_failed"})
        if changed:
            try:
                sync_notifications(db, only_candidate_id=candidate_id)
            except Exception:
                db.rollback()
                logger.error("Document intake notification refresh failed")
        all_saved = all(result["status"] == "saved" for result in results)
        finished = all_saved and _finish_submission(db, candidate_id, batch_id, finish_selected=payload.finish_submission)
        return {"results": results, **({"submission_finished": True} if finished else {})}

    router.include_router(routes)
    return router
