from __future__ import annotations

import io
from typing import Iterable

from PIL import Image, ImageOps

from models.schema import Attachment

CANDIDATE_PHOTO_SOURCE = "candidate_photo"
CANDIDATE_PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
CANDIDATE_PHOTO_MEDIA_TYPE = "image/jpeg"
CANDIDATE_PHOTO_MAX_SIZE = (1600, 2000)


def prepare_candidate_photo_bytes(content: bytes) -> bytes:
    """Validate, orient and normalize an uploaded portrait to a compact JPEG."""
    try:
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail(CANDIDATE_PHOTO_MAX_SIZE, Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue()
    except Exception as exc:
        raise ValueError("Invalid or unsupported image file") from exc


def find_candidate_photo(attachments: Iterable[Attachment]) -> Attachment | None:
    photos = [item for item in attachments if (item.source or "").strip() == CANDIDATE_PHOTO_SOURCE]
    if not photos:
        return None
    return max(photos, key=lambda item: (item.uploaded_at, item.attachment_id or 0))
