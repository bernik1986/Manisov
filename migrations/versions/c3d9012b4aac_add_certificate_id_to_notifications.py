"""add certificate_id to notifications for focus navigation

Revision ID: c3d9012b4aac
Revises: b2c8f1a4e501
Create Date: 2026-04-29 15:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d9012b4aac"
down_revision: Union[str, Sequence[str], None] = "b2c8f1a4e501"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notifications" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("notifications")}
    if "certificate_id" in existing_columns:
        return

    op.add_column("notifications", sa.Column("certificate_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_notifications_certificate_id_certificates",
        "notifications",
        "certificates",
        ["certificate_id"],
        ["certificate_id"],
    )
    op.create_index("ix_notifications_certificate_id", "notifications", ["certificate_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notifications" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("notifications")}
    if "certificate_id" not in existing_columns:
        return

    op.drop_index("ix_notifications_certificate_id", table_name="notifications")
    op.drop_constraint("fk_notifications_certificate_id_certificates", "notifications", type_="foreignkey")
    op.drop_column("notifications", "certificate_id")
