"""add contract_json to candidates

Revision ID: f8b2c3d4e5f6
Revises: e7f1a2b3c4d5
Create Date: 2026-06-04 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e7f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidates" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("candidates")}
    if "contract_json" not in existing:
        op.add_column("candidates", sa.Column("contract_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidates" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("candidates")}
    if "contract_json" in existing:
        op.drop_column("candidates", "contract_json")
