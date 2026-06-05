"""Convert candidate scan uploads to PDF (images only; existing PDF unchanged)."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import HTTPException
from PIL import Image

IMAGE_ATTACHMENT_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
PDF_ATTACHMENT_SUFFIX = ".pdf"
STORED_ATTACHMENT_SUFFIX = PDF_ATTACHMENT_SUFFIX
STORED_ATTACHMENT_MEDIA_TYPE = "application/pdf"


def image_bytes_to_pdf(content: bytes) -> bytes:
    """Raster image bytes → single-page PDF."""
    try:
        with Image.open(io.BytesIO(content)) as img:
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode == "P":
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="PDF")
            return out.getvalue()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid or unsupported image file") from exc


def prepare_attachment_bytes(suffix: str, content: bytes) -> tuple[bytes, str, str]:
    """
    Return (bytes to store on disk, stored suffix, media type).

    Images become PDF; PDF is stored as-is.
    """
    normalized = suffix.lower()
    if normalized in IMAGE_ATTACHMENT_SUFFIXES:
        pdf_bytes = image_bytes_to_pdf(content)
        return pdf_bytes, STORED_ATTACHMENT_SUFFIX, STORED_ATTACHMENT_MEDIA_TYPE
    if normalized == PDF_ATTACHMENT_SUFFIX:
        if not content.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="Invalid PDF file")
        return content, PDF_ATTACHMENT_SUFFIX, STORED_ATTACHMENT_MEDIA_TYPE
    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Allowed extensions: .jpeg, .jpg, .png, .pdf",
    )


def stored_file_suffix_from_path(file_path: str | Path) -> str:
    return Path(file_path).suffix.lower() or STORED_ATTACHMENT_SUFFIX
