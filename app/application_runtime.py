"""Bound questionnaire parsing outside the API process, without service credentials."""

from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading

from app.document_intake_runtime import recognition_environment, _terminate

TIMEOUT_SECONDS = 90
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 100
_SLOTS = threading.BoundedSemaphore(2)


class ApplicationParserBusy(RuntimeError):
    pass


def parse_application_bounded(path: Path, *, mode: str = "application", timeout: float | None = None) -> dict:
    if (path.suffix.lower() not in {".doc", ".docx", ".xls", ".xlsx", ".pdf"}
            or mode not in {"application", "cv"} or (mode == "cv" and path.suffix.lower() != ".pdf")):
        raise ValueError("Unsupported questionnaire format")
    if not _SLOTS.acquire(blocking=False):
        raise ApplicationParserBusy("Questionnaire parser is busy; please retry shortly")
    try:
        with TemporaryDirectory(prefix="manisov-application-") as folder:
            request, output = Path(folder) / "request.json", Path(folder) / "result.json"
            request.write_text(json.dumps({"path": str(path.resolve()), "mode": mode}), encoding="utf-8")
            environment = recognition_environment()
            environment["DATABASE_URL"] = "sqlite:///:memory:"
            # The parent owns cleanup even when a worker is killed before its
            # nested TemporaryDirectory context can run its own finalizer.
            environment.update({key: folder for key in ("TEMP", "TMP", "TMPDIR")})
            process = subprocess.Popen(
                [sys.executable, "-m", "app.application_runtime", str(request), str(output)],
                cwd=Path(__file__).resolve().parents[1], env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt",
            )
            try:
                try:
                    code = process.wait(timeout=min(TIMEOUT_SECONDS, timeout if timeout is not None else TIMEOUT_SECONDS))
                except subprocess.TimeoutExpired as exc:
                    raise TimeoutError("Questionnaire parsing timed out; the original file was not imported") from exc
                if code != 0 or not output.is_file():
                    raise RuntimeError("Questionnaire parser failed or exceeded its processing limits")
                with output.open("rb") as stream:
                    raw = stream.read(MAX_RESULT_BYTES + 1)
                if len(raw) > MAX_RESULT_BYTES:
                    raise ValueError("Questionnaire result is too large")
                response = json.loads(raw)
                if "error" in response:
                    raise ValueError(response["error"])
                if not isinstance(response.get("result"), dict):
                    raise RuntimeError("Invalid questionnaire parser result")
                return response["result"]
            finally:
                if process.poll() is None:
                    _terminate(process)
    finally:
        _SLOTS.release()


def _resource_limits():
    if os.name == "nt":
        return
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _parse(path: Path, mode: str):
    suffix = path.suffix.lower()
    if suffix in {".docx", ".xlsx"}:
        from app.template_security import validate_ooxml_archive
        validate_ooxml_archive(path)
    if suffix == ".pdf":
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(path) as pdf:
            if not 0 < len(pdf) <= MAX_PDF_PAGES:
                raise ValueError("Questionnaire PDF page limit exceeded")
    if mode == "cv":
        import nltk
        for resource_name in ("corpora/stopwords", "tokenizers/punkt"):
            try:
                nltk.data.find(resource_name)
            except LookupError as exc:
                raise ValueError("CV language resources must be installed by the administrator") from exc
        from pyresparser import ResumeParser
        return ResumeParser(str(path)).get_extracted_data() or {}
    if suffix in {".doc", ".docx"}:
        from parser.docx_parser import DocxParser
        parser = DocxParser()
    elif suffix in {".xls", ".xlsx"}:
        from parser.excel_parser import ExcelParser
        from parser.man09_excel_parser import Man09ExcelParser, looks_like_man09_excel
        parser = Man09ExcelParser() if looks_like_man09_excel(path) else ExcelParser()
    else:
        import pdfplumber
        from parser.crewwell_pdf_parser import CrewwellPDFParser
        from parser.pdf_parser import PDFParser
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:2]).lower()
        is_crewwell = "main info" in text and "passports / smbk" in text and ("crewell id" in text or "position applied for" in text)
        parser = CrewwellPDFParser() if is_crewwell else PDFParser()
    return parser.parse(path)


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("Unsupported parser result value")


def _main():
    _resource_limits()
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        response = {"result": _parse(Path(request["path"]), request["mode"])}
        encoded = json.dumps(response, default=_json_value, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError("Questionnaire result is too large")
    except ValueError as exc:
        encoded = json.dumps({"error": str(exc)[:300]})
    except Exception:
        encoded = json.dumps({"error": "Invalid or unsupported questionnaire; no candidate was saved"})
    Path(sys.argv[2]).write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    _main()
