"""add cv_imported to candidates

Revision ID: a9d4e9f7b213
Revises: eb853505c1dd
Create Date: 2026-04-23 08:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9d4e9f7b213"
down_revision: Union[str, Sequence[str], None] = "eb853505c1dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("candidates")}
    if "cv_imported" not in existing_columns:
        op.add_column(
            "candidates",
            sa.Column("cv_imported", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("candidates", "cv_imported")
