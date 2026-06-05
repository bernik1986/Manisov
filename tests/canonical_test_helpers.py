"""Helpers for API tests after canonical document/certificate/diploma slots."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

CERTIFICATE_LIST_KEYS: tuple[str, ...] = (
    "certificates",
    "conventional_certificates",
    "ecdis_certificates",
    "company_certificates",
    "bwts_certificates",
    "diplomas",
    "tanker_diplomas",
)


def iter_certificate_rows(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for key in CERTIFICATE_LIST_KEYS:
        for row in payload.get(key) or []:
            yield key, row


def count_certificate_rows(payload: dict[str, Any]) -> int:
    return sum(len(payload.get(key) or []) for key in CERTIFICATE_LIST_KEYS)


def find_certificate(
    payload: dict[str, Any],
    predicate: Callable[[dict[str, Any]], bool],
) -> tuple[str | None, dict[str, Any] | None]:
    for key, row in iter_certificate_rows(payload):
        if predicate(row):
            return key, row
    return None, None


def find_document(
    documents: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, Any] | None:
    for row in documents:
        if predicate(row):
            return row
    return None
