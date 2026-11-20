"""Synthetic files only; optional real local OCR tests never download models."""

from pathlib import Path
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import document_intake_recognition as recognition


FIELDS = ["number", "issue_date", "expiry_date", "country", "authority", "place", "code", "holder_name", "unlimited_validity"]
CATALOG = [
    {"key": "document:SB", "label": "Seaman's Book", "kind": "document", "aliases": ["seaman book", "sb"], "fields": FIELDS},
    {"key": "document:TP", "label": "Travel Passport", "kind": "document", "aliases": ["passport"], "fields": FIELDS},
    {"key": "document:CP", "label": "Civil Passport", "kind": "document", "aliases": [], "fields": FIELDS},
    {"key": "certificate:AFF", "label": "Advanced Fire Fighting", "kind": "certificate", "aliases": ["advanced firefighting", "aff"], "fields": FIELDS},
]
TEXT = """SEAMAN'S BOOK
Document Number: SB123456
Full Name: ALEX TESTMAN
Date of Issue: 15.03.2024
Date of Expiry: 15.03.2034
Country of Issue: TESTLAND
Issuing Authority: Test Maritime Authority
Place of Issue: TEST PORT
"""


def text_pdf(path, pages):
    """Minimal real PDF with native text, without another test dependency."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode())
        content = b"BT /F1 14 Tf 40 740 Td 20 TL "
        for line in text.splitlines():
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content += f"({escaped}) Tj T* ".encode("ascii")
        content += b"ET"
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Count {len(kids)} /Kids [{' '.join(kids)}] >>".encode()
    output = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(output)
    output += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode()
    path.write_bytes(output)
    return path


def raster():
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 36) if font_path.exists() else ImageFont.load_default(size=36)
    image = Image.new("RGB", (1654, 1200), "white")
    ImageDraw.Draw(image).multiline_text((80, 80), TEXT, fill="black", font=font, spacing=22)
    return image


@pytest.fixture
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("native-text parsing must not run OCR")
    monkeypatch.setattr(recognition._OCR, "text", forbidden)


def test_native_pdf_contract(tmp_path, offline):
    result = recognition.recognize_document(text_pdf(tmp_path / "scan.pdf", [TEXT]), CATALOG)
    assert result["type_key"] == "document:SB"
    assert result["page_count"] == 1
    assert result["fields"] == {
        "number": "SB123456", "holder_name": "ALEX TESTMAN", "issue_date": "2024-03-15",
        "expiry_date": "2034-03-15", "country": "TESTLAND", "authority": "Test Maritime Authority", "place": "TEST PORT",
    }
    assert not result["warnings"]


@pytest.mark.parametrize("payload", [b"", b"not a document", b"%PDF-1.4\ncorrupt", b"\xff\xd8\xffbroken", b"\x89PNG\r\n\x1a\nbroken"])
def test_corrupt_is_value_error(tmp_path, payload):
    path = tmp_path / "scan.pdf"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        recognition.recognize_document(path, CATALOG)


def test_missing_file_is_value_error(tmp_path):
    with pytest.raises(ValueError):
        recognition.recognize_document(tmp_path / "missing", CATALOG)


def test_file_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, "MAX_FILE_BYTES", 4)
    path = tmp_path / "scan.png"
    path.write_bytes(b"12345")
    with pytest.raises(ValueError, match="size_limit"):
        recognition.recognize_document(path, CATALOG)


def test_pixel_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, "MAX_IMAGE_PIXELS", 10)
    path = tmp_path / "scan.png"
    with Image.new("RGB", (5, 5)) as image:
        image.save(path)
    with pytest.raises(ValueError, match="image_size_limit"):
        recognition.recognize_document(path, CATALOG)


def test_absent_ocr_keeps_valid_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, "_tesseract_executable", lambda: None)
    path = tmp_path / "scan.png"
    with raster() as image:
        image.save(path)
    result = recognition.recognize_document(path, CATALOG)
    assert result["fields"] == {}
    assert result["page_count"] == 1
    assert {"ocr_unavailable", "no_readable_text", "unknown_type"} <= set(result["warnings"])


def test_page_limit_retains_actual_count(tmp_path, monkeypatch, offline):
    monkeypatch.setattr(recognition, "MAX_PAGES", 1)
    result = recognition.recognize_document(text_pdf(tmp_path / "scan.pdf", [TEXT, TEXT]), CATALOG)
    assert result["page_count"] == 2
    assert "page_limit" in result["warnings"]


def test_multiple_documents_do_not_select_one(tmp_path, offline):
    other = TEXT.replace("SEAMAN'S BOOK", "ADVANCED FIRE FIGHTING").replace("SB123456", "AFF987654")
    result = recognition.recognize_document(text_pdf(tmp_path / "scan.pdf", [TEXT, other]), CATALOG)
    assert result["type_key"] is None
    assert "number" not in result["fields"]
    assert "multiple_document_types" in result["warnings"]
    assert "conflicting_field:number" in result["warnings"]


def test_dynamic_catalog_not_hardcoded():
    item = {"key": "custom:machinery", "label": "Experimental Machinery Training", "aliases": [], "kind": "certificate", "fields": FIELDS}
    assert recognition._classify(item["label"], [item], []) == item["key"]


def test_entire_actual_crm_catalog():
    from app.document_intake_catalog import CANONICAL
    catalog = [item.public() for item in CANONICAL]
    assert len(catalog) > 100
    for item in catalog:
        assert recognition._classify(item["label"], catalog, []) == item["key"], item["key"]


def test_specific_title_beats_generic():
    assert recognition._classify("Civil Passport", CATALOG, []) == "document:CP"


def test_short_alias_not_matched_inside_number():
    assert recognition._classify("Document Number: SB 12345", CATALOG, []) is None


def test_two_titles_are_ambiguous():
    warnings = []
    assert recognition._classify("Seaman's Book\nAdvanced Fire Fighting", CATALOG, warnings) is None
    assert warnings == ["ambiguous_type"]


def test_specific_course_subtitle_beats_generic_proficiency_heading():
    from app.document_intake_catalog import CANONICAL
    catalog = [item.public() for item in CANONICAL]
    assert recognition._classify(
        "Certificate of Proficiency\nAdvanced Fire Fighting Training\nIssued by Example Centre", catalog, [],
    ) == "certificate:AFF"
    assert recognition._classify(
        "Certificate of Proficiency\nIssued after the holder completed Advanced Fire Fighting Training", catalog, [],
    ) == "diploma:COP"


@pytest.mark.parametrize("value,expected", [("2025-12-31", "2025-12-31"), ("31/12/2025", "2025-12-31"),
    ("12/31/2025", "2025-12-31"), ("01.02.2025", "2025-02-01"), ("15 March 2025", "2025-03-15"),
    ("March 15, 2025", "2025-03-15")])
def test_valid_dates(value, expected):
    assert recognition._date_value(value) == (expected, None)


@pytest.mark.parametrize("value", ["01/02/2025", "02-01-2025"])
def test_ambiguous_dates_are_not_guessed(value):
    assert recognition._date_value(value) == (None, "ambiguous_date")


@pytest.mark.parametrize("value", ["31.02.2025", "15/03/25", "yesterday", "2025-13-01"])
def test_invalid_dates(value):
    assert recognition._date_value(value) == (None, "invalid_date")


def test_conflicts_and_date_order():
    warnings = []
    fields = recognition._fields("Document Number: AA123\nDocument Number: BB456\nIssue Date: 2030-01-15\nExpiry Date: 2029-01-15", warnings)
    assert not fields
    assert set(warnings) == {"conflicting_field:number", "date_order_invalid"}


def test_name_parts_and_birth_date_not_issue_date():
    fields = recognition._fields("Surname: TESTMAN\nGiven Names: ALEX\nDate of Birth: 1990-01-15", [])
    assert fields == {"holder_name": "ALEX TESTMAN"}


def test_inline_labels_and_last_first_name():
    fields = recognition._fields("Last Name: TESTMAN\nFirst Name: ALEX\nIssue Date: 2024-03-15 Expiry Date: 2034-03-15", [])
    assert fields == {"holder_name": "ALEX TESTMAN", "issue_date": "2024-03-15", "expiry_date": "2034-03-15"}


def test_dates_in_endorsement_sentences_and_bilingual_labels():
    assert recognition._fields(
        "This certificate was issued on 18.07.2024.\n"
        "The original certificate was issued on 18.07.2020.\n"
        "This endorsement is valid until 18.07.2029.\n"
        "Date of birth: 01.01.1990",
        [],
    ) == {"issue_date": "2024-07-18", "expiry_date": "2029-07-18"}
    assert recognition._fields("Datum / Date of issue 18.07.2024 at Example Office", []) == {
        "issue_date": "2024-07-18",
    }


def test_inline_dates_do_not_resolve_ambiguity_or_conflicts():
    warnings = []
    assert recognition._fields(
        "The certificate was issued on 01/02/2025.\n"
        "Date of issue: 2025-02-01\n"
        "Valid until: 2028-02-01\nIt is valid until 2029-02-01.",
        warnings,
    ) == {}
    assert "ambiguous_date:issue_date" in warnings
    assert "conflicting_field:expiry_date" in warnings


def test_conflicting_holder_is_not_reintroduced_from_parts():
    warnings = []
    fields = recognition._fields("Full Name: ALEX TESTMAN\nFull Name: SOMEONE ELSE\nSurname: TESTMAN\nGiven Names: ALEX", warnings)
    assert "holder_name" not in fields
    assert "conflicting_field:holder_name" in warnings


def test_ru_ua_labels_from_native_text():
    fields = recognition._fields("\u041d\u043e\u043c\u0435\u0440: AA123\n\u0414\u0430\u0442\u0430 \u0432\u0438\u0434\u0430\u0447\u0456: 15.03.2024\n\u0414\u0430\u0442\u0430 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f: 15.03.2034", [])
    assert fields == {"number": "AA123", "issue_date": "2024-03-15", "expiry_date": "2034-03-15"}


def test_next_line_fields_and_unlimited():
    fields = recognition._fields("Full Name:\nALEX TESTMAN\nDate of Expiry: Unlimited", [])
    assert fields == {"holder_name": "ALEX TESTMAN", "unlimited_validity": True}


def test_unlimited_conflict_is_not_saved():
    warnings = []
    assert recognition._fields("Expiry Date: Unlimited\nExpiry Date: 2034-12-31", warnings) == {}
    assert "conflicting_field:expiry_date" in warnings


def test_label_does_not_consume_next_label():
    assert recognition._fields("Document Number:\nCountry: TESTLAND", []) == {"country": "TESTLAND"}


def test_restricted_catalog_fields(tmp_path, offline):
    catalog = [{**CATALOG[0], "fields": ["number"]}]
    result = recognition.recognize_document(text_pdf(tmp_path / "scan.pdf", [TEXT]), catalog)
    assert result["fields"] == {"number": "SB123456", "holder_name": "ALEX TESTMAN"}


MRZ = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_td3_checks_and_fields():
    # ICAO sample first line padded to the full TD3 width.
    first, second = MRZ.splitlines()
    warnings = []
    fields = recognition._mrz_fields(first.ljust(44, "<") + "\n" + second, warnings)
    assert fields["number"] == "L898902C3"
    assert fields["holder_name"] == "ANNA MARIA ERIKSSON"
    assert fields["country"] == "UTO"
    assert "mrz_used" in warnings


def test_td3_bad_checksum_no_ocr_repair():
    first, second = MRZ.splitlines()
    warnings = []
    assert recognition._mrz_fields(first.ljust(44, "<") + "\n" + "X" + second[1:], warnings) == {}
    assert "mrz_invalid_check_digits" in warnings


def test_mrz_identifies_passport_without_title(tmp_path, offline):
    first, second = MRZ.splitlines()
    result = recognition.recognize_document(text_pdf(tmp_path / "passport.pdf", [first.ljust(44, "<") + "\n" + second]), CATALOG)
    assert result["type_key"] == "document:TP"
    assert result["fields"]["number"] == "L898902C3"


def test_mrz_does_not_overwrite_disagreement(tmp_path, offline):
    first, second = MRZ.splitlines()
    text = "Travel Passport\nDocument Number: XX12345\n" + first.ljust(44, "<") + "\n" + second
    result = recognition.recognize_document(text_pdf(tmp_path / "passport.pdf", [text]), CATALOG)
    assert "number" not in result["fields"]
    assert "conflicting_field:number" in result["warnings"]


def test_mrz_ambiguous_century_is_not_guessed(monkeypatch):
    from datetime import date
    class FutureDate(date):
        @classmethod
        def today(cls):
            return cls(2060, 1, 1)
    monkeypatch.setattr(recognition, "date", FutureDate)
    first, second = MRZ.splitlines()
    warnings = []
    fields = recognition._mrz_fields(first.ljust(44, "<") + "\n" + second, warnings)
    assert "expiry_date" not in fields
    assert "ambiguous_date:expiry_date" in warnings


def test_content_must_agree_with_supported_extension(tmp_path):
    path = tmp_path / "misnamed.pdf"
    with Image.new("RGB", (8, 8)) as image:
        image.save(path, "PNG")
    with pytest.raises(ValueError, match="content_type_mismatch"):
        recognition.recognize_document(path, CATALOG)


def test_document_deadline_retains_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, "DOCUMENT_TIMEOUT", -1)
    result = recognition.recognize_document(text_pdf(tmp_path / "scan.pdf", [TEXT]), CATALOG)
    assert result["fields"] == {}
    assert result["page_count"] == 1
    assert "recognition_time_limit" in result["warnings"]


def test_text_budget(tmp_path, monkeypatch, offline):
    monkeypatch.setattr(recognition, "MAX_TEXT_CHARS", 100)
    result = recognition.recognize_document(text_pdf(tmp_path / "scan.pdf", [TEXT]), CATALOG)
    assert "text_limit" in result["warnings"]


def test_timeout_returns_review_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, "_tesseract_executable", lambda: "tesseract")
    def run(args, *a, **kw):
        if "--list-langs" in args:
            return subprocess.CompletedProcess(args, 0, b"eng\n")
        raise subprocess.TimeoutExpired(args, 1)
    monkeypatch.setattr(recognition, "_run", run)
    path = tmp_path / "scan.png"
    with raster() as image:
        image.save(path)
    result = recognition.recognize_document(path, CATALOG)
    assert "ocr_timeout" in result["warnings"]
    assert result["page_count"] == 1


def test_ocr_releases_shared_pdfium_lock(tmp_path, monkeypatch):
    from app.document_intake_pdf import PDFIUM_LOCK
    def text(self, image):
        assert not PDFIUM_LOCK._is_owned()
        return TEXT
    monkeypatch.setattr(recognition._OCR, "text", text)
    path = tmp_path / "scan.pdf"
    with raster() as image:
        image.save(path, "PDF")
    assert recognition.recognize_document(path, CATALOG)["type_key"] == "document:SB"


@pytest.mark.parametrize("format,suffix", [("PNG", ".png"), ("JPEG", ".jpg"), ("PDF", ".pdf")])
def test_real_local_ocr_smoke(tmp_path, monkeypatch, format, suffix):
    if not recognition._tesseract_executable():
        pytest.skip("Requires locally installed Tesseract; never installs or downloads")
    monkeypatch.setenv("DOCUMENT_INTAKE_OCR_LANGS", "eng")
    path = tmp_path / ("synthetic" + suffix)
    with raster() as image:
        image.save(path, format)
    result = recognition.recognize_document(path, CATALOG)
    assert "ocr_used" in result["warnings"], result
    assert result["type_key"] == "document:SB", result
    assert result["fields"]["number"] == "SB123456", result
    assert result["fields"]["holder_name"] == "ALEX TESTMAN", result
    assert result["fields"]["issue_date"] == "2024-03-15", result
    assert result["fields"]["expiry_date"] == "2034-03-15", result
    assert result["page_count"] == 1
