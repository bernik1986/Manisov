"""add submission info-list fields to candidates

Revision ID: d5e6f7a8b9c0
Revises: c3d9012b4aac
Create Date: 2026-05-18 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c3d9012b4aac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLUMNS = [
    ("home_airport", sa.String(255)),
    ("desirable_salary_usd", sa.Float()),
    ("rejoin_bonus_usd", sa.Float()),
    ("submission_contract_duration_text", sa.String(100)),
    ("ecdis_systems_text", sa.Text()),
    ("vaccination_summary", sa.Text()),
    ("leaving_reason", sa.Text()),
    ("employer_reference_note", sa.Text()),
    ("passport_visa_status_note", sa.Text()),
    ("coc_gmdss_expiry_note", sa.Text()),
    ("coc_has_qr_codes", sa.Boolean()),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidates" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("candidates")}
    for name, col_type in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("candidates", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_NEW_COLUMNS):
        op.drop_column("candidates", name)
