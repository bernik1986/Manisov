"""Tests for candidate submission pack (ПОДАЧА) ZIP endpoint."""

from __future__ import annotations

import io
import zipfile
from uuid import uuid4

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.main import app, get_db_session
from models.db import Base
from models.schema import Candidate, Role, TemplateFile, TemplateFolder, User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@pytest.fixture
def db_setup():
    engine = __import__("sqlalchemy").create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield lambda: TestingSessionLocal()
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def users_fixture(db_setup):
    db_session = db_setup()
    admin_role = Role(name="admin")
    viewer_role = Role(name="viewer")
    db_session.add_all([admin_role, viewer_role])
    db_session.flush()
    db_session.add(
        User(
            username="admin_sub",
            password_hash=pwd_context.hash("admin123"),
            role_id=admin_role.role_id,
            is_active=True,
        )
    )
    db_session.add(
        User(
            username="viewer_sub",
            password_hash=pwd_context.hash("viewer123"),
            role_id=viewer_role.role_id,
            is_active=True,
        )
    )
    db_session.commit()
    yield
    db_session.close()


@pytest.fixture
def client(db_setup, tmp_path, users_fixture):
    templates_dir = tmp_path / "templates"
    generated_dir = tmp_path / "generated"
    manager_dir = tmp_path / "manager_files"
    podacha_dir = templates_dir / "Podacha"
    podacha_dir.mkdir(parents=True)
    generated_dir.mkdir(parents=True)
    manager_dir.mkdir(parents=True)

    template_path = podacha_dir / "info_list_new.docx"
    doc = DocxDocument()
    doc.add_paragraph("Rank {{ rank }} {{ surname }} {{ first_name }}")
    doc.add_paragraph("Opening m/v {{ opening_vessel }}")
    doc.save(template_path)

    main_module.TEMPLATES_DIR = templates_dir
    main_module.GENERATED_DIR = generated_dir
    main_module.TEMPLATES_MANAGER_DIR = manager_dir
    main_module.UPLOADS_DIR = tmp_path / "uploads"
    main_module.UPLOADS_DIR.mkdir(parents=True)

    def override_get_db_session():
        session = db_setup()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app) as test_client:
            db_session = db_setup()
            try:
                main_module.ensure_podacha_builtin_templates(
                    db_session,
                    templates_dir=templates_dir,
                    templates_manager_dir=manager_dir,
                    get_or_create_root=main_module._get_or_create_templates_root,
                )
            finally:
                db_session.close()
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_submission_pack_returns_zip_with_generated_docx(client: TestClient, db_setup):
    db_session = db_setup()
    candidate = Candidate(
        surname="Martynyuk",
        first_name="Gennadiy",
        current_rank="Master",
        watch_officer_since_year=2015,
        home_airport="Warsaw, Poland",
        english_level="Normal",
    )
    db_session.add(candidate)
    db_session.flush()

    stored = f"{uuid4().hex}.docx"
    src = main_module.TEMPLATES_DIR / "Podacha" / "info_list_new.docx"
    target = main_module.TEMPLATES_MANAGER_DIR / stored
    target.write_bytes(src.read_bytes())

    root = TemplateFolder(name="Templates", parent_id=None)
    db_session.add(root)
    db_session.flush()
    folder = TemplateFolder(name="Podacha", parent_id=root.folder_id)
    db_session.add(folder)
    db_session.flush()
    tpl = TemplateFile(
        folder_id=folder.folder_id,
        file_name="info_list_new.docx",
        file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        stored_name=stored,
        relative_path=stored,
        file_size_bytes=target.stat().st_size,
    )
    db_session.add(tpl)
    db_session.commit()
    db_session.refresh(candidate)
    db_session.refresh(tpl)

    headers = _login(client, "viewer_sub", "viewer123")
    response = client.post(
        f"/candidates/{candidate.candidate_id}/submission-pack",
        json={
            "opening_vessel": "Edessaikos",
            "previous_vessel": "",
            "template_file_ids": [tpl.template_file_id],
            "attachment_ids": [],
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/zip"
    assert len(response.content) > 0

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert names[0].lower().endswith(".docx")

    db_session.close()


def test_submission_pack_rejects_empty_selection(client: TestClient, db_setup):
    db_session = db_setup()
    candidate = Candidate(surname="Empty", first_name="Pack")
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    headers = _login(client, "admin_sub", "admin123")
    response = client.post(
        f"/candidates/{candidate.candidate_id}/submission-pack",
        json={"template_file_ids": [], "attachment_ids": []},
        headers=headers,
    )
    assert response.status_code == 400
    db_session.close()


def test_candidate_update_persists_submission_fields(client: TestClient, db_setup):
    db_session = db_setup()
    candidate = Candidate(surname="Fields", first_name="Test")
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    headers = _login(client, "admin_sub", "admin123")
    response = client.put(
        f"/candidates/{candidate.candidate_id}",
        json={
            "home_airport": "Odessa",
            "desirable_salary_usd": 9500,
            "rejoin_bonus_usd": 500,
            "vaccination_summary": "fully vaccinated",
        },
        headers=headers,
    )
    assert response.status_code == 200
    db_session.expire_all()
    stored = db_session.get(Candidate, candidate.candidate_id)
    assert stored.home_airport == "Odessa"
    assert stored.desirable_salary_usd == 9500
    assert stored.rejoin_bonus_usd == 500
    assert stored.vaccination_summary == "fully vaccinated"
    db_session.close()
