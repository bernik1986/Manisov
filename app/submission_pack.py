"""Build submission (ПОДАЧА) ZIP packs: generated DOCX + selected attachment scans."""

from __future__ import annotations

import re
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.attachment_naming import attachment_download_filename, safe_file_part, safe_scan_part
from app.template_renderer import (
    SUPPORTED_RENDER_TEMPLATE_SUFFIXES,
    build_generated_template_name,
    render_template_to_file,
)
from models.schema import Attachment, Candidate, TemplateFile, TemplateFolder

PODACHA_BUILTIN_TEMPLATE_NAMES = (
    "инфо лист для подачи новых кандидатов.docx",
    "инфо лист для подачи эксов.docx",
)


def augment_submission_pack_context(context: dict[str, Any], modal: dict[str, Any]) -> None:
    """Merge modal-only fields and derived display strings for info-list templates."""
    opening = str(modal.get("opening_vessel") or "").strip()
    previous = str(modal.get("previous_vessel") or "").strip()
    context["opening_vessel"] = opening or context.get("candidate_for_vessel") or ""
    context["previous_vessel"] = previous

    if not str(context.get("passport_visa_status_note") or "").strip():
        context["passport_visa_status_note"] = context.get("visa_status_note") or ""

    applications = context.get("applications") or []
    first_app = applications[0] if applications else {}
    if not isinstance(first_app, dict):
        first_app = {}
    date_avail = first_app.get("date_available") or ""
    context["date_available_display"] = date_avail if str(date_avail).strip() else "Ready"

    salary = context.get("desirable_salary_usd")
    if salary in (None, ""):
        salary = first_app.get("last_salary_usd")
    rj = context.get("rejoin_bonus_usd")
    salary_parts: list[str] = []
    if salary not in (None, ""):
        try:
            salary_parts.append(f"{int(float(salary))}$")
        except (TypeError, ValueError):
            salary_parts.append(str(salary))
    if rj not in (None, ""):
        try:
            salary_parts.append(f"+{int(float(rj))}$ RJ")
        except (TypeError, ValueError):
            salary_parts.append(f"+{rj} RJ")
    context["desirable_salary_display"] = " ".join(salary_parts)

    context["contract_duration_display"] = context.get("submission_contract_duration_text") or ""

    rank = context.get("current_rank") or context.get("rank") or ""
    since_year = context.get("watch_officer_since_year")
    if since_year:
        context["rank_since_sentence"] = f"The gent has been working in the rank of {rank} since {since_year}."
    else:
        years = context.get("years_in_rank")
        if years not in (None, ""):
            context["rank_since_sentence"] = (
                f"The gent has been working in the rank of {rank} ({years} years in rank)."
            )
        else:
            context["rank_since_sentence"] = f"The gent has been working in the rank of {rank}."

    if context.get("coc_has_qr_codes"):
        context["coc_qr_paragraph"] = (
            "Kindly be informed the gent's COC&Endorsement and COC GMDSS & Endorsement are with QR codes."
        )
    else:
        context["coc_qr_paragraph"] = ""

    if not str(context.get("coc_gmdss_expiry_note") or "").strip():
        coc_exp = context.get("coc_expiry_date") or ""
        if coc_exp:
            context["coc_gmdss_expiry_note"] = (
                "Kindly be informed that the gent's COC & Endorsement and GMDSS COC & Endorsement "
                f"expire on {coc_exp}."
            )

    usa_exp = context.get("usa_visa_expiry_date") or ""
    context["usa_visa_valid_paragraph"] = (
        f"Kindly be informed that the gent's USA visa valid till {usa_exp}." if usa_exp else ""
    )

    sb_exp = context.get("seaman_book_expiry_date") or ""
    context["sb_expiry_paragraph"] = (
        f"Kindly be informed, that the gent's SB will expire on {sb_exp}." if sb_exp else ""
    )

    context["rank"] = rank
    context["gent_name"] = " ".join(
        part
        for part in [
            str(context.get("first_name") or "").strip(),
            str(context.get("surname") or "").strip(),
        ]
        if part
    ).strip() or str(context.get("full_name") or "").strip()


def resolve_template_path(
    db_session: Session,
    *,
    templates_dir: Path,
    templates_manager_dir: Path,
    template_file_id: int,
) -> tuple[Path, str]:
    managed = db_session.get(TemplateFile, template_file_id)
    if not managed:
        raise HTTPException(status_code=404, detail=f"Template file id {template_file_id} not found")
    resolved = templates_manager_dir / managed.relative_path
    if not resolved.exists():
        discovered = next(templates_manager_dir.rglob(f"*{managed.file_name}"), None)
        if discovered and discovered.exists():
            resolved = discovered
        else:
            discovered = next(templates_dir.rglob(f"*{managed.file_name}"), None)
            if discovered and discovered.exists():
                resolved = discovered
    if not resolved.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Template file not found on disk: {managed.file_name} "
                f"(expected under templates manager, relative_path={managed.relative_path})"
            ),
        )
    if resolved.suffix.lower() not in SUPPORTED_RENDER_TEMPLATE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only DOCX/XLSX/XLSM templates can be included in submission pack.")
    return resolved, managed.file_name


def resolve_builtin_template_path(templates_dir: Path, file_name: str) -> Path:
    path = templates_dir / "Podacha" / file_name
    if not path.exists():
        path = templates_dir / file_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Template not found: {file_name}")
    return path


def build_output_docx_name(candidate: Candidate, template_stem: str) -> str:
    return build_generated_template_name(candidate, template_stem, ".docx")


def render_docx_template(template_path: Path, context: dict[str, Any], output_path: Path) -> None:
    render_template_to_file(template_path, context, output_path)


def build_submission_zip(
    *,
    db_session: Session,
    candidate: Candidate,
    templates_dir: Path,
    templates_manager_dir: Path,
    generated_dir: Path,
    serialize_context,
    modal_fields: dict[str, Any],
    template_file_ids: list[int],
    attachment_ids: list[int],
) -> tuple[bytes, str]:
    if not template_file_ids and not attachment_ids:
        raise HTTPException(status_code=400, detail="Select at least one template or attachment for the pack.")

    base_context = serialize_context(candidate)
    augment_submission_pack_context(base_context, modal_fields)

    zip_buffer = BytesIO()
    used_names: set[str] = set()

    def unique_zip_name(name: str) -> str:
        base = safe_scan_part(Path(name).stem) or "file"
        ext = Path(name).suffix or ""
        candidate_name = f"{base}{ext}"
        if candidate_name not in used_names:
            used_names.add(candidate_name)
            return candidate_name
        idx = 2
        while True:
            alt = f"{base}_{idx}{ext}"
            if alt not in used_names:
                used_names.add(alt)
                return alt
            idx += 1

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for template_file_id in template_file_ids:
            template_path, template_file_name = resolve_template_path(
                db_session,
                templates_dir=templates_dir,
                templates_manager_dir=templates_manager_dir,
                template_file_id=template_file_id,
            )
            output_name = build_generated_template_name(candidate, Path(template_file_name).stem, template_path.suffix)
            output_path = generated_dir / output_name
            render_template_to_file(template_path, base_context, output_path)
            zf.write(output_path, arcname=unique_zip_name(output_name))

        if attachment_ids:
            rows = (
                db_session.query(Attachment)
                .filter(
                    Attachment.candidate_id == candidate.candidate_id,
                    Attachment.attachment_id.in_(attachment_ids),
                )
                .all()
            )
            found_ids = {row.attachment_id for row in rows}
            missing = [aid for aid in attachment_ids if aid not in found_ids]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Attachments not found for this candidate: {missing}",
                )
            for row in rows:
                file_path = Path(row.file_path)
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail=f"Attachment file missing: {row.file_name}")
                display_name = attachment_download_filename(db_session, candidate, row)
                arcname = unique_zip_name(display_name)
                zf.write(file_path, arcname=arcname)

    surname = safe_file_part(candidate.surname or "candidate")
    zip_name = f"PODACHA_{surname}_{candidate.candidate_id}_{uuid4().hex[:8]}.zip"
    return zip_buffer.getvalue(), zip_name


def ensure_podacha_builtin_templates(
    db_session: Session,
    *,
    templates_dir: Path,
    templates_manager_dir: Path,
    get_or_create_root: Callable[[Session], TemplateFolder],
) -> None:
    """Register shipped Podacha DOCX files in templates manager when missing."""
    podacha_src_dir = templates_dir / "Podacha"
    if not podacha_src_dir.is_dir():
        return

    root = get_or_create_root(db_session)
    folder = (
        db_session.query(TemplateFolder)
        .filter(TemplateFolder.parent_id == root.folder_id, TemplateFolder.name == "Подача")
        .one_or_none()
    )
    if not folder:
        folder = TemplateFolder(name="Подача", parent_id=root.folder_id)
        db_session.add(folder)
        db_session.flush()

    for file_name in PODACHA_BUILTIN_TEMPLATE_NAMES:
        src = podacha_src_dir / file_name
        if not src.is_file():
            continue
        existing = (
            db_session.query(TemplateFile)
            .filter(TemplateFile.folder_id == folder.folder_id, TemplateFile.file_name == file_name)
            .one_or_none()
        )
        if existing:
            target_path = templates_manager_dir / existing.relative_path
            if target_path.is_file():
                continue
            stored_name = existing.relative_path
        else:
            stored_name = f"{uuid4().hex}.docx"
        target_path = templates_manager_dir / stored_name
        shutil.copy2(src, target_path)
        size = target_path.stat().st_size
        if existing:
            existing.file_size_bytes = size
        else:
            db_session.add(
                TemplateFile(
                    folder_id=folder.folder_id,
                    file_name=file_name,
                    file_type="docx",
                    stored_name=stored_name,
                    relative_path=stored_name,
                    file_size_bytes=size,
                )
            )
    db_session.commit()
