"""Offline document intake. No network clients or automatic provider selection.

Requires Pillow, pypdfium2 and a local Tesseract installation with eng.traineddata.
Windows discovery includes Program Files/Tesseract-OCR (no PATH change needed).
DOCUMENT_INTAKE_TESSERACT may specify the executable; DOCUMENT_INTAKE_OCR_LANGS
defaults to eng+rus+ukr. Install additional traineddata locally for those languages.
Absent OCR/languages produce review warnings, never a cloud fallback. Warning
identifiers are stable machine-readable codes; suffixed field codes identify the
field requiring review. Dates are ISO strings and unknown fields are omitted.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import warnings as python_warnings
from datetime import date
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError

from app.attachment_convert import image_on_white


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_RENDER_PIXELS = 10_000_000
MAX_PAGES = 20
MAX_TEXT_CHARS = 100_000
OCR_TIMEOUT = 20
DOCUMENT_TIMEOUT = 120


class RecognitionProvider(Protocol):
    """Future explicitly configured adapters must obey this same review contract.

    This module implements only local recognition. Declaring this interface does
    not enable external providers or grant permission to transmit documents.
    """

    def recognize_document(self, path: Path, catalog: list[dict], *, deadline: float | None = None) -> dict: ...


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def _tesseract_executable() -> str | None:
    explicit = os.getenv("DOCUMENT_INTAKE_TESSERACT")
    if explicit:
        return str(Path(explicit)) if Path(explicit).is_file() else None
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt":
        for base in (os.getenv("ProgramFiles", "C:/Program Files"), os.getenv("ProgramFiles(x86)", "")):
            executable = Path(base) / "Tesseract-OCR" / "tesseract.exe"
            if executable.is_file():
                return str(executable)
    return None


def _run(args: list[str], timeout: float, **kwargs):
    # Do not invoke a shell or expose document content in stderr/logs.
    from app.document_intake_runtime import recognition_environment

    kwargs["env"] = recognition_environment()
    return subprocess.run(
        args, timeout=max(0.1, timeout), check=True, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs,
    )


class _OCR:
    def __init__(self, deadline: float, warnings: list[str]):
        self.deadline, self.warnings = deadline, warnings
        self.executable = None
        self.languages = None
        self.checked = False

    def text(self, image: Image.Image) -> str:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.warnings.append("recognition_time_limit")
            return ""
        if not self.checked:
            self.checked = True
            self.executable = _tesseract_executable()
            if not self.executable:
                self.warnings.append("ocr_unavailable")
                return ""
            try:
                output = _run([self.executable, "--list-langs"], min(5, remaining), stdout=subprocess.PIPE)
                installed = set(output.stdout.decode("utf-8", errors="replace").splitlines())
                requested = os.getenv("DOCUMENT_INTAKE_OCR_LANGS", "eng+rus+ukr").split("+")
                requested = [lang for lang in requested if re.fullmatch(r"[a-zA-Z0-9_]+", lang)]
                usable = [lang for lang in requested if lang in installed and lang != "osd"]
                if len(usable) != len(requested):
                    self.warnings.append("ocr_languages_missing")
                if not usable:
                    self.warnings.append("ocr_unavailable")
                    return ""
                self.languages = "+".join(usable)
            except (OSError, subprocess.SubprocessError):
                self.warnings.append("ocr_unavailable")
                return ""
        if not self.languages:
            return ""
        try:
            with tempfile.TemporaryDirectory(prefix="intake-ocr-") as folder:
                source, target = Path(folder) / "page.png", Path(folder) / "result"
                image.save(source, format="PNG")
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    self.warnings.append("recognition_time_limit")
                    return ""
                _run(
                    [self.executable, str(source), str(target), "-l", self.languages, "--psm", "3"],
                    min(OCR_TIMEOUT, remaining), stdout=subprocess.DEVNULL,
                )
                with target.with_suffix(".txt").open("rb") as stream:
                    content = stream.read(MAX_TEXT_CHARS * 4 + 1)
                if len(content) > MAX_TEXT_CHARS * 4:
                    self.warnings.append("text_limit")
                self.warnings.append("ocr_used")
                return content.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
        except subprocess.TimeoutExpired:
            self.warnings.append("ocr_timeout")
        except (OSError, subprocess.SubprocessError):
            self.warnings.append("ocr_failed")
        return ""


def _image_text(path: Path, ocr: _OCR) -> tuple[list[str], int]:
    try:
        with python_warnings.catch_warnings():
            python_warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise ValueError("unsupported_image")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError("image_size_limit")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("animated_image_not_supported")
                source.load()
                with ImageOps.exif_transpose(source) as oriented:
                    with image_on_white(oriented) as page:
                        return [ocr.text(page)], 1
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("invalid_image") from exc


def _pdf_text(path: Path, ocr: _OCR) -> tuple[list[str], int]:
    import pypdfium2 as pdfium
    from parser.pdfium_runtime import PDFIUM_LOCK

    document = None
    pages = []
    try:
        with PDFIUM_LOCK:
            document = pdfium.PdfDocument(path)
            count = len(document)
        if not count:
            raise ValueError("empty_pdf")
        if count > MAX_PAGES:
            ocr.warnings.append("page_limit")
        characters = 0
        for index in range(min(count, MAX_PAGES)):
            if time.monotonic() >= ocr.deadline:
                ocr.warnings.append("recognition_time_limit")
                break
            image = None
            with PDFIUM_LOCK:
                page = document[index]
                try:
                    textpage = page.get_textpage()
                    try:
                        length = textpage.count_chars()
                        text = textpage.get_text_range(count=min(length, MAX_TEXT_CHARS)) if length else ""
                        if length > MAX_TEXT_CHARS:
                            ocr.warnings.append("text_limit")
                    finally:
                        textpage.close()
                    # A near-empty text layer is common on otherwise scanned pages.
                    if sum(char.isalnum() for char in text) < 40:
                        width, height = page.get_size()
                        if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                            raise ValueError("invalid_page_size")
                        scale = min(2.5, math.sqrt(MAX_RENDER_PIXELS / (width * height)), 8000 / max(width, height))
                        bitmap = page.render(scale=scale)
                        try:
                            with bitmap.to_pil() as view:
                                image = view.convert("RGB")
                        finally:
                            bitmap.close()
                finally:
                    page.close()
            # PDFium and its buffers are not used during this slow subprocess.
            if image is not None:
                try:
                    scanned = ocr.text(image)
                    text = scanned if len(scanned.strip()) > len(text.strip()) else text
                finally:
                    image.close()
            remaining = MAX_TEXT_CHARS - characters
            pages.append(text[:remaining])
            characters += len(text)
            if characters >= MAX_TEXT_CHARS:
                ocr.warnings.append("text_limit")
                break
        return pages, count
    except (pdfium.PdfiumError, OSError, RuntimeError, OverflowError) as exc:
        raise ValueError("invalid_pdf") from exc
    finally:
        if document is not None:
            with PDFIUM_LOCK:
                document.close()


def _classify(text: str, catalog: list[dict], warnings: list[str]) -> str | None:
    lines = [_normal(line) for line in text.splitlines() if line.strip()]
    hits = []
    for item in catalog:
        for alias in [item.get("label", ""), *(item.get("aliases") or [])]:
            term = _normal(alias)
            if len(term) < 2 or term.isdigit():
                continue
            for index, line in enumerate(lines):
                if f" {term} " not in f" {line} ":
                    continue
                # Short abbreviations are only trusted as explicit titles/types.
                standalone = line == term or line in {"document type " + term, "certificate type " + term}
                if len(term) <= 4 and not standalone:
                    continue
                score = 100 if standalone else 60 if index < 8 else 30
                hits.append((item["key"], term, index, score))
    # A specific title (Civil Passport) suppresses its generic substring
    # (Passport) on that same line, without hiding distinct document titles.
    hits = [h for h in hits if not any(
        h[0] != other[0] and h[2] == other[2] and h[1] != other[1]
        and f" {h[1]} " in f" {other[1]} " for other in hits
    )]
    # A training certificate can use "Certificate of Proficiency" as its
    # heading, with the actual course title immediately underneath.
    course_keys = {item["key"] for item in catalog if item.get("kind") == "certificate"}
    course_titles = [
        hit for hit in hits if hit[0] in course_keys and len(hit[1].split()) >= 2 and hit[2] < 8
        and lines[hit[2]] in {prefix + hit[1] + suffix
                              for prefix in ("", "in ", "on ") for suffix in ("", " training")}
    ]
    hits = [hit for hit in hits if not (
        hit[0] == "diploma:COP" and hit[1] == "certificate of proficiency" and hit[3] == 100
        and any(0 < course[2] - hit[2] <= 3 for course in course_titles)
    )]
    scores = {}
    for key, _, _, score in hits:
        scores[key] = max(scores.get(key, 0), score)
    if not scores:
        return None
    top = max(scores.values())
    winners = [key for key, score in scores.items() if score >= top - 10]
    if len(winners) != 1:
        warnings.append("ambiguous_type")
        return None
    return winners[0]


# Escape non-ASCII labels to keep source portable across Windows shell encodings.
_LABELS = {
    "number": [r"(?:passport|document|certificate|book|seaman'?s? book)\s*(?:number|no\.?)", r"(?:number|no\.?)", r"\u043d\u043e\u043c\u0435\u0440(?:\s+\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430)?", r"\u2116"],
    "issue_date": [r"date\s+(?:of\s+)?issu(?:e|ance)", r"issued\s+(?:on|date)", r"issue\s+date", r"date\s+issued", r"\u0434\u0430\u0442\u0430\s+(?:\u0432\u044b\u0434\u0430\u0447\u0438|\u0432\u0438\u0434\u0430\u0447\u0456)"],
    "expiry_date": [r"date\s+(?:of\s+)?(?:expiry|expiration)", r"(?:expiry|expiration|expiring)\s+date", r"valid\s+(?:until|till|to)", r"expires(?:\s+on)?", r"\u0434\u0430\u0442\u0430\s+\u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f", r"\u0434\u0456\u0439\u0441\u043d\u0438\u0439\s+\u0434\u043e"],
    "country": [r"country\s+of\s+(?:issue|issuance)", r"issuing\s+country", r"country", r"\u0441\u0442\u0440\u0430\u043d\u0430\s+\u0432\u044b\u0434\u0430\u0447\u0438", r"\u043a\u0440\u0430\u0457\u043d\u0430\s+\u0432\u0438\u0434\u0430\u0447\u0456"],
    "authority": [r"issuing\s+authority", r"authority", r"issued\s+by", r"\u043a\u0435\u043c\s+\u0432\u044b\u0434\u0430\u043d", r"\u043e\u0440\u0433\u0430\u043d\s+\u0432\u0438\u0434\u0430\u0447\u0456"],
    "place": [r"place\s+of\s+issue", r"issued\s+at", r"\u043c\u0435\u0441\u0442\u043e\s+\u0432\u044b\u0434\u0430\u0447\u0438", r"\u043c\u0456\u0441\u0446\u0435\s+\u0432\u0438\u0434\u0430\u0447\u0456"],
    "code": [r"certificate\s+code", r"stcw\s+(?:code|regulation)", r"code", r"\u043a\u043e\u0434"],
    "holder_name": [r"holder(?:'?s)?\s+name", r"full\s+name", r"name\s+of\s+(?:holder|seafarer|seaman)", r"name", r"this\s+is\s+to\s+certify\s+that", r"\u0444\u0438\u043e", r"\u043f\u0456\u0431"],
    "_surname": [r"surname", r"last\s+name", r"\u0444\u0430\u043c\u0438\u043b\u0438\u044f", r"\u043f\u0440\u0456\u0437\u0432\u0438\u0449\u0435"],
    "_given": [r"given\s+names?", r"first\s+names?", r"\u0438\u043c\u044f", r"\u0456\u043c['\u2019]?\u044f"],
}
_COMPILED_LABELS = {
    field: re.compile(r"^(?:\d+[.)]\s*)?(?:" + "|".join(patterns) + r")(?=\s|[:#\-]|$)\s*[:#\-]?\s*(.*)$", re.I)
    for field, patterns in _LABELS.items()
}
_MONTHS = {name: index for index, names in enumerate([
    "jan january", "feb february", "mar march", "apr april", "may", "jun june",
    "jul july", "aug august", "sep sept september", "oct october", "nov november", "dec december",
], 1) for name in names.split()}
_DATE_TOKEN = r"(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})(?!\w|[ \t]*[./-][ \t]*\d)"
_INLINE_DATES = {
    "issue_date": re.compile(r"\b(?:date\s+of\s+issu(?:e|ance)|(?:was|is)\s+issued\s+on)\s*[:#]?\s*(" + _DATE_TOKEN + r")", re.I),
    "expiry_date": re.compile(r"\b(?:date\s+of\s+(?:expiry|expiration)|valid\s+until)\s*[:#]?\s*(" + _DATE_TOKEN + r")", re.I),
}
_REFERENCED_DOCUMENT = re.compile(r"\b(?:original|previous|superseded)\s+(?:certificate|document|licen[cs]e)\b", re.I)


def _date_value(value: str) -> tuple[str | None, str | None]:
    value = value.strip().casefold()
    parts = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", value)
    if parts:
        year, month, day = map(int, parts.groups())
    else:
        parts = re.fullmatch(r"(\d{1,2})([-/.])(\d{1,2})\2(\d{4})", value)
        if parts:
            first, separator, second, year = parts.groups()
            first, second, year = int(first), int(second), int(year)
            if separator != "." and first <= 12 and second <= 12 and first != second:
                return None, "ambiguous_date"
            day, month = (first, second) if separator == "." or first > 12 else (second, first)
        else:
            words = re.sub(r"[,./-]", " ", value).split()
            if len(words) != 3:
                return None, "invalid_date"
            if words[1] in _MONTHS and words[0].isdigit() and len(words[2]) == 4 and words[2].isdigit():
                day, month, year = int(words[0]), _MONTHS[words[1]], int(words[2])
            elif words[0] in _MONTHS and words[1].isdigit() and len(words[2]) == 4 and words[2].isdigit():
                day, month, year = int(words[1]), _MONTHS[words[0]], int(words[2])
            else:
                return None, "invalid_date"
    try:
        return date(year, month, day).isoformat(), None
    except ValueError:
        return None, "invalid_date"


def _label(line: str):
    for field, pattern in _COMPILED_LABELS.items():
        match = pattern.match(line)
        if match:
            return field, match.group(1).strip()
    return None


def _fields(text: str, warnings: list[str]) -> dict:
    # Split wide column gutters, but never join unrelated lines into a value.
    lines = []
    for raw in re.split(r"\n|\t+| {3,}", text):
        raw = raw.strip()
        # A colon is required when detecting an embedded label, otherwise
        # "Test Maritime Authority" could be mistaken for two fields.
        boundaries = [0]
        first_value = next((match.start(1) for pattern in _COMPILED_LABELS.values()
                            if (match := pattern.match(raw))), 0)
        for offset in re.finditer(r"\s+", raw):
            if offset.end() <= first_value:
                continue
            tail = raw[offset.end():]
            for pattern in _COMPILED_LABELS.values():
                match = pattern.match(tail)
                if match and ":" in tail[:match.start(1)]:
                    boundaries.append(offset.end())
                    break
        boundaries.append(len(raw))
        lines.extend(raw[start:end].strip() for start, end in zip(boundaries, boundaries[1:]) if raw[start:end].strip())
    values: dict[str, list] = {}
    invalid = set()
    for index, line in enumerate(lines):
        inline = {field: [
            match[1] for match in pattern.finditer(line)
            if not _REFERENCED_DOCUMENT.search(line[max(0, match.start() - 90):match.start()])
        ] for field, pattern in _INLINE_DATES.items()}
        for field, dates in inline.items():
            for value in dates:
                parsed, problem = _date_value(value)
                if problem:
                    warnings.append(f"{problem}:{field}")
                    invalid.add(field)
                else:
                    values.setdefault(field, []).append(parsed)
        labelled = _label(line)
        if not labelled:
            continue
        field, value = labelled
        if inline.get(field):
            continue
        if not value and index + 1 < len(lines) and not _label(lines[index + 1]):
            value = lines[index + 1]
        if not value:
            continue
        if field in {"issue_date", "expiry_date"}:
            if field == "expiry_date" and _normal(value) in {"unlimited", "unlimited validity", "no expiry", "no expiration", "lifetime", "permanent", "does not expire"}:
                values.setdefault("unlimited_validity", []).append(True)
                continue
            parsed, problem = _date_value(value)
            if problem:
                warnings.append(f"{problem}:{field}")
                invalid.add(field)
                continue
            value = parsed
        elif field in {"number", "code"}:
            if not re.fullmatch(r"[\w][\w ./\-]{0,79}", value) or not any(c.isdigit() for c in value) and field == "number":
                warnings.append(f"uncertain_field:{field}")
                invalid.add(field)
                continue
        elif len(value) > 200 or not any(c.isalpha() for c in value):
            warnings.append(f"uncertain_field:{field}")
            invalid.add(field)
            continue
        if field in {"holder_name", "_surname", "_given"} and (any(c.isdigit() for c in value) or len(value.split()) > 8):
            warnings.append("uncertain_field:holder_name")
            invalid.add(field)
            continue
        values.setdefault(field, []).append(value)
    result = {}
    for field, choices in values.items():
        if len(set(choices)) > 1 or field in invalid:
            warnings.append(f"conflicting_field:{field}")
        else:
            result[field] = choices[0]
    surname, given = result.pop("_surname", None), result.pop("_given", None)
    if surname and given:
        combined = f"{given} {surname}"
        full = result.get("holder_name")
        if full and set(_normal(full).split()) != set(_normal(combined).split()):
            result.pop("holder_name", None)
            warnings.append("conflicting_field:holder_name")
        elif "holder_name" not in invalid and "conflicting_field:holder_name" not in warnings:
            result.setdefault("holder_name", combined)
    if result.get("unlimited_validity") and ("expiry_date" in values or "expiry_date" in invalid):
        result.pop("unlimited_validity", None)
        result.pop("expiry_date", None)
        warnings.append("conflicting_field:expiry_date")
    if result.get("issue_date") and result.get("expiry_date") and result["expiry_date"] < result["issue_date"]:
        result.pop("issue_date")
        result.pop("expiry_date")
        warnings.append("date_order_invalid")
    return result


def _mrz_digit(value: str) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return str(sum((0 if char == "<" else alphabet.index(char)) * (7, 3, 1)[index % 3]
                   for index, char in enumerate(value)) % 10)


def _mrz_fields(text: str, warnings: list[str]) -> dict:
    """Only TD3 passports with intact check digits; never repair OCR characters."""
    lines = [re.sub(r"\s", "", line).upper() for line in text.splitlines()]
    results = []
    for first, second in zip(lines, lines[1:]):
        if not (len(first) == len(second) == 44 and first.startswith("P")
                and re.fullmatch(r"[A-Z<]{44}", first)
                and re.fullmatch(r"[A-Z0-9<]{44}", second)):
            continue
        checks = [(second[:9], second[9]), (second[13:19], second[19]),
                  (second[21:27], second[27]), (second[:10] + second[13:20] + second[21:43], second[43])]
        optional = second[28:42]
        if second[42] != "<" or optional.strip("<"):
            checks.append((optional, second[42]))
        if any(_mrz_digit(value) != digit for value, digit in checks):
            warnings.append("mrz_invalid_check_digits")
            continue
        result = {"number": second[:9].rstrip("<"), "country": first[2:5]}
        surname, _, given = first[5:].partition("<<")
        if surname.strip("<") and given.strip("<"):
            result["holder_name"] = " ".join((given.replace("<", " ") + " " + surname.replace("<", " ")).split())
        expiry = second[21:27]
        if expiry.isdigit():
            today = date.today()
            years = [century + int(expiry[:2]) for century in (1900, 2000, 2100)
                     if today.year - 20 <= century + int(expiry[:2]) <= today.year + 20]
            if len(years) == 1:
                try:
                    result["expiry_date"] = date(years[0], int(expiry[2:4]), int(expiry[4:])).isoformat()
                except ValueError:
                    warnings.append("invalid_date:expiry_date")
            else:
                warnings.append("ambiguous_date:expiry_date")
        if result["number"] and result["country"].isalpha():
            results.append(result)
    if not results:
        return {}
    if any(result != results[0] for result in results):
        warnings.append("multiple_passport_mrz")
        return {}
    warnings.append("mrz_used")
    return results[0]


def recognize_document(path: Path, catalog: list[dict], *, deadline: float | None = None) -> dict:
    """Return unapproved suggestions, or ValueError for invalid/unsafe content.

    Missing OCR does not make a valid scan corrupt: return an empty/partial
    suggestion and warnings so a manager can still attach and classify it.
    """
    path = Path(path)
    try:
        size = path.stat().st_size
        if not 0 < size <= MAX_FILE_BYTES:
            raise ValueError("file_size_limit")
        with path.open("rb") as stream:
            signature = stream.read(8)
    except OSError as exc:
        raise ValueError("unreadable_file") from exc
    warnings = []
    document_deadline = time.monotonic() + DOCUMENT_TIMEOUT
    ocr = _OCR(min(document_deadline, deadline) if deadline is not None else document_deadline, warnings)
    if signature.startswith(b"%PDF-"):
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            raise ValueError("content_type_mismatch")
        pages, count = _pdf_text(path, ocr)
    elif signature.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        expected = ".png" if signature.startswith(b"\x89PNG") else ".jpg"
        if path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"} and path.suffix.lower().replace(".jpeg", ".jpg") != expected:
            raise ValueError("content_type_mismatch")
        pages, count = _image_text(path, ocr)
    else:
        raise ValueError("unsupported_content")
    keys = {_classify(text, catalog, warnings) for text in pages}
    keys.discard(None)
    if len(keys) > 1:
        warnings.append("multiple_document_types")
    key = next(iter(keys)) if len(keys) == 1 and "ambiguous_type" not in warnings else None
    text = "\n".join(pages)
    fields = _fields(text, warnings)
    mrz = _mrz_fields(text, warnings)
    if mrz:
        passport_key = _classify("Passport", catalog, warnings)
        if not key and not keys and "ambiguous_type" not in warnings:
            key = passport_key
        if key == passport_key and key is not None:
            for name, value in mrz.items():
                current = fields.get(name)
                if current is not None and _normal(str(current)) != _normal(value):
                    fields.pop(name)
                    warnings.append(f"conflicting_field:{name}")
                elif not any(w.endswith(":" + name) for w in warnings):
                    fields[name] = value
    if not key:
        warnings.append("unknown_type")
    if not text.strip():
        warnings.append("no_readable_text")
    if key:
        allowed = next(item.get("fields") for item in catalog if item["key"] == key)
        if allowed is not None:
            fields = {name: value for name, value in fields.items() if name in allowed or name == "holder_name"}
    return {"type_key": key, "fields": fields, "warnings": list(dict.fromkeys(warnings)), "page_count": count}
