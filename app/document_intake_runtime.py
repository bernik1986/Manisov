"""Killable, offline recognition process; no database or web-app imports."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


PROCESS_TIMEOUT = 130.0
MAX_RESULT_BYTES = 1024 * 1024


def recognition_environment():
    """Pass local OCR configuration, never service credentials or DB settings."""
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "TMPDIR",
        "HOME", "USERPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)",
        "LANG", "LC_ALL", "LC_CTYPE", "TESSDATA_PREFIX",
        "DOCUMENT_INTAKE_TESSERACT", "DOCUMENT_INTAKE_OCR_LANGS",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update({
        "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1",
    })
    return environment


def _terminate(process):
    # Tesseract is a child of the recognizer. Stop the tree before removing
    # temporary input/output files, not just the Python process.
    if os.name == "nt":
        try:
            subprocess.run(
                [str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe"),
                 "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                env=recognition_environment(),
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def recognize_document_bounded(path, catalog, *, stop_event=None, timeout=None):
    """Bound native PDF calls as well as OCR; never leave a timed-out thread."""
    timeout = PROCESS_TIMEOUT if timeout is None else min(timeout, PROCESS_TIMEOUT)
    if timeout <= 0:
        raise TimeoutError("recognition_timeout")
    if stop_event is not None and stop_event.is_set():
        raise InterruptedError("recognition_stopped")
    deadline = time.monotonic() + timeout
    with TemporaryDirectory(prefix="parcer-recognition-") as folder:
        request = Path(folder) / "request.json"
        result = Path(folder) / "result.json"
        request.write_text(json.dumps({"path": str(Path(path).resolve()), "catalog": catalog}), encoding="utf-8")
        environment = recognition_environment()
        environment.update({key: folder for key in ("TEMP", "TMP", "TMPDIR")})
        process = subprocess.Popen(
            [sys.executable, "-m", "app.document_intake_runtime", str(request), str(result)],
            cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            start_new_session=os.name != "nt",
        )
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    raise InterruptedError("recognition_stopped")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("recognition_timeout")
                try:
                    code = process.wait(timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if code != 0 or not result.is_file():
                raise RuntimeError("recognition_failed")
            with result.open("rb") as stream:
                content = stream.read(MAX_RESULT_BYTES + 1)
            if len(content) > MAX_RESULT_BYTES:
                raise RuntimeError("recognition_result_limit")
            response = json.loads(content)
            if response.get("error") == "invalid_scan":
                raise ValueError("invalid_scan")
            if "result" not in response:
                raise RuntimeError("recognition_failed")
            return response["result"]
        finally:
            if process.poll() is None:
                _terminate(process)


def _main():
    from app.document_intake_recognition import recognize_document

    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        response = {"result": recognize_document(Path(request["path"]), request["catalog"])}
    except ValueError:
        response = {"error": "invalid_scan"}
    Path(sys.argv[2]).write_text(json.dumps(response), encoding="utf-8")


if __name__ == "__main__":
    _main()
