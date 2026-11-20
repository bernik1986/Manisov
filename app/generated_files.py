"""Short-lived, bounded response artifacts; never sweep unrelated generated files."""

from pathlib import Path
import shutil
import tempfile
import threading
import time

from fastapi import HTTPException
from fastapi.responses import FileResponse
import anyio
from starlette.concurrency import run_in_threadpool

TTL_SECONDS = 3600
MAX_STORAGE_BYTES = 512 * 1024 * 1024
MAX_RESPONSE_BYTES = 100 * 1024 * 1024
_SLOTS = threading.BoundedSemaphore(4)
_LOCK = threading.Lock()
_ACTIVE: set[Path] = set()
PREFIX = "response-artifact-"


class _TemporaryFileResponse(FileResponse):
    def __init__(self, path, *, cleanup, **kwargs):
        super().__init__(path, **kwargs)
        self._cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # BackgroundTask alone is skipped when a client disconnects mid-send.
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self._cleanup)


def _storage_usage(root):
    used = 0
    for folder in root.glob(PREFIX + "*"):
        if folder.is_symlink() or not folder.is_dir():
            continue
        for file in folder.rglob("*"):
            try:
                if file.is_file() and not file.is_symlink():
                    used += file.stat().st_size
            except FileNotFoundError:
                pass
    return used


def cleanup_expired(root: Path, *, now: float | None = None) -> None:
    root = root.resolve()
    if not root.is_dir():
        return
    now = time.time() if now is None else now
    with _LOCK:
        active = set(_ACTIVE)
    for folder in root.glob(PREFIX + "*"):
        if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent != root or folder.resolve() in active:
            continue
        try:
            if now - folder.stat().st_mtime > TTL_SECONDS:
                shutil.rmtree(folder)
        except FileNotFoundError:
            pass


class GeneratedWorkspace:
    def __init__(self, root: Path):
        self.path = None
        self._closed = False
        if not _SLOTS.acquire(blocking=False):
            raise HTTPException(429, "Document generation is busy; please retry shortly")
        try:
            root = root.resolve()
            root.mkdir(parents=True, exist_ok=True)
            cleanup_expired(root)
            with _LOCK:
                reserved = sum(MAX_RESPONSE_BYTES for folder in _ACTIVE if folder.parent == root)
                if _storage_usage(root) + reserved + MAX_RESPONSE_BYTES > MAX_STORAGE_BYTES:
                    raise HTTPException(507, "Temporary document storage is full")
                self.path = Path(tempfile.mkdtemp(prefix=PREFIX, dir=root)).resolve()
                _ACTIVE.add(self.path)
        except BaseException:
            _SLOTS.release()
            raise

    def cleanup(self):
        with _LOCK:
            if self._closed:
                return
            self._closed = True
            if self.path:
                _ACTIVE.discard(self.path)
        try:
            if self.path and self.path.is_dir():
                shutil.rmtree(self.path)
        finally:
            _SLOTS.release()

    def response(self, path: Path, **kwargs) -> FileResponse:
        if not path.resolve().is_relative_to(self.path) or path.stat().st_size > MAX_RESPONSE_BYTES:
            raise HTTPException(413, "Generated document is too large")
        return _TemporaryFileResponse(path, cleanup=self.cleanup, **kwargs)
