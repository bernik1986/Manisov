"""Uppercase candidate name fields.

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NAME_FIELDS = (
    "surname",
    "first_name",
    "middle_name",
    "full_name",
    "latin_full_name",
    "native_full_name",
)


def upgrade() -> None:
    for field in _NAME_FIELDS:
        op.execute(
            sa.text(
                f"UPDATE candidates SET {field} = UPPER(TRIM({field})) "
                f"WHERE {field} IS NOT NULL"
            )
        )


def downgrade() -> None:
    # Original capitalization cannot be reconstructed after normalization.
    pass
