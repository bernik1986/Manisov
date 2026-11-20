from __future__ import annotations

from collections.abc import Generator
import logging
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./maritime_parser.db")

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    # Longer busy timeout reduces intermittent "database is locked" under concurrent API + UI.
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()
logger = logging.getLogger(__name__)


def _alembic_startup_enabled() -> bool:
    """
    When unset: run Alembic on startup for non-SQLite URLs so production Postgres
    stays aligned with migrations even if the process was started without `alembic upgrade`.
    Set AUTO_ALEMBIC_ON_STARTUP=0 to disable (e.g. multi-tenant or custom migration flow).
    """
    raw = os.getenv("AUTO_ALEMBIC_ON_STARTUP", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return not DATABASE_URL.startswith("sqlite")


def _run_alembic_upgrade_at_startup() -> None:
    if not _alembic_startup_enabled():
        return
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    if not ini_path.is_file():
        logger.warning("Alembic ini not found at %s; skipping startup migrations", ini_path)
        return
    lock_path = Path(tempfile.gettempdir()) / "parcer_alembic_upgrade.lock"
    lock_f = open(lock_path, "a+", encoding="utf-8")
    try:
        try:
            import fcntl

            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        except OSError as exc:
            logger.debug("Alembic lock not acquired (fcntl): %s", exc)

        from alembic import command
        from alembic.config import Config

        cfg = Config(str(ini_path))
        logger.info("Applying Alembic migrations to head")
        command.upgrade(cfg, "head")
    finally:
        try:
            import fcntl

            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
        except OSError:
            pass
        try:
            lock_f.close()
        except OSError:
            pass


def _ensure_company_vessel_tables() -> None:
    """Create company/vessel tables on existing SQLite DBs (create_all alone runs only at startup)."""
    from sqlalchemy import inspect

    from . import schema  # noqa: F401

    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    required = {"company_folders", "companies", "vessels"}
    if required.issubset(names):
        return
    Base.metadata.create_all(
        bind=engine,
        tables=[
            schema.CompanyFolder.__table__,
            schema.Company.__table__,
            schema.Vessel.__table__,
        ],
    )


def _ensure_salary_calculator_tables() -> None:
    """Create salary calculator tables on existing SQLite DBs."""
    from sqlalchemy import inspect

    from . import schema  # noqa: F401

    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    if "salary_component_templates" in names:
        return
    if not {"companies"}.issubset(names):
        return
    Base.metadata.create_all(
        bind=engine,
        tables=[schema.SalaryComponentTemplate.__table__],
    )


def init_db() -> None:
    from sqlalchemy import inspect, text

    from . import schema  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_company_vessel_tables()
    _ensure_salary_calculator_tables()
    # SQLite: create_all does not add new columns to existing tables; keep minimal ALTERs in sync with Alembic.
    if DATABASE_URL.startswith("sqlite"):
        inspector = inspect(engine)
        if "users" in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns("users")}
            with engine.begin() as conn:
                if "auth_version" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN auth_version VARCHAR(32) NOT NULL DEFAULT ''"))
                user_ids = conn.execute(text("SELECT user_id FROM users WHERE auth_version = '' OR auth_version IS NULL")).scalars().all()
                for user_id in user_ids:
                    conn.execute(text("UPDATE users SET auth_version = :version WHERE user_id = :id"),
                                 {"version": uuid4().hex, "id": user_id})
        if "candidate_comments" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("candidate_comments")}
            with engine.begin() as conn:
                for name, definition in (
                    ("reminder_at", "DATETIME"),
                    ("reminder_user_id", "INTEGER CONSTRAINT fk_candidate_comments_reminder_user_id_users REFERENCES users(user_id) ON DELETE SET NULL"),
                    ("reminder_dismissed_at", "DATETIME"),
                ):
                    if name not in columns:
                        conn.execute(text(f"ALTER TABLE candidate_comments ADD COLUMN {name} {definition}"))
                for name in ("reminder_at", "reminder_user_id"):
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_candidate_comments_{name} ON candidate_comments ({name})"))
        if "candidates" in inspector.get_table_names():
            col_names = {c["name"] for c in inspector.get_columns("candidates")}
            alters: list[str] = []
            if "cv_imported" not in col_names:
                alters.append("ALTER TABLE candidates ADD COLUMN cv_imported BOOLEAN NOT NULL DEFAULT 0")
            if "ukr_contract_json" not in col_names:
                alters.append("ALTER TABLE candidates ADD COLUMN ukr_contract_json TEXT")
            if "salary_calculation_json" not in col_names:
                alters.append("ALTER TABLE candidates ADD COLUMN salary_calculation_json TEXT")
            if "contract_json" not in col_names:
                alters.append("ALTER TABLE candidates ADD COLUMN contract_json TEXT")
            if "company_id" not in col_names:
                alters.append("ALTER TABLE candidates ADD COLUMN company_id INTEGER")
            for col_def in (
                "home_airport TEXT",
                "desirable_salary_usd REAL",
                "rejoin_bonus_usd REAL",
                "submission_contract_duration_text TEXT",
                "ecdis_systems_text TEXT",
                "vaccination_summary TEXT",
                "leaving_reason TEXT",
                "employer_reference_note TEXT",
                "passport_visa_status_note TEXT",
                "coc_gmdss_expiry_note TEXT",
                "coc_has_qr_codes BOOLEAN",
                "departure_airport TEXT",
            ):
                col_name = col_def.split()[0]
                if col_name not in col_names:
                    alters.append(f"ALTER TABLE candidates ADD COLUMN {col_def}")
            if alters:
                with engine.begin() as conn:
                    for stmt in alters:
                        conn.execute(text(stmt))
        if "vessels" in inspector.get_table_names():
            vessel_cols = {c["name"] for c in inspector.get_columns("vessels")}
            vessel_alters: list[str] = []
            for col_def in (
                "port_of_registry TEXT",
                "registry_address TEXT",
                "official_number TEXT",
                "call_sign TEXT",
                "grt TEXT",
                "deadweight TEXT",
                "year_built INTEGER",
                "engine_type TEXT",
                "engine_hp TEXT",
                "classification_society TEXT",
            ):
                col_name = col_def.split()[0]
                if col_name not in vessel_cols:
                    vessel_alters.append(f"ALTER TABLE vessels ADD COLUMN {col_def}")
            if vessel_alters:
                with engine.begin() as conn:
                    for stmt in vessel_alters:
                        conn.execute(text(stmt))
        if "certificates" in inspector.get_table_names():
            cert_cols = {c["name"] for c in inspector.get_columns("certificates")}
            if "competency_rank" not in cert_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE certificates ADD COLUMN competency_rank VARCHAR(150)"))
        if "sea_services" in inspector.get_table_names():
            sea_service_cols = {c["name"] for c in inspector.get_columns("sea_services")}
            if "ecdis_dg_maker" not in sea_service_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE sea_services ADD COLUMN ecdis_dg_maker VARCHAR(150)"))

    _run_alembic_upgrade_at_startup()


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
