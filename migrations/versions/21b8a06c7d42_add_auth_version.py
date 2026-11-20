"""Persist revocable authentication versions for each user."""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "21b8a06c7d42"
down_revision = "f1c4e92381ad"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "auth_version" not in columns:
        if bind.dialect.name == "sqlite":
            op.add_column("users", sa.Column("auth_version", sa.String(32), nullable=False, server_default=""))
        else:
            op.add_column("users", sa.Column("auth_version", sa.String(32), nullable=True))
    users = sa.table("users", sa.column("user_id", sa.Integer), sa.column("auth_version", sa.String(32)))
    ids = bind.execute(sa.select(users.c.user_id).where(sa.or_(users.c.auth_version.is_(None), users.c.auth_version == ""))).scalars().all()
    for user_id in ids:
        bind.execute(users.update().where(users.c.user_id == user_id).values(auth_version=uuid4().hex))
    if bind.dialect.name != "sqlite":
        op.alter_column("users", "auth_version", existing_type=sa.String(32), nullable=False)
    # Rebuilding SQLite users can cascade-delete scan drafts when FK checks are
    # enabled. Keep the original table and its references intact.


def downgrade():
    if "auth_version" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}:
        op.drop_column("users", "auth_version")
