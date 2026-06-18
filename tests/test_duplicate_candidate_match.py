from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import _find_duplicate_candidate
from models.db import Base
from models.schema import Candidate


def test_find_duplicate_when_file_omits_middle_name() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    with Session() as session:
        session.add(
            Candidate(
                surname="Ivanov",
                first_name="Ivan",
                middle_name="Petrovych",
                date_of_birth=date(1990, 1, 1),
            )
        )
        session.commit()

    with Session() as session:
        parsed = {
            "personal_data": {
                "surname": "Ivanov",
                "first_name": "Ivan",
                "middle_name": None,
                "date_of_birth": "1990-01-01",
            }
        }
        hit = _find_duplicate_candidate(session, parsed)
        assert hit is not None
        assert hit.surname == "IVANOV"


def test_find_duplicate_rejects_different_middle_when_both_present() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    with Session() as session:
        session.add(
            Candidate(
                surname="Ivanov",
                first_name="Ivan",
                middle_name="Petrovych",
                date_of_birth=date(1990, 1, 1),
            )
        )
        session.commit()

    with Session() as session:
        parsed = {
            "personal_data": {
                "surname": "Ivanov",
                "first_name": "Ivan",
                "middle_name": "Semenovych",
                "date_of_birth": "1990-01-01",
            }
        }
        hit = _find_duplicate_candidate(session, parsed)
        assert hit is None


def test_find_duplicate_parses_may_style_date_of_birth() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    with Session() as session:
        session.add(
            Candidate(
                surname="Budurin",
                first_name="Andrii",
                date_of_birth=date(1990, 5, 25),
            )
        )
        session.commit()

    with Session() as session:
        parsed = {
            "personal_data": {
                "surname": "Budurin",
                "first_name": "Andrii",
                "date_of_birth": "25/MAY/1990",
            }
        }
        hit = _find_duplicate_candidate(session, parsed)
        assert hit is not None
        assert hit.surname == "BUDURIN"
