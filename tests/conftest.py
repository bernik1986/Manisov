"""Shared pytest configuration."""

from __future__ import annotations

import os
from pathlib import Path

# Isolate pytest from a developer Postgres DATABASE_URL (avoids aborted-transaction cascades).
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(Path(__file__).resolve().parents[1] / '.pytest_parcer.db').as_posix()}")
os.environ.setdefault("AUTO_ALEMBIC_ON_STARTUP", "0")
os.environ.setdefault("RESET_DB_ON_STARTUP", "0")

import pytest

import app.main as main_module


@pytest.fixture(autouse=True)
def _reset_login_throttle_between_tests() -> None:
    main_module.login_throttle_reset_for_testing()
    yield
    main_module.login_throttle_reset_for_testing()
