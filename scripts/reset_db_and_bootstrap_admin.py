from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from passlib.context import CryptContext

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.db import Base, SessionLocal, engine
from models.schema import Role, User

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def reset_database(*, use_alembic: bool) -> None:
    print("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)

    if use_alembic:
        ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        if not ini_path.exists():
            raise FileNotFoundError(f"Alembic config not found: {ini_path}")
        print("Recreating schema via Alembic migrations (upgrade head)...")
        cfg = Config(str(ini_path))
        command.upgrade(cfg, "head")
        return

    print("Recreating schema via SQLAlchemy metadata...")
    Base.metadata.create_all(bind=engine)


def bootstrap_default_admin() -> None:
    print("Bootstrapping roles and default admin...")
    role_names = {"admin": "Full access", "recruiter": "Can manage records", "viewer": "Read only"}
    default_admin_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin").strip() or "admin"
    default_admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    default_admin_full_name = os.getenv("DEFAULT_ADMIN_FULL_NAME", "Default Admin").strip() or "Default Admin"

    session = SessionLocal()
    try:
        for name, description in role_names.items():
            if not session.query(Role).filter(Role.name == name).one_or_none():
                session.add(Role(name=name, description=description))
        session.flush()

        admin_role = session.query(Role).filter(Role.name == "admin").one()
        admin_user = session.query(User).filter(User.username == default_admin_username).one_or_none()
        if not admin_user:
            session.add(
                User(
                    username=default_admin_username,
                    password_hash=pwd_context.hash(default_admin_password),
                    full_name=default_admin_full_name,
                    role_id=admin_role.role_id,
                    is_active=True,
                )
            )
        session.commit()
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset DB to empty state and create default admin from env variables."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive reset.",
    )
    parser.add_argument(
        "--skip-alembic",
        action="store_true",
        help="Use SQLAlchemy create_all instead of Alembic migrations.",
    )
    args = parser.parse_args()

    if not args.yes and not _bool_env("ALLOW_DB_RESET", default=False):
        raise SystemExit(
            "Refusing to reset DB without confirmation. "
            "Use --yes or set ALLOW_DB_RESET=1 for non-interactive environments."
        )

    print("Starting database reset...")
    reset_database(use_alembic=not args.skip_alembic)
    bootstrap_default_admin()
    print("Done. Database is clean and default admin is ensured.")
    print("Admin credentials source:")
    print("  DEFAULT_ADMIN_USERNAME (default: admin)")
    print("  DEFAULT_ADMIN_PASSWORD (default: admin123)")
    print("  DEFAULT_ADMIN_FULL_NAME (default: Default Admin)")


if __name__ == "__main__":
    main()
