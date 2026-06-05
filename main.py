"""Compatibility entrypoint for `uvicorn main:app`.

The full CRM API (candidates, flag documents, auth, …) lives in ``app.main``.
Previously this file defined a smaller FastAPI app; that led to 404 on newer
routes when the server was started as ``uvicorn main:app`` instead of
``uvicorn app.main:app``.

Prefer explicitly: ``uvicorn app.main:app --host 127.0.0.1 --port 8000``.
"""

from app.main import app

__all__ = ["app"]
