import asyncio
from io import BytesIO
from pathlib import Path
import threading
import time

from docx import Document
from fastapi import UploadFile
import pytest

from app import application_runtime, main


def test_parser_worker_environment_has_no_service_credentials(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "synthetic-never-leave-parent")
    monkeypatch.setenv("DATABASE_URL", "synthetic-never-leave-parent")
    monkeypatch.setenv("VPS_SSH_KEY", "synthetic-never-leave-parent")
    env = application_runtime.recognition_environment()
    assert all(key not in env for key in ("JWT_SECRET_KEY", "DATABASE_URL", "VPS_SSH_KEY"))


def test_real_questionnaire_worker_parses_docx(tmp_path):
    path = tmp_path / "synthetic.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Surname"
    table.cell(0, 1).text = "SYNTHETIC"
    table.cell(1, 0).text = "First Name"
    table.cell(1, 1).text = "AUDIT"
    doc.save(path)
    result = application_runtime.parse_application_bounded(path)
    assert isinstance(result["personal_data"], dict)
    assert "sea_service" in result


def test_worker_deadline_terminates_and_releases_slot(tmp_path):
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"%PDF invalid synthetic input")
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        application_runtime.parse_application_bounded(path, timeout=0.0001)
    assert time.monotonic() - started < 10
    assert application_runtime._SLOTS.acquire(blocking=False)
    application_runtime._SLOTS.release()


def test_worker_rejects_unsupported_format_and_busy_queue(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        application_runtime.parse_application_bounded(tmp_path / "file.exe")
    semaphore = threading.BoundedSemaphore(1)
    semaphore.acquire()
    monkeypatch.setattr(application_runtime, "_SLOTS", semaphore)
    with pytest.raises(application_runtime.ApplicationParserBusy):
        application_runtime.parse_application_bounded(tmp_path / "file.pdf")


def test_upload_does_not_block_event_loop(monkeypatch):
    def parse(path):
        time.sleep(0.25)
        return {"personal_data": {}}

    monkeypatch.setattr(main, "parse_application_bounded", parse)
    monkeypatch.setattr(main, "_save_parsed_data", lambda *args: 1)
    monkeypatch.setattr(main, "_write_audit_log", lambda *args, **kwargs: None)

    async def run():
        upload = asyncio.create_task(main.upload(
            file=UploadFile(filename="synthetic.pdf", file=BytesIO(b"dummy")),
            confirm_duplicate_update=False, db_session=None, _current_user=None,
        ))
        await asyncio.sleep(0.03)
        assert not upload.done()
        assert (await upload)["candidate_id"] == 1

    asyncio.run(run())
