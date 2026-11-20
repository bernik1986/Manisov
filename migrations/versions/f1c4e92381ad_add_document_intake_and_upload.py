"""Add private scan drafts, personal upload links and the review inbox.

Revision ID: f1c4e92381ad
Revises: b5c6d7e8f9a0
"""

from alembic import op
import sqlalchemy as sa

revision = "f1c4e92381ad"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade():
    # Fresh installs create the current ORM schema in the baseline migration.
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "document_intake_files" not in tables:
        op.create_table(
            "document_intake_files",
            sa.Column("file_id", sa.String(32), primary_key=True),
            sa.Column("batch_id", sa.String(32), nullable=False),
            sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE")),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(30)),
            sa.Column("content", sa.LargeBinary()),
            sa.Column("result", sa.JSON(), nullable=False),
            sa.Column("saved_key", sa.String(64)),
        )
        op.create_index("ix_document_intake_owner", "document_intake_files", ["candidate_id", "owner_id", "batch_id"])
        op.create_index("ix_document_intake_files_created_at", "document_intake_files", ["created_at"])
    if "document_upload_links" not in tables:
        op.create_table(
            "document_upload_links",
            sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id", ondelete="CASCADE"), primary_key=True),
            sa.Column("token", sa.String(43), unique=True, nullable=False),
        )
    if "document_upload_submissions" not in tables:
        op.create_table(
            "document_upload_submissions",
            sa.Column("submission_id", sa.String(32), primary_key=True),
            sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False),
            sa.Column("request_id", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("file_count", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("closed_at", sa.DateTime()),
            sa.UniqueConstraint("candidate_id", "request_id", name="uq_document_upload_request"),
        )
        op.create_index("ix_document_upload_submissions_candidate_id", "document_upload_submissions", ["candidate_id"])


def downgrade():
    op.drop_table("document_upload_submissions")
    op.drop_table("document_upload_links")
    op.drop_table("document_intake_files")
