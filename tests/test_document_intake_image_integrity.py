"""Check real OCR input and rendered PDF pixels, not just conversion success."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
import pypdfium2 as pdfium
import pytest
from sqlalchemy import select

from app import document_intake_recognition as recognition
from app.attachment_convert import image_bytes_to_pdf
from models.schema import Attachment, DocumentIntakeFile
from parser.pdfium_runtime import PDFIUM_LOCK
from tests import test_document_intake as support
from tests.test_document_intake import ROOT, _approval, _save, _wait_batch, intake


def _transparent_png(kind):
    mode = {"palette_index": "P", "palette_alpha": "P", "rgb_key": "RGB", "gray_key": "L"}.get(kind, kind)
    background = {"RGBA": (0, 0, 0, 0), "LA": (0, 0), "P": 0, "RGB": (0, 0, 0), "L": 0}[mode]
    ink = {"RGBA": (0, 0, 0, 255), "LA": (0, 255), "P": 1, "RGB": (1, 1, 1), "L": 1}[mode]
    with Image.new(mode, (80, 60), background) as image, BytesIO() as stream:
        if mode == "P":
            image.putpalette([0, 0, 0] * 256)
        image.paste(ink, (20, 20, 40, 40))
        if kind in {"RGBA", "LA", "palette_alpha"}:
            partial = {"RGBA": (0, 0, 0, 128), "LA": (0, 128), "P": 2}[mode]
            image.paste(partial, (50, 20, 70, 40))
        options = {}
        if kind == "palette_index" or kind == "gray_key":
            options["transparency"] = 0
        elif kind == "palette_alpha":
            options["transparency"] = bytes([0, 255, 128])
        elif kind == "rgb_key":
            options["transparency"] = (0, 0, 0)
        image.save(stream, format="PNG", **options)
        return stream.getvalue()


def _render(content):
    with PDFIUM_LOCK, pdfium.PdfDocument(content) as document:
        page = document[0]
        try:
            bitmap = page.render(scale=1)
            try:
                with bitmap.to_pil() as image:
                    return image.convert("RGB")
            finally:
                bitmap.close()
        finally:
            page.close()


@pytest.mark.parametrize("kind", ["RGBA", "LA", "palette_index", "palette_alpha", "rgb_key", "gray_key"])
def test_transparency_survives_ocr_and_approved_pdf(intake, monkeypatch, kind):
    client, sessions, _ = intake
    content = _transparent_png(kind)
    inspected = []

    def ocr(_self, image):
        assert image.mode == "RGB"
        assert image.getpixel((5, 5)) == (255, 255, 255)
        assert max(image.getpixel((30, 30))) <= 1
        if kind in {"RGBA", "LA", "palette_alpha"}:
            assert image.getpixel((60, 30)) == (127, 127, 127)
        inspected.append(True)
        return ""

    monkeypatch.setattr(recognition._OCR, "text", ocr)
    monkeypatch.setattr(support, "_recognize", recognition.recognize_document)
    response = client.post(ROOT, files=[("files", ("transparent.png", content, "image/png"))])
    assert response.status_code == 202
    batch = _wait_batch(client, response.json()["batch_id"])
    assert inspected == [True]
    assert "no_readable_text" in batch["items"][0]["warnings"]
    assert _save(client, batch, _approval(batch["items"]))[0]["status"] == "saved"
    with sessions() as db:
        attachment = db.scalars(select(Attachment)).one()
        with _render(Path(attachment.file_path).read_bytes()) as image:
            assert image.size == (80, 60)
            assert min(image.getpixel((5, 5))) >= 250
            assert max(image.getpixel((30, 30))) <= 5
            if kind in {"RGBA", "LA", "palette_alpha"}:
                assert all(120 <= channel <= 135 for channel in image.getpixel((60, 30)))
        draft = db.get(DocumentIntakeFile, batch["items"][0]["file_id"])
        assert draft.content is None and draft.saved_key


@pytest.mark.parametrize("orientation", range(1, 9))
def test_standalone_pdf_honors_all_exif_orientations(orientation):
    with Image.new("RGB", (120, 80), "white") as source, BytesIO() as stream:
        source.paste("red", (0, 0, 60, 40))
        source.paste("green", (60, 0, 120, 40))
        source.paste("blue", (0, 40, 60, 80))
        exif = Image.Exif()
        exif[274] = orientation
        source.save(stream, format="JPEG", quality=95, exif=exif)
        content = stream.getvalue()
    with Image.open(BytesIO(content)) as source, ImageOps.exif_transpose(source) as expected:
        with _render(image_bytes_to_pdf(content)) as actual:
            assert actual.size == expected.size
            for x, y in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):
                point = (int(actual.width * x), int(actual.height * y))
                assert all(abs(a - b) <= 5 for a, b in zip(actual.getpixel(point), expected.getpixel(point)))


def test_camera_orientation_survives_approval(intake):
    client, sessions, _ = intake
    with Image.new("RGB", (60, 30), "red") as source, BytesIO() as stream:
        exif = Image.Exif()
        exif[274] = 6
        source.save(stream, format="JPEG", exif=exif)
        response = client.post(ROOT, files=[("files", ("camera.jpg", stream.getvalue(), "image/jpeg"))])
    assert response.status_code == 202
    batch = _wait_batch(client, response.json()["batch_id"])
    assert _save(client, batch, _approval(batch["items"]))[0]["status"] == "saved"
    with sessions() as db:
        attachment = db.scalars(select(Attachment)).one()
        with _render(Path(attachment.file_path).read_bytes()) as image:
            assert image.size == (30, 60)
            assert image.getpixel((15, 30))[0] >= 250
        assert db.get(DocumentIntakeFile, batch["items"][0]["file_id"]).content is None
