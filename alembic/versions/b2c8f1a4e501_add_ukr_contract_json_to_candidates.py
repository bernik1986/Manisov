"""add ukr_contract_json to candidates

Revision ID: b2c8f1a4e501
Revises: a9d4e9f7b213
Create Date: 2026-04-25 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c8f1a4e501"
down_revision: Union[str, Sequence[str], None] = "a9d4e9f7b213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("candidates")}
    if "ukr_contract_json" not in existing_columns:
        op.add_column("candidates", sa.Column("ukr_contract_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "ukr_contract_json")
