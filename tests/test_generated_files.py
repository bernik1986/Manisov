import os
import asyncio
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from app import generated_files


def test_response_artifact_removed_after_download(tmp_path):
    app = FastAPI()

    @app.get("/download")
    def download():
        workspace = generated_files.GeneratedWorkspace(tmp_path)
        path = workspace.path / "synthetic.txt"
        path.write_bytes(b"synthetic result")
        return workspace.response(path, filename=path.name)

    with TestClient(app) as client:
        response = client.get("/download")
        assert response.content == b"synthetic result"
        assert list(tmp_path.iterdir()) == []


def test_cleanup_is_scoped_and_preserves_active_requests(tmp_path):
    retained = tmp_path / "unrelated.txt"
    retained.write_text("keep")
    old = tmp_path / (generated_files.PREFIX + "abandoned")
    old.mkdir()
    (old / "result.txt").write_text("temporary")
    now = time.time()
    os.utime(old, (now - 7200, now - 7200))
    workspace = generated_files.GeneratedWorkspace(tmp_path)
    try:
        os.utime(workspace.path, (now - 7200, now - 7200))
        generated_files.cleanup_expired(tmp_path, now=now)
        assert not old.exists()
        assert workspace.path.exists()
        assert retained.read_text() == "keep"
    finally:
        workspace.cleanup()
        workspace.cleanup()


def test_generation_concurrency_is_bounded(tmp_path):
    workspaces = []
    try:
        for _ in range(4):
            workspaces.append(generated_files.GeneratedWorkspace(tmp_path))
        with pytest.raises(HTTPException) as error:
            generated_files.GeneratedWorkspace(tmp_path)
        assert error.value.status_code == 429
    finally:
        for workspace in workspaces:
            workspace.cleanup()


def test_response_size_and_path_are_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(generated_files, "MAX_RESPONSE_BYTES", 5)
    workspace = generated_files.GeneratedWorkspace(tmp_path)
    try:
        large = workspace.path / "result.txt"
        large.write_bytes(b"123456")
        with pytest.raises(HTTPException) as error:
            workspace.response(large)
        assert error.value.status_code == 413
        outside = tmp_path / "unrelated.txt"
        outside.write_bytes(b"x")
        with pytest.raises(HTTPException):
            workspace.response(outside)
    finally:
        workspace.cleanup()
    assert outside.exists()


def test_disconnected_download_releases_artifact_and_slot(tmp_path):
    workspace = generated_files.GeneratedWorkspace(tmp_path)
    path = workspace.path / "result.txt"
    path.write_bytes(b"synthetic result")
    response = workspace.response(path)

    async def disconnected(message):
        raise OSError("synthetic disconnect")

    async def receive():
        return {"type": "http.disconnect"}

    with pytest.raises(OSError):
        asyncio.run(response({"type": "http", "method": "GET", "headers": []}, receive, disconnected))
    assert not workspace.path.exists()
    assert workspace.path not in generated_files._ACTIVE
