"""add company folder, company and vessel tables

Revision ID: c3f7a2b91d04
Revises: d5e6f7a8b9c0
Create Date: 2026-05-28 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f7a2b91d04"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "company_folders" not in existing:
        op.create_table(
            "company_folders",
            sa.Column("folder_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["parent_id"], ["company_folders.folder_id"]),
            sa.PrimaryKeyConstraint("folder_id"),
        )
        op.create_index(op.f("ix_company_folders_folder_id"), "company_folders", ["folder_id"], unique=False)
        op.create_index(op.f("ix_company_folders_parent_id"), "company_folders", ["parent_id"], unique=False)

    if "companies" not in existing:
        op.create_table(
            "companies",
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("folder_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["folder_id"], ["company_folders.folder_id"]),
            sa.PrimaryKeyConstraint("company_id"),
            sa.UniqueConstraint("slug", name="uq_companies_slug"),
        )
        op.create_index(op.f("ix_companies_company_id"), "companies", ["company_id"], unique=False)
        op.create_index(op.f("ix_companies_folder_id"), "companies", ["folder_id"], unique=False)
        op.create_index(op.f("ix_companies_slug"), "companies", ["slug"], unique=False)

    if "vessels" not in existing:
        op.create_table(
            "vessels",
            sa.Column("vessel_id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("imo", sa.String(length=50), nullable=True),
            sa.Column("flag", sa.String(length=100), nullable=True),
            sa.Column("vessel_type", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.company_id"]),
            sa.PrimaryKeyConstraint("vessel_id"),
            sa.UniqueConstraint("company_id", "slug", name="uq_vessels_company_slug"),
        )
        op.create_index(op.f("ix_vessels_company_id"), "vessels", ["company_id"], unique=False)
        op.create_index(op.f("ix_vessels_slug"), "vessels", ["slug"], unique=False)
        op.create_index(op.f("ix_vessels_vessel_id"), "vessels", ["vessel_id"], unique=False)


def downgrade() -> None:
    op.drop_table("vessels")
    op.drop_table("companies")
    op.drop_table("company_folders")
