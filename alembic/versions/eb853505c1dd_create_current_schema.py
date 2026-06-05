"""create current schema

Revision ID: eb853505c1dd
Revises: 
Create Date: 2026-04-22 13:29:36.689969

"""
from typing import Sequence, Union

from alembic import op
from models import schema  # noqa: F401
from models.db import Base


# revision identifiers, used by Alembic.
revision: str = 'eb853505c1dd'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
