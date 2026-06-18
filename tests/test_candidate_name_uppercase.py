from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import _apply_composed_full_names, _coerce_model_payload
from models.db import Base
from models.schema import Candidate


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_candidate_import_payload_uppercases_all_name_variants() -> None:
    payload = _coerce_model_payload(
        Candidate,
        {
            "surname": "  Ivanov  ",
            "first_name": "Ivan",
            "middle_name": "Petrovych",
            "full_name": "Ivan Petrovych Ivanov",
            "latin_full_name": "Ivan Petrovych Ivanov",
            "native_full_name": "Іван Петрович Іванов",
            "email": "Ivanov@example.com",
        },
    )

    assert payload == {
        "surname": "IVANOV",
        "first_name": "IVAN",
        "middle_name": "PETROVYCH",
        "full_name": "IVAN PETROVYCH IVANOV",
        "latin_full_name": "IVAN PETROVYCH IVANOV",
        "native_full_name": "ІВАН ПЕТРОВИЧ ІВАНОВ",
        "email": "Ivanov@example.com",
    }


def test_candidate_model_event_covers_direct_parser_and_script_saves() -> None:
    Session = _session_factory()
    with Session() as session:
        candidate = Candidate(
            surname="Petrov",
            first_name="Petr",
            middle_name="Oleksiiovych",
            full_name="Petr Oleksiiovych Petrov",
            latin_full_name="Petr Oleksiiovych Petrov",
            native_full_name="Петро Олексійович Петров",
        )
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        assert candidate.surname == "PETROV"
        assert candidate.first_name == "PETR"
        assert candidate.middle_name == "OLEKSIIOVYCH"
        assert candidate.full_name == "PETR OLEKSIIOVYCH PETROV"
        assert candidate.latin_full_name == "PETR OLEKSIIOVYCH PETROV"
        assert candidate.native_full_name == "ПЕТРО ОЛЕКСІЙОВИЧ ПЕТРОВ"

        candidate.first_name = "Petro"
        session.commit()
        session.refresh(candidate)
        assert candidate.first_name == "PETRO"


def test_candidate_api_projection_composes_uppercase_full_names() -> None:
    result = _apply_composed_full_names(
        {
            "surname": "Shevchenko",
            "first_name": "Taras",
            "middle_name": "Hryhorovych",
            "full_name": "stale value",
            "latin_full_name": "stale latin value",
            "native_full_name": "Тарас Григорович Шевченко",
        }
    )

    assert result["surname"] == "SHEVCHENKO"
    assert result["first_name"] == "TARAS"
    assert result["middle_name"] == "HRYHOROVYCH"
    assert result["full_name"] == "SHEVCHENKO TARAS"
    assert result["latin_full_name"] == "SHEVCHENKO TARAS"
    assert result["native_full_name"] == "ТАРАС ГРИГОРОВИЧ ШЕВЧЕНКО"
