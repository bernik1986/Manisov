from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

MAX_SUBMISSION_ZIP_BYTES = 5_000_000


@dataclass(frozen=True)
class CompressionProfile:
    pdf_scale: float
    image_max_side: int
    jpeg_quality: int


COMPRESSION_PROFILES = (
    CompressionProfile(pdf_scale=2.0, image_max_side=2000, jpeg_quality=88),
    CompressionProfile(pdf_scale=1.7, image_max_side=1800, jpeg_quality=84),
    CompressionProfile(pdf_scale=1.45, image_max_side=1600, jpeg_quality=78),
    CompressionProfile(pdf_scale=1.2, image_max_side=1400, jpeg_quality=70),
    CompressionProfile(pdf_scale=1.0, image_max_side=1200, jpeg_quality=62),
    CompressionProfile(pdf_scale=0.85, image_max_side=1000, jpeg_quality=52),
    CompressionProfile(pdf_scale=0.7, image_max_side=800, jpeg_quality=42),
)


class SubmissionZipTooLargeError(Exception):
    def __init__(self, actual_bytes: int, max_bytes: int):
        super().__init__(f"Submission ZIP is {actual_bytes} bytes; limit is {max_bytes} bytes")
        self.actual_bytes = actual_bytes
        self.max_bytes = max_bytes


def _build_zip(entries: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


def _rgb_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image.copy()


def _compress_image(data: bytes, suffix: str, profile: CompressionProfile) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = _rgb_image(source)
        image.thumbnail((profile.image_max_side, profile.image_max_side), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        if suffix in {".jpg", ".jpeg"}:
            image.save(output, format="JPEG", quality=profile.jpeg_quality, optimize=True)
        else:
            image.save(output, format="PNG", optimize=True, compress_level=9)
        image.close()
        compressed = output.getvalue()
        return compressed if len(compressed) < len(data) else data
    except Exception:
        return data


def _compress_pdf(data: bytes, profile: CompressionProfile) -> bytes:
    images: list[Image.Image] = []
    document = None
    try:
        document = pdfium.PdfDocument(data)
        for index in range(len(document)):
            page = document[index]
            bitmap = page.render(scale=profile.pdf_scale)
            image = _rgb_image(bitmap.to_pil())
            bitmap.close()
            page.close()
            images.append(image)
        if not images:
            return data
        output = io.BytesIO()
        images[0].save(
            output,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            quality=profile.jpeg_quality,
            optimize=True,
            resolution=72 * profile.pdf_scale,
        )
        compressed = output.getvalue()
        return compressed if len(compressed) < len(data) else data
    except Exception:
        return data
    finally:
        for image in images:
            image.close()
        if document is not None:
            document.close()


def _compress_entry(name: str, data: bytes, profile: CompressionProfile) -> bytes:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return _compress_pdf(data, profile)
    if suffix in {".jpg", ".jpeg", ".png"}:
        return _compress_image(data, suffix, profile)
    return data


def build_size_limited_submission_zip(
    entries: list[tuple[str, bytes]],
    *,
    max_bytes: int = MAX_SUBMISSION_ZIP_BYTES,
) -> bytes:
    """Build the best-quality ZIP that fits the limit without changing source files."""
    archive = _build_zip(entries)
    if len(archive) <= max_bytes:
        return archive

    smallest_archive = archive
    for profile in COMPRESSION_PROFILES:
        compressed_entries = [(name, _compress_entry(name, data, profile)) for name, data in entries]
        candidate = _build_zip(compressed_entries)
        if len(candidate) < len(smallest_archive):
            smallest_archive = candidate
        if len(candidate) <= max_bytes:
            return candidate

    raise SubmissionZipTooLargeError(len(smallest_archive), max_bytes)
