"""Disposable template worker: bounded IPC, wall time, CPU, memory and output.

No application/database imports. POSIX rlimits and Windows Job Objects are
mandatory (fail closed on setup errors). This is process/resource isolation,
not a filesystem/network OS sandbox; only the restricted language is exposed.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from threading import BoundedSemaphore
import time


PROCESS_TIMEOUT = 30.0
CPU_SECONDS = 20
MEMORY_BYTES = 768 * 1024 * 1024
MAX_OUTPUT_BYTES = 20 * 1024 * 1024
MAX_WORK_BYTES = 128 * 1024 * 1024
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_STATUS_BYTES = 1024
_RENDER_SLOTS = BoundedSemaphore(2)


@contextmanager
def _render_slot(deadline):
    if not _RENDER_SLOTS.acquire(timeout=max(0, deadline - time.monotonic())):
        raise TimeoutError("template_render_timeout")
    try:
        yield
    finally:
        _RENDER_SLOTS.release()


def rendering_environment(folder: Path) -> dict[str, str]:
    allowed = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "LANG", "LC_ALL", "LC_CTYPE"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update({
        "TEMP": str(folder), "TMP": str(folder), "TMPDIR": str(folder),
        "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1",
    })
    return environment


def _copy_bounded(source: Path, target: Path, limit: int) -> None:
    from app.template_security import TemplateValidationError

    with source.open("rb") as src, target.open("wb") as dst:
        total = 0
        while chunk := src.read(65536):
            total += len(chunk)
            if total > limit:
                raise TemplateValidationError("template_file_size_limit")
            dst.write(chunk)


def _terminate(process) -> None:
    if os.name == "nt":
        # The worker Job Object forbids descendants. Also handles launch failures
        # before the worker attaches itself to the job.
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def _check_work_files(folder: Path) -> None:
    from app.template_security import TemplateValidationError

    total = 0
    for item in folder.iterdir():
        try:
            if not item.is_file():
                continue
            size = item.stat().st_size
        except FileNotFoundError:
            # DOCX postprocessing atomically renames temporary ZIPs.
            continue
        total += size
        if size > MAX_OUTPUT_BYTES or total > MAX_WORK_BYTES:
            raise TemplateValidationError("template_output_limit")


def render_template_bounded(template_path: Path, context: dict, output_path: Path, *, timeout=None) -> None:
    from app.template_security import MAX_ARCHIVE_BYTES, MAX_CONTEXT_BYTES, TemplateValidationError, plain_template_context

    timeout = PROCESS_TIMEOUT if timeout is None else min(timeout, PROCESS_TIMEOUT)
    if timeout <= 0:
        raise TimeoutError("template_render_timeout")
    deadline = time.monotonic() + timeout
    template_path, output_path = Path(template_path), Path(output_path)
    if template_path.suffix.lower() not in {".docx", ".xlsx", ".xlsm"}:
        raise TemplateValidationError("template_type_unsupported")
    render_context = plain_template_context(context)
    photo = context.get("candidate_photo_path", "")
    if type(photo) is not str and photo is not None:
        raise TemplateValidationError("template_photo_not_plain")
    with _render_slot(deadline), TemporaryDirectory(prefix="parcer-template-") as folder_name:
        folder = Path(folder_name)
        template = folder / ("template" + template_path.suffix.lower())
        output = folder / ("output" + template.suffix)
        request, result = folder / "request.json", folder / "result.json"
        _copy_bounded(template_path, template, MAX_ARCHIVE_BYTES)
        photo_name = None
        if photo and Path(photo).is_file():
            photo_name = "photo.bin"
            _copy_bounded(Path(photo), folder / photo_name, MAX_PHOTO_BYTES)
        payload = json.dumps({"template": template.name, "output": output.name,
                              "context": render_context, "photo": photo_name}, ensure_ascii=False).encode("utf-8")
        if len(payload) > MAX_CONTEXT_BYTES:
            raise TemplateValidationError("template_context_limit")
        request.write_bytes(payload)
        if time.monotonic() >= deadline:
            raise TimeoutError("template_render_timeout")
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).resolve()), str(request), str(result)],
            cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=rendering_environment(folder), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            start_new_session=os.name != "nt",
        )
        try:
            while True:
                _check_work_files(folder)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("template_render_timeout")
                try:
                    code = process.wait(timeout=min(0.05, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            _check_work_files(folder)
            if code != 0 or not result.is_file():
                raise RuntimeError("template_render_failed")
            with result.open("rb") as stream:
                status = stream.read(MAX_STATUS_BYTES + 1)
            if len(status) > MAX_STATUS_BYTES:
                raise RuntimeError("template_render_failed")
            try:
                response = json.loads(status)
            except (ValueError, UnicodeError) as exc:
                raise RuntimeError("template_render_failed") from exc
            if response == {"error": "template_rejected"}:
                raise TemplateValidationError("template_rejected")
            if response != {"ok": True} or not output.is_file():
                raise RuntimeError("template_render_failed")
            if output.stat().st_size > MAX_OUTPUT_BYTES:
                raise TemplateValidationError("template_output_limit")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            staged = None
            try:
                with NamedTemporaryFile(prefix=".template-", dir=output_path.parent, delete=False) as stream:
                    staged = Path(stream.name)
                _copy_bounded(output, staged, MAX_OUTPUT_BYTES)
                if time.monotonic() >= deadline:
                    raise TimeoutError("template_render_timeout")
                os.replace(staged, output_path)
            finally:
                if staged is not None:
                    staged.unlink(missing_ok=True)
        finally:
            if process.poll() is None:
                _terminate(process)


def _apply_resource_limits() -> None:
    if os.name != "nt":
        import resource

        for name, ceiling in (("RLIMIT_CPU", CPU_SECONDS), ("RLIMIT_AS", MEMORY_BYTES),
                              ("RLIMIT_FSIZE", MAX_OUTPUT_BYTES), ("RLIMIT_CORE", 0)):
            kind = getattr(resource, name)
            _, hard = resource.getrlimit(kind)
            limit = ceiling if hard == resource.RLIM_INFINITY else min(ceiling, hard)
            resource.setrlimit(kind, (limit, limit))
        return

    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x2 | 0x8 | 0x100 | 0x2000
    limits.BasicLimitInformation.PerProcessUserTimeLimit = CPU_SECONDS * 10_000_000
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.ProcessMemoryLimit = MEMORY_BYTES
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(job)
        raise error
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(job)
        raise error
    # Keep the kill-on-close job alive for the entire worker lifetime.
    global _JOB_HANDLE
    _JOB_HANDLE = job


def _main() -> None:
    result = Path(sys.argv[2])
    try:
        _apply_resource_limits()
        from app.template_security import MAX_CONTEXT_BYTES, TemplateValidationError, validate_ooxml_archive
        from jinja2 import TemplateError

        request_path = Path(sys.argv[1])
        with request_path.open("rb") as stream:
            content = stream.read(MAX_CONTEXT_BYTES + 1)
        if len(content) > MAX_CONTEXT_BYTES:
            raise TemplateValidationError("template_context_limit")
        request = json.loads(content)
        template, output = Path(request["template"]), Path(request["output"])
        try:
            validate_ooxml_archive(template)
            from app.template_renderer import _render_docx_template, _render_excel_template

            photo = Path(request["photo"]) if request["photo"] else None
            if photo:
                from PIL import Image

                with Image.open(photo) as image:
                    if image.width * image.height > 12_000_000:
                        raise TemplateValidationError("template_photo_limit")
                    image.verify()
            render = _render_docx_template if template.suffix == ".docx" else _render_excel_template
            render(template, request["context"], output, photo)
            validate_ooxml_archive(output)
            response = {"ok": True}
        except (ValueError, TemplateError):
            response = {"error": "template_rejected"}
    except Exception:
        response = {"error": "template_render_failed"}
    result.write_text(json.dumps(response), encoding="utf-8")


if __name__ == "__main__":
    # -I ignores PYTHONPATH and cwd; only this known code root is added.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _main()
