from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.main import app, get_db_session, pwd_context
from app.salary_calculator import calculate_salary, fixed_components_total, owners_bonus
from models.db import Base
from models.schema import Company, CompanyFolder, Role, SalaryComponentTemplate, User


@pytest.fixture
def db_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


@pytest.fixture
def db_session(db_setup):
    session = db_setup()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_company(db_session):
    admin_role = Role(name="admin", description="Admin")
    db_session.add(admin_role)
    db_session.flush()
    user = User(
        username="admin_salary",
        password_hash=pwd_context.hash("admin123"),
        full_name="Admin",
        role_id=admin_role.role_id,
        is_active=True,
    )
    root = CompanyFolder(name="Companies", parent_id=None)
    db_session.add_all([user, root])
    db_session.flush()
    company = Company(folder_id=root.folder_id, name="Company A", slug="company_a")
    db_session.add(company)
    db_session.flush()
    template = SalaryComponentTemplate(
        company_id=company.company_id,
        rank="Captain",
        basic_monthly_wage=854,
        monthly_overtime=634,
        overtime_rate=0,
        sepf=10,
        imtf=5,
        leave=256,
        leave_sub=70,
        various_extra_overtime=351,
    )
    db_session.add(template)
    db_session.commit()
    return {"user": user, "company": company, "template": template}


@pytest.fixture
def client(db_setup, tmp_path):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True)
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(parents=True)

    def override_get_db():
        db = db_setup()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_get_db
    main_module.TEMPLATES_DIR = templates_dir
    main_module.GENERATED_DIR = generated_dir
    main_module.TEMPLATES_MANAGER_DIR = templates_dir / "manager_files"
    main_module.TEMPLATES_MANAGER_DIR.mkdir(parents=True)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_fixed_total_and_owners_bonus():
    components = {
        "basic_monthly_wage": 854,
        "monthly_overtime": 634,
        "sepf": 10,
        "imtf": 5,
        "leave": 256,
        "leave_sub": 70,
        "various_extra_overtime": 351,
        "overtime_rate": 99,
    }
    assert fixed_components_total(components) == 2180.0
    assert owners_bonus(3000, 2180) == 820.0


def test_calculate_salary_example(db_session, seeded_company):
    company = seeded_company["company"]
    result = calculate_salary(
        db_session,
        company_id=company.company_id,
        rank="Captain",
        total_wage=3000,
        period_of_employment="6 months",
    )
    assert result["valid"] is True
    assert result["fixed_components_total"] == 2180.0
    assert result["owners_bonus"] == 820.0
    assert result["period_of_employment"] == "6 months"


def test_calculate_rejects_low_total_wage(db_session, seeded_company):
    company = seeded_company["company"]
    result = calculate_salary(
        db_session,
        company_id=company.company_id,
        rank="Captain",
        total_wage=1000,
    )
    assert result["valid"] is False
    assert any("lower" in err.lower() for err in result["errors"])


def test_save_and_template_context(client, db_setup, seeded_company):
    from models.schema import Candidate

    company = seeded_company["company"]
    db = db_setup()
    candidate = Candidate(surname="Test", first_name="User")
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    login = client.post("/auth/login", json={"username": "admin_salary", "password": "admin123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    save = client.put(
        f"/candidates/{candidate.candidate_id}/salary-calculator",
        headers=headers,
        json={
            "company_id": company.company_id,
            "rank": "Captain",
            "total_wage": 3000,
            "period_of_employment": "6 months",
        },
    )
    assert save.status_code == 200, save.text
    saved = save.json()["calculation"]
    assert saved["owners_bonus"] == 820

    db.refresh(candidate)
    context = main_module._serialize_candidate_context(candidate, db_session=db)
    assert context["salary_owners_bonus"] == "820"
    assert context["salary_total_wage"] == "3000"
    assert context["salary_company"] == "Company A"


def test_list_ranks_for_company(client, seeded_company):
    company = seeded_company["company"]
    login = client.post("/auth/login", json={"username": "admin_salary", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/companies-manager/companies/{company.company_id}/salary-ranks", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ranks"] == ["Captain"]


def test_import_salary_scale_xlsx_api(client, db_session, seeded_company):
    import io

    import pandas as pd

    company = seeded_company["company"]
    company.slug = "drylog"
    company.name = "DRYLOG"
    db_session.commit()

    buf = io.BytesIO()
    df = pd.DataFrame(
        {
            "Rank": ["Second Officer"],
            "Basic Pay": [800],
            "Guaranteed O/T (103 hrs)": [100],
            "Extra O/T (57 hrs)": [50],
            "Leave Pay": [10],
            "Leave Sub": [5],
        }
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="DryLog PTE LTD", index=False)

    login = client.post("/auth/login", json={"username": "admin_salary", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.post(
        "/companies-manager/salary-scale/import",
        files={
            "file": (
                "Salary Scale.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"company_slug": "drylog"},
        headers=headers,
    )
    assert resp.status_code == 200
    stats = resp.json()["stats"]
    assert stats["created"] + stats["updated"] >= 1
