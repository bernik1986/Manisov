"""add departure_airport to candidates

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-06-04 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidates" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("candidates")}
    if "departure_airport" not in existing:
        op.add_column("candidates", sa.Column("departure_airport", sa.String(length=255), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidates" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("candidates")}
    if "departure_airport" in existing:
        op.drop_column("candidates", "departure_airport")
