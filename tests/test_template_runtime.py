from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore
from time import monotonic

from docx import Document
import pytest

from app import template_runtime as runtime
from app.template_security import TemplateValidationError


def source_fixture(tmp_path):
    path = tmp_path / "source.docx"
    doc = Document()
    doc.add_paragraph("{{ name }}")
    doc.save(path)
    return path


def test_runtime_environment_is_allowlisted(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPLATE_TEST_UNRELATED_SETTING", "benign")
    monkeypatch.setenv("PYTHONPATH", "not-used")
    env = runtime.rendering_environment(tmp_path)
    assert "TEMPLATE_TEST_UNRELATED_SETTING" not in env
    assert "PYTHONPATH" not in env and "DATABASE_URL" not in env
    assert env["TMP"] == str(tmp_path)
    assert env["OPENBLAS_NUM_THREADS"] == "1"


def test_hung_worker_is_killed_reaped_and_private_files_removed(tmp_path, monkeypatch):
    original = subprocess.Popen
    children, folders = [], []

    def hung(args, **kwargs):
        assert args[1:3] == ["-I", "-B"]
        folders.append(Path(kwargs["cwd"]))
        child = original([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        return child

    source = source_fixture(tmp_path)
    monkeypatch.setattr(runtime.subprocess, "Popen", hung)
    started = monotonic()
    with pytest.raises(TimeoutError, match="template_render_timeout"):
        runtime.render_template_bounded(source, {}, tmp_path / "output.docx", timeout=0.5)
    assert children and all(child.poll() is not None for child in children)
    assert monotonic() - started < 8
    assert all(not folder.exists() for folder in folders)
    assert not (tmp_path / "output.docx").exists()


def test_crash_does_not_prevent_next_render(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    output = tmp_path / "output.docx"
    original = subprocess.Popen

    def crashed(args, **kwargs):
        return original([sys.executable, "-c", "raise SystemExit(7)"], **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(runtime.subprocess, "Popen", crashed)
        with pytest.raises(RuntimeError, match="template_render_failed"):
            runtime.render_template_bounded(source, {"name": "Ada"}, output)
    runtime.render_template_bounded(source, {"name": "Ada"}, output)
    assert Document(output).paragraphs[0].text == "Ada"


def test_small_benign_output_over_lowered_limit_is_not_published(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    output = tmp_path / "output.docx"
    original = subprocess.Popen

    def oversized(args, **kwargs):
        code = "from pathlib import Path; Path('output.docx').write_bytes(b'x' * 65536)"
        return original([sys.executable, "-c", code], **kwargs)

    monkeypatch.setattr(runtime, "MAX_OUTPUT_BYTES", 50000)
    monkeypatch.setattr(runtime.subprocess, "Popen", oversized)
    with pytest.raises(TemplateValidationError, match="output_limit"):
        runtime.render_template_bounded(source, {"name": "Ada"}, output)
    assert not output.exists()


@pytest.mark.parametrize("response", ["x" * 1025, "not-json", '{"ok":true}'])
def test_bad_worker_status_or_missing_output_is_not_published(tmp_path, monkeypatch, response):
    source = source_fixture(tmp_path)
    original = subprocess.Popen

    def bad_status(args, **kwargs):
        code = "from pathlib import Path; import sys; Path('result.json').write_text(sys.argv[1])"
        return original([sys.executable, "-c", code, response], **kwargs)

    monkeypatch.setattr(runtime.subprocess, "Popen", bad_status)
    with pytest.raises(RuntimeError, match="template_render_failed"):
        runtime.render_template_bounded(source, {}, tmp_path / "output.docx")
    assert not (tmp_path / "output.docx").exists()


def test_worker_slot_wait_counts_against_deadline(tmp_path, monkeypatch):
    slots = BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(runtime, "_RENDER_SLOTS", slots)
    with pytest.raises(TimeoutError, match="template_render_timeout"):
        runtime.render_template_bounded(source_fixture(tmp_path), {}, tmp_path / "output.docx", timeout=0.01)
    slots.release()


def test_worker_has_no_app_or_database_imports(tmp_path):
    root = Path(runtime.__file__).resolve().parents[1]
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from app.template_runtime import _apply_resource_limits; _apply_resource_limits(); "
        "import app.template_renderer; "
        "assert 'app.main' not in sys.modules and 'models.db' not in sys.modules; print('ok')"
    )
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(root)], cwd=tmp_path,
                            env=runtime.rendering_environment(tmp_path), capture_output=True,
                            timeout=runtime.PROCESS_TIMEOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"ok"
