from __future__ import annotations

import io
import random
import zipfile

import pypdfium2 as pdfium
import pytest
from PIL import Image

from app.submission_compression import SubmissionZipTooLargeError, build_size_limited_submission_zip


def _noisy_scan_pdf() -> bytes:
    image = Image.effect_noise((1400, 1800), 90).convert("RGB")
    output = io.BytesIO()
    image.save(output, format="PDF", quality=95, resolution=150)
    image.close()
    return output.getvalue()


def test_large_scan_is_compressed_to_requested_zip_limit():
    source_pdf = _noisy_scan_pdf()
    assert len(source_pdf) > 500_000

    archive_bytes = build_size_limited_submission_zip(
        [("COC.pdf", source_pdf), ("SB.pdf", source_pdf)],
        max_bytes=450_000,
    )

    assert len(archive_bytes) <= 450_000
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert archive.namelist() == ["COC.pdf", "SB.pdf"]
        for name in archive.namelist():
            rendered_pdf = archive.read(name)
            assert rendered_pdf.startswith(b"%PDF")
            document = pdfium.PdfDocument(rendered_pdf)
            assert len(document) == 1
            document.close()


def test_small_archive_keeps_original_file_bytes():
    original = b"small source document"
    archive_bytes = build_size_limited_submission_zip([("note.txt", original)])
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert archive.read("note.txt") == original


def test_oversized_non_compressible_files_return_clear_failure():
    with pytest.raises(SubmissionZipTooLargeError):
        build_size_limited_submission_zip(
            [("application.docx", random.Random(7).randbytes(200_000))],
            max_bytes=1_000,
        )
