"""add reminders to candidate comments

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidate_comments" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("candidate_comments")}
    with op.batch_alter_table("candidate_comments") as batch_op:
        if "reminder_at" not in existing_columns:
            batch_op.add_column(sa.Column("reminder_at", sa.DateTime(), nullable=True))
            batch_op.create_index("ix_candidate_comments_reminder_at", ["reminder_at"], unique=False)
        if "reminder_user_id" not in existing_columns:
            batch_op.add_column(sa.Column("reminder_user_id", sa.Integer(), nullable=True))
            batch_op.create_index("ix_candidate_comments_reminder_user_id", ["reminder_user_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_candidate_comments_reminder_user_id_users",
                "users",
                ["reminder_user_id"],
                ["user_id"],
                ondelete="SET NULL",
            )
        if "reminder_dismissed_at" not in existing_columns:
            batch_op.add_column(sa.Column("reminder_dismissed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidate_comments" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("candidate_comments")}
    indexes = {index["name"] for index in inspector.get_indexes("candidate_comments")}
    foreign_keys = inspector.get_foreign_keys("candidate_comments")
    # SQLite create_all/older startup ALTERs left unnamed constraints. Naming
    # reflection gives those a stable handle without changing unrelated FKs.
    naming_convention = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    with op.batch_alter_table("candidate_comments", naming_convention=naming_convention) as batch_op:
        if "reminder_dismissed_at" in existing_columns:
            batch_op.drop_column("reminder_dismissed_at")
        if "reminder_user_id" in existing_columns:
            for foreign_key in foreign_keys:
                if "reminder_user_id" in foreign_key["constrained_columns"]:
                    name = foreign_key["name"] or (
                        f"fk_candidate_comments_{foreign_key['constrained_columns'][0]}_"
                        f"{foreign_key['referred_table']}"
                    )
                    batch_op.drop_constraint(name, type_="foreignkey")
            if "ix_candidate_comments_reminder_user_id" in indexes:
                batch_op.drop_index("ix_candidate_comments_reminder_user_id")
            batch_op.drop_column("reminder_user_id")
        if "reminder_at" in existing_columns:
            if "ix_candidate_comments_reminder_at" in indexes:
                batch_op.drop_index("ix_candidate_comments_reminder_at")
            batch_op.drop_column("reminder_at")
