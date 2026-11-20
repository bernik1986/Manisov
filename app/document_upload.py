"""Validate a candidate's public upload and assemble ordered photo pages."""

from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.document_intake_pdf import merge_photo_pages

MEDIA_TYPES = {".pdf": "application/pdf", ".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png"}
SIGNATURES = {".pdf": b"%PDF-", ".jpeg": b"\xff\xd8\xff", ".jpg": b"\xff\xd8\xff", ".png": b"\x89PNG\r\n\x1a\n"}
MAX_FILES = 40
MAX_FILE = 15 * 1024 * 1024
MAX_BATCH = 45 * 1024 * 1024
MAX_PAGES = 20  # Also the maximum number of pages the intake worker recognizes.
MAX_PENDING_SUBMISSIONS = 10
MAX_BODY = MAX_BATCH + 128 * 1024

PUBLIC_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, nofollow",
}


class PageGroup(BaseModel):
    type_key: str = Field(min_length=1, max_length=500)
    page_count: int = Field(ge=1, le=MAX_PAGES)


class SubmissionManifest(BaseModel):
    request_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    documents: list[PageGroup] = Field(default_factory=list, max_length=MAX_FILES)


def clean_upload_name(filename):
    name = PurePosixPath((filename or "scan").replace("\\", "/")).name
    name = "".join(c for c in name if c.isprintable()) or "scan"
    suffix = Path(name).suffix.lower()
    return (name[:240] + suffix if len(name) > 255 else name), suffix


async def parse_upload_form(request: Request):
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "multipart/form-data":
        raise HTTPException(400, "invalid_manifest", headers=PUBLIC_HEADERS)
    length = request.headers.get("content-length")
    if length and length.isdecimal() and int(length) > MAX_BODY:
        raise HTTPException(413, "batch_size_limit", headers=PUBLIC_HEADERS)

    async def bounded_stream():
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY:
                raise MultiPartException("batch_size_limit")
            yield chunk

    try:
        return await MultiPartParser(
            request.headers, bounded_stream(), max_files=MAX_FILES, max_fields=1, max_part_size=24 * 1024,
        ).parse()
    except MultiPartException as exc:
        if exc.message == "batch_size_limit":
            raise HTTPException(413, "batch_size_limit", headers=PUBLIC_HEADERS) from None
        code = "batch_file_limit" if exc.message.startswith("Too many files") else "invalid_manifest"
        raise HTTPException(400, code, headers=PUBLIC_HEADERS) from None
    except ValueError:
        raise HTTPException(400, "invalid_manifest", headers=PUBLIC_HEADERS) from None


def _read_file(file: UploadFile, *, photo=False):
    name, suffix = clean_upload_name(file.filename)
    if suffix not in MEDIA_TYPES or (photo and suffix == ".pdf"):
        raise HTTPException(400, "unsupported_file", headers=PUBLIC_HEADERS)
    content = file.file.read(MAX_FILE + 1)
    if len(content) > MAX_FILE:
        raise HTTPException(413, "file_size_limit", headers=PUBLIC_HEADERS)
    if not content:
        raise HTTPException(400, "empty_file", headers=PUBLIC_HEADERS)
    if not content.startswith(SIGNATURES[suffix]):
        raise HTTPException(400, "invalid_scan", headers=PUBLIC_HEADERS)
    return name, MEDIA_TYPES[suffix], content


def _photos_to_pdf(pages):
    try:
        return merge_photo_pages((_read_file(photo, photo=True)[2] for photo in pages), MAX_FILE)
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(400, "invalid_scan", headers=PUBLIC_HEADERS) from None


def read_submission_manifest(form):
    try:
        manifest = SubmissionManifest.model_validate_json(form["manifest"], strict=True)
    except (KeyError, TypeError, ValidationError):
        raise HTTPException(400, "invalid_manifest", headers=PUBLIC_HEADERS) from None
    files, pages = form.getlist("files"), form.getlist("pages")
    if set(form) - {"manifest", "files", "pages"} or any(
        not isinstance(file, UploadFile) for file in (*files, *pages)
    ) or sum(group.page_count for group in manifest.documents) != len(pages):
        raise HTTPException(400, "invalid_manifest", headers=PUBLIC_HEADERS)
    if not 1 <= len(files) + len(pages) <= MAX_FILES:
        raise HTTPException(400, "batch_file_limit", headers=PUBLIC_HEADERS)
    if sum(file.size or 0 for file in (*files, *pages)) > MAX_BATCH:
        raise HTTPException(413, "batch_size_limit", headers=PUBLIC_HEADERS)
    return manifest, files, pages


def prepare_submission_files(manifest, files, pages, labels):
    if any(group.type_key not in labels for group in manifest.documents):
        raise HTTPException(400, "type_required", headers=PUBLIC_HEADERS)
    prepared = [(*_read_file(file), None) for file in files]
    offset = 0
    for group in manifest.documents:
        pdf = _photos_to_pdf(pages[offset:offset + group.page_count])
        if len(pdf) > MAX_FILE:
            raise HTTPException(413, "file_size_limit", headers=PUBLIC_HEADERS)
        offset += group.page_count
        name, _ = clean_upload_name(labels[group.type_key] + ".pdf")
        prepared.append((name, "application/pdf", pdf, group.type_key))
    if sum(len(content) for _, _, content, _ in prepared) > MAX_BATCH:
        raise HTTPException(413, "batch_size_limit", headers=PUBLIC_HEADERS)
    return prepared
