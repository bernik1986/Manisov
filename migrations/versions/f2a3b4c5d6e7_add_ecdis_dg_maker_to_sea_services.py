"""add ecdis dg maker to sea services

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-15 16:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sea_services" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("sea_services")}
    if "ecdis_dg_maker" not in existing:
        op.add_column("sea_services", sa.Column("ecdis_dg_maker", sa.String(length=150), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sea_services" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("sea_services")}
    if "ecdis_dg_maker" in existing:
        op.drop_column("sea_services", "ecdis_dg_maker")
