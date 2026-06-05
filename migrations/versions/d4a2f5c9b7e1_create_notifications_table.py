"""create notifications table

Revision ID: d4a2f5c9b7e1
Revises: a9d4e9f7b213
Create Date: 2026-04-23 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a2f5c9b7e1"
down_revision: Union[str, Sequence[str], None] = "a9d4e9f7b213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notifications" in inspector.get_table_names():
        return

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.candidate_id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notifications_id"), "notifications", ["id"], unique=False)
    op.create_index(op.f("ix_notifications_candidate_id"), "notifications", ["candidate_id"], unique=False)
    op.create_index(op.f("ix_notifications_document_id"), "notifications", ["document_id"], unique=False)
    op.create_index(op.f("ix_notifications_sent"), "notifications", ["sent"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notifications" not in inspector.get_table_names():
        return

    op.drop_index(op.f("ix_notifications_sent"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_document_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_candidate_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_id"), table_name="notifications")
    op.drop_table("notifications")
