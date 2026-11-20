from pathlib import Path
import subprocess
import sys
from threading import Event, Timer
from time import monotonic

import pytest

from app import document_intake_runtime as runtime
from tests.test_document_intake_recognition import CATALOG, TEXT, text_pdf


def test_real_isolated_recognition_and_invalid_input(tmp_path):
    path = text_pdf(tmp_path / "valid.pdf", [TEXT])
    result = runtime.recognize_document_bounded(path, CATALOG, timeout=15)
    assert result["fields"]["number"] == "SB123456"
    assert result["type_key"] == "document:SB"
    path.write_bytes(b"%PDF-broken")
    with pytest.raises(ValueError, match="invalid_scan"):
        runtime.recognize_document_bounded(path, CATALOG, timeout=15)


@pytest.mark.parametrize("cancel", [False, True])
def test_hung_native_process_is_killed_and_reaped(tmp_path, monkeypatch, cancel):
    original = subprocess.Popen
    children = []

    def hung(args, **kwargs):
        # Keep taskkill itself real, but replace the recognizer with a hung process.
        if args[0] == sys.executable:
            args = [sys.executable, "-c", "import time; time.sleep(60)"]
        process = original(args, **kwargs)
        if args[0] == sys.executable:
            children.append(process)
        return process

    monkeypatch.setattr(runtime.subprocess, "Popen", hung)
    stopped = Event()
    timer = Timer(0.5, stopped.set)
    if cancel:
        timer.start()
    started = monotonic()
    try:
        with pytest.raises(InterruptedError if cancel else TimeoutError):
            runtime.recognize_document_bounded(
                tmp_path / "unused.pdf", [], timeout=10 if cancel else 0.5, stop_event=stopped,
            )
        assert len(children) == 1 and children[0].poll() is not None
        assert monotonic() - started < 12
    finally:
        timer.cancel()
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_crashed_worker_does_not_prevent_next_job(tmp_path, monkeypatch):
    original = subprocess.Popen

    def crashed(args, **kwargs):
        return original([sys.executable, "-c", "raise SystemExit(7)"], **kwargs)

    path = text_pdf(tmp_path / "valid.pdf", [TEXT])
    with monkeypatch.context() as patch:
        patch.setattr(runtime.subprocess, "Popen", crashed)
        with pytest.raises(RuntimeError, match="recognition_failed"):
            runtime.recognize_document_bounded(path, CATALOG, timeout=15)
    assert runtime.recognize_document_bounded(path, CATALOG, timeout=15)["page_count"] == 1


def test_environment_allows_only_local_ocr_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://not-for-ocr")
    monkeypatch.setenv("SECRET_KEY", "not-for-ocr")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "not-for-ocr")
    monkeypatch.setenv("PYTHONPATH", "not-for-ocr")
    monkeypatch.setenv("DOCUMENT_INTAKE_OCR_LANGS", "eng")
    monkeypatch.setenv("DOCUMENT_INTAKE_OCR_TIMEOUT", "99999")
    monkeypatch.setenv("OMP_THREAD_LIMIT", "99999")
    monkeypatch.setenv("OMP_NUM_THREADS", "99999")
    environment = runtime.recognition_environment()
    assert not {"DATABASE_URL", "SECRET_KEY", "AWS_SECRET_ACCESS_KEY", "PYTHONPATH",
                "DOCUMENT_INTAKE_OCR_TIMEOUT"}.intersection(environment)
    assert environment["DOCUMENT_INTAKE_OCR_LANGS"] == "eng"
    assert environment["OMP_THREAD_LIMIT"] == environment["OMP_NUM_THREADS"] == "1"
    original = subprocess.Popen
    seen = []

    def launch(args, **kwargs):
        owned_temp = str(Path(args[-2]).parent)
        assert kwargs["env"] == {**environment, **{key: owned_temp for key in ("TEMP", "TMP", "TMPDIR")}}
        seen.append(True)
        return original(args, **kwargs)

    monkeypatch.setattr(runtime.subprocess, "Popen", launch)
    path = text_pdf(tmp_path / "valid.pdf", [TEXT])
    assert runtime.recognize_document_bounded(path, CATALOG, timeout=15)["page_count"] == 1
    assert seen == [True]


def test_tesseract_does_not_inherit_service_environment(monkeypatch):
    from app import document_intake_recognition as recognition

    monkeypatch.setenv("DATABASE_URL", "postgresql://not-for-tesseract")
    monkeypatch.setenv("OMP_THREAD_LIMIT", "999")
    calls = []

    def run(args, **kwargs):
        calls.append(kwargs)
        assert "DATABASE_URL" not in kwargs["env"]
        assert kwargs["env"]["OMP_THREAD_LIMIT"] == "1"

    monkeypatch.setattr(recognition.subprocess, "run", run)
    recognition._run(["tesseract", "--list-langs"], 2)
    assert len(calls) == 1


def test_preview_and_photo_merge_isolated_from_web_process(tmp_path, monkeypatch):
    from io import BytesIO
    from pathlib import Path
    from PIL import Image
    from app import document_intake_pdf as pdf

    original = subprocess.run
    outputs = []

    def run(args, **kwargs):
        assert args[:3] == [sys.executable, "-m", "app.document_intake_pdf"]
        assert kwargs["timeout"] and "DATABASE_URL" not in kwargs["env"]
        outputs.append(Path(args[4]))
        return original(args, **kwargs)

    monkeypatch.setattr(pdf.subprocess, "run", run)
    with BytesIO() as stream, Image.new("RGB", (20, 30), "red") as image:
        image.save(stream, format="PNG")
        content = pdf.merge_photo_pages([stream.getvalue()], 100_000)
    assert content.startswith(b"%PDF")
    assert pdf.render_preview_page(content, 1).startswith(b"\x89PNG")
    with pytest.raises(ValueError):
        pdf.render_preview_page(content, 2)
    assert len(outputs) == 3 and not any(path.parent.exists() for path in outputs)
