from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import (
    LAST_ACTIVE_ADMIN_ERROR,
    SELF_ACTIVE_ADMIN_ROLE_CHANGE_ERROR,
    _assert_not_last_active_admin_lockout,
    app,
    get_db_session,
    pwd_context,
)
from models.db import Base
from models.schema import Role, User


@pytest.fixture
def testing_session_local():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_local


@pytest.fixture
def db_session(testing_session_local):
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(testing_session_local):
    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth_seed(db_session):
    admin_role = Role(name="admin", description="Admin")
    recruiter_role = Role(name="recruiter", description="Recruiter")
    viewer_role = Role(name="viewer", description="Viewer")
    db_session.add_all([admin_role, recruiter_role, viewer_role])
    db_session.flush()

    admin_1 = User(
        username="admin_one",
        password_hash=pwd_context.hash("admin123"),
        full_name="Admin One",
        role_id=admin_role.role_id,
        is_active=True,
    )
    admin_2 = User(
        username="admin_two",
        password_hash=pwd_context.hash("admin123"),
        full_name="Admin Two",
        role_id=admin_role.role_id,
        is_active=True,
    )
    recruiter = User(
        username="recruiter_one",
        password_hash=pwd_context.hash("recruit123"),
        full_name="Recruiter One",
        role_id=recruiter_role.role_id,
        is_active=True,
    )
    viewer = User(
        username="viewer_one",
        password_hash=pwd_context.hash("viewer123"),
        full_name="Viewer One",
        role_id=viewer_role.role_id,
        is_active=True,
    )
    db_session.add_all([admin_1, admin_2, recruiter, viewer])
    db_session.commit()
    return {
        "admin_1": admin_1,
        "admin_2": admin_2,
        "recruiter": recruiter,
        "viewer": viewer,
        "admin_role": admin_role,
        "recruiter_role": recruiter_role,
        "viewer_role": viewer_role,
    }


def _auth_header(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _make_admin_one_last_active(db_session, auth_seed):
    auth_seed["admin_2"].is_active = False
    db_session.commit()
    db_session.refresh(auth_seed["admin_1"])


def test_last_admin_cannot_demote_self(client: TestClient, db_session, auth_seed):
    _make_admin_one_last_active(db_session, auth_seed)
    headers = _auth_header(client, "admin_one", "admin123")

    response = client.put(
        f"/auth/users/{auth_seed['admin_1'].user_id}/role",
        json={"role": "recruiter"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == SELF_ACTIVE_ADMIN_ROLE_CHANGE_ERROR


def test_active_admin_cannot_change_own_role_even_with_other_admins(client: TestClient, auth_seed):
    headers = _auth_header(client, "admin_one", "admin123")

    response = client.put(
        f"/auth/users/{auth_seed['admin_1'].user_id}/role",
        json={"role": "recruiter"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == SELF_ACTIVE_ADMIN_ROLE_CHANGE_ERROR


def test_last_admin_cannot_be_demoted_by_another_admin_business_guard(db_session, auth_seed):
    _make_admin_one_last_active(db_session, auth_seed)
    db_session.refresh(auth_seed["admin_1"])
    with pytest.raises(HTTPException) as err:
        _assert_not_last_active_admin_lockout(
            db_session,
            target_user=auth_seed["admin_1"],
            remove_admin_privileges=True,
        )
    assert err.value.status_code == 400
    assert err.value.detail == LAST_ACTIVE_ADMIN_ERROR


def test_last_admin_cannot_be_deleted(client: TestClient, db_session, auth_seed):
    _make_admin_one_last_active(db_session, auth_seed)
    headers = _auth_header(client, "admin_one", "admin123")

    response = client.delete(f"/auth/users/{auth_seed['admin_1'].user_id}", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == LAST_ACTIVE_ADMIN_ERROR


def test_last_admin_cannot_be_deactivated(client: TestClient, db_session, auth_seed):
    _make_admin_one_last_active(db_session, auth_seed)
    headers = _auth_header(client, "admin_one", "admin123")

    response = client.put(
        f"/auth/users/{auth_seed['admin_1'].user_id}/active",
        json={"is_active": False},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == LAST_ACTIVE_ADMIN_ERROR


def test_demotion_allowed_when_more_than_one_active_admin(client: TestClient, auth_seed):
    headers = _auth_header(client, "admin_two", "admin123")

    response = client.put(
        f"/auth/users/{auth_seed['admin_1'].user_id}/role",
        json={"role": "recruiter"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "recruiter"


def test_non_admin_users_can_be_edited_without_lockout_restriction(client: TestClient, auth_seed):
    headers = _auth_header(client, "admin_one", "admin123")

    role_response = client.put(
        f"/auth/users/{auth_seed['viewer'].user_id}/role",
        json={"role": "recruiter"},
        headers=headers,
    )
    assert role_response.status_code == 200
    assert role_response.json()["user"]["role"] == "recruiter"

    active_response = client.put(
        f"/auth/users/{auth_seed['recruiter'].user_id}/active",
        json={"is_active": False},
        headers=headers,
    )
    assert active_response.status_code == 200
    assert active_response.json()["user"]["is_active"] is False


def test_last_admin_lockout_error_message_is_exact(client: TestClient, db_session, auth_seed):
    _make_admin_one_last_active(db_session, auth_seed)
    headers = _auth_header(client, "admin_one", "admin123")

    response = client.put(
        f"/auth/users/{auth_seed['admin_1'].user_id}/active",
        json={"is_active": False},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {"detail": LAST_ACTIVE_ADMIN_ERROR}
