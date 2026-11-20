"""Isolated native PDF operations for previews and ordered photo uploads."""

from io import BytesIO
from math import isfinite
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from app.document_intake_runtime import recognition_environment
from parser.pdfium_runtime import PDFIUM_LOCK


MAX_SOURCE_PIXELS = 50_000_000
MAX_IMAGE_EDGE = 2400


def _preview(path, page_number):
    with PDFIUM_LOCK, pdfium.PdfDocument(path) as document:
        if not 1 <= page_number <= len(document):
            raise ValueError("Page out of range")
        page = document[page_number - 1]
        try:
            width, height = page.get_size()
            if any(not isfinite(value) or value <= 0 for value in (width, height)):
                raise ValueError("Invalid page dimensions")
            scale = min(2.0, 1800 / max(width, height))
            bitmap = page.render(scale=scale)
            try:
                with bitmap.to_pil() as image, BytesIO() as output:
                    image.save(output, format="PNG")
                    return output.getvalue()
            finally:
                bitmap.close()
        finally:
            page.close()


def _merge(paths, target):
    with PDFIUM_LOCK, pdfium.PdfDocument.new() as merged:
        for path in paths:
            with Image.open(path, formats=("JPEG", "PNG")) as source, BytesIO() as single:
                if source.width * source.height > MAX_SOURCE_PIXELS or getattr(source, "is_animated", False):
                    raise ValueError("Photo must be a single image within the pixel limit")
                source.load()
                source.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
                with ImageOps.exif_transpose(source) as oriented, oriented.convert("RGBA") as rgba:
                    with Image.new("RGB", oriented.size, "white") as image:
                        image.paste(rgba, mask=rgba.getchannel("A"))
                        image.save(single, format="PDF", resolution=150, quality=88)
                with pdfium.PdfDocument(single.getvalue()) as page:
                    merged.import_pages(page)
        merged.save(target)


def _pdf_job(operation, inputs, output_limit):
    # Existing questionnaire and submission-pack code also calls PDFium in
    # the web process. Isolate intake so none of those callers need to change.
    with TemporaryDirectory(prefix="manisov-intake-pdf-") as folder:
        target = Path(folder) / "result"
        paths = []
        for index, content in enumerate(inputs):
            path = Path(folder) / str(index)
            path.write_bytes(content)
            paths.append(str(path))
        try:
            process = subprocess.run(
                [sys.executable, "-m", "app.document_intake_pdf", operation, str(target), *paths],
                cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                env=recognition_environment(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise ValueError("invalid_scan") from None
        if process.returncode:
            raise ValueError("invalid_scan")
        with target.open("rb") as stream:
            return stream.read(output_limit + 1)


def merge_photo_pages(inputs, output_limit):
    return _pdf_job("merge", inputs, output_limit)


def render_preview_page(content: bytes, page_number: int) -> bytes:
    return _pdf_job(str(page_number), [content], 16 * 1024 * 1024)


if __name__ == "__main__":
    operation, output, *sources = sys.argv[1:]
    if operation == "merge":
        _merge(sources, output)
    else:
        Path(output).write_bytes(_preview(sources[0], int(operation)))
