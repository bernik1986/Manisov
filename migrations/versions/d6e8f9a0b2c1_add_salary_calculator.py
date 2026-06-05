"""add salary calculator tables and candidate field

Revision ID: d6e8f9a0b2c1
Revises: c3f7a2b91d04
Create Date: 2026-06-02 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6e8f9a0b2c1"
down_revision: Union[str, Sequence[str], None] = "c3f7a2b91d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "salary_component_templates" not in existing:
        op.create_table(
            "salary_component_templates",
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("rank", sa.String(length=120), nullable=False),
            sa.Column("basic_monthly_wage", sa.Float(), nullable=False, server_default="0"),
            sa.Column("monthly_overtime", sa.Float(), nullable=False, server_default="0"),
            sa.Column("overtime_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("sepf", sa.Float(), nullable=False, server_default="0"),
            sa.Column("imtf", sa.Float(), nullable=False, server_default="0"),
            sa.Column("leave", sa.Float(), nullable=False, server_default="0"),
            sa.Column("leave_sub", sa.Float(), nullable=False, server_default="0"),
            sa.Column("various_extra_overtime", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.company_id"]),
            sa.PrimaryKeyConstraint("template_id"),
            sa.UniqueConstraint("company_id", "rank", name="uq_salary_template_company_rank"),
        )
        op.create_index(
            op.f("ix_salary_component_templates_template_id"),
            "salary_component_templates",
            ["template_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_salary_component_templates_company_id"),
            "salary_component_templates",
            ["company_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_salary_component_templates_rank"),
            "salary_component_templates",
            ["rank"],
            unique=False,
        )

    if "candidates" in existing:
        cols = {c["name"] for c in inspector.get_columns("candidates")}
        if "salary_calculation_json" not in cols:
            op.add_column("candidates", sa.Column("salary_calculation_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "salary_calculation_json")
    op.drop_table("salary_component_templates")
