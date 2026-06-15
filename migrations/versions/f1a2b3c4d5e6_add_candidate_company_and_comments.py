"""add candidate company and comments

Revision ID: f1a2b3c4d5e6
Revises: b2c3d4e5f6a8
Create Date: 2026-06-15 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "candidates" in table_names:
        candidate_cols = {c["name"] for c in inspector.get_columns("candidates")}
        if "company_id" not in candidate_cols:
            op.add_column("candidates", sa.Column("company_id", sa.Integer(), nullable=True))
            op.create_index(op.f("ix_candidates_company_id"), "candidates", ["company_id"], unique=False)
        elif "ix_candidates_company_id" not in {idx["name"] for idx in inspector.get_indexes("candidates")}:
            op.create_index(op.f("ix_candidates_company_id"), "candidates", ["company_id"], unique=False)

        if bind.dialect.name != "sqlite" and "companies" in table_names:
            fk_names = {fk.get("name") for fk in inspector.get_foreign_keys("candidates")}
            if "fk_candidates_company_id_companies" not in fk_names:
                op.create_foreign_key(
                    "fk_candidates_company_id_companies",
                    "candidates",
                    "companies",
                    ["company_id"],
                    ["company_id"],
                    ondelete="SET NULL",
                )

    if "candidate_comments" not in table_names:
        op.create_table(
            "candidate_comments",
            sa.Column("comment_id", sa.Integer(), nullable=False),
            sa.Column("candidate_id", sa.Integer(), nullable=False),
            sa.Column("comment_text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["candidate_id"], ["candidates.candidate_id"]),
            sa.PrimaryKeyConstraint("comment_id"),
        )
        op.create_index(op.f("ix_candidate_comments_comment_id"), "candidate_comments", ["comment_id"], unique=False)
        op.create_index(op.f("ix_candidate_comments_candidate_id"), "candidate_comments", ["candidate_id"], unique=False)
        op.create_index(op.f("ix_candidate_comments_created_at"), "candidate_comments", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "candidate_comments" in table_names:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("candidate_comments")}
        for index_name in (
            op.f("ix_candidate_comments_created_at"),
            op.f("ix_candidate_comments_candidate_id"),
            op.f("ix_candidate_comments_comment_id"),
        ):
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="candidate_comments")
        op.drop_table("candidate_comments")

    if "candidates" in table_names:
        if bind.dialect.name != "sqlite":
            fk_names = {fk.get("name") for fk in inspector.get_foreign_keys("candidates")}
            if "fk_candidates_company_id_companies" in fk_names:
                op.drop_constraint("fk_candidates_company_id_companies", "candidates", type_="foreignkey")
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("candidates")}
        if op.f("ix_candidates_company_id") in existing_indexes:
            op.drop_index(op.f("ix_candidates_company_id"), table_name="candidates")
        existing_columns = {c["name"] for c in inspector.get_columns("candidates")}
        if "company_id" in existing_columns:
            op.drop_column("candidates", "company_id")
