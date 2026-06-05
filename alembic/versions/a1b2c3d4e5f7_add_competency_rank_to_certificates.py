"""add competency_rank to certificates

Revision ID: a1b2c3d4e5f7
Revises: f8b2c3d4e5f6
Create Date: 2026-06-04 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f8b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "certificates" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("certificates")}
    if "competency_rank" not in existing:
        op.add_column("certificates", sa.Column("competency_rank", sa.String(length=150), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "certificates" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("certificates")}
    if "competency_rank" in existing:
        op.drop_column("certificates", "competency_rank")
