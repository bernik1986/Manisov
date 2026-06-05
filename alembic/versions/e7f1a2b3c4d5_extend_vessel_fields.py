"""extend vessels with registry, tonnage and engine fields

Revision ID: e7f1a2b3c4d5
Revises: d6e8f9a0b2c1
Create Date: 2026-06-03 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d6e8f9a0b2c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLUMNS = (
    ("port_of_registry", sa.String(length=150)),
    ("registry_address", sa.String(length=255)),
    ("official_number", sa.String(length=80)),
    ("call_sign", sa.String(length=50)),
    ("grt", sa.String(length=50)),
    ("deadweight", sa.String(length=50)),
    ("year_built", sa.Integer()),
    ("engine_type", sa.String(length=150)),
    ("engine_hp", sa.String(length=80)),
    ("classification_society", sa.String(length=120)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "vessels" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("vessels")}
    for name, col_type in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("vessels", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "vessels" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("vessels")}
    for name, _ in reversed(_NEW_COLUMNS):
        if name in existing:
            op.drop_column("vessels", name)
