from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import app.main as main
from models.db import Base
from models.schema import Role, User


@pytest.fixture
def auth_api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as db:
        admin = Role(name="admin")
        viewer = Role(name="viewer")
        db.add_all([admin, viewer])
        db.flush()
        for name in ("operator", "second"):
            db.add(User(username=name, password_hash=main.pwd_context.hash("test-password-123"), role_id=admin.role_id))
        db.commit()

    def session():
        with sessions() as db:
            yield db

    main.app.dependency_overrides[main.get_db_session] = session
    client = TestClient(main.app)
    try:
        yield client, sessions
    finally:
        client.close()
        main.app.dependency_overrides.clear()
        engine.dispose()


def _login(client, username="operator", password="test-password-123"):
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(token):
    return {"Authorization": "Bearer " + token}


def test_reset_route_not_registered_in_normal_app():
    assert "/test/reset-login-throttle" not in {getattr(route, "path", None) for route in main.app.routes}


def test_forwarded_header_does_not_change_login_throttle_identity():
    request = Request({"type": "http", "client": ("192.0.2.10", 1234),
                       "headers": [(b"x-forwarded-for", b"198.51.100.11, 198.51.100.12")]})
    assert main._login_throttle_client_identity(request) == "192.0.2.10"


def test_password_reset_revokes_previous_tokens_and_refresh(auth_api):
    client, _ = auth_api
    admin = _login(client)
    previous = _login(client, "second")
    url = f"/auth/users/{previous['user']['user_id']}/password"
    assert client.put(url, headers=_headers(admin["access_token"]), json={"password": "new-test-password"}).status_code == 200
    assert client.post("/auth/refresh", headers=_headers(previous["access_token"])).status_code == 401
    assert client.get("/candidates", headers=_headers(previous["access_token"])).status_code == 401
    assert _login(client, "second", "new-test-password")["access_token"]


@pytest.mark.parametrize("operation,payload", [("active", {"is_active": False}), ("role", {"role": "viewer"})])
def test_account_changes_revoke_tokens(auth_api, operation, payload):
    client, _ = auth_api
    admin, previous = _login(client), _login(client, "second")
    url = f"/auth/users/{previous['user']['user_id']}/{operation}"
    assert client.put(url, headers=_headers(admin["access_token"]), json=payload).status_code == 200
    if operation == "active":
        assert client.put(url, headers=_headers(admin["access_token"]), json={"is_active": True}).status_code == 200
    assert client.post("/auth/refresh", headers=_headers(previous["access_token"])).status_code == 401


def test_refresh_preserves_login_identity_but_new_login_does_not(auth_api):
    client, _ = auth_api
    first = _login(client)["access_token"]
    response = client.post("/auth/refresh", headers=_headers(first))
    assert response.status_code == 200
    claims = jwt.get_unverified_claims(first)
    refreshed = jwt.get_unverified_claims(response.json()["access_token"])
    assert claims["sid"] == refreshed["sid"]
    assert claims["ver"] == refreshed["ver"]
    assert jwt.get_unverified_claims(_login(client)["access_token"])["sid"] != claims["sid"]


def test_legacy_token_requires_new_login(auth_api):
    client, _ = auth_api
    user = _login(client)["user"]
    token = jwt.encode({"sub": str(user["user_id"]), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                       main.JWT_SECRET_KEY, algorithm=main.JWT_ALGORITHM)
    assert client.post("/auth/refresh", headers=_headers(token)).status_code == 401


@pytest.mark.parametrize("password", ["", "       ", "short", "x" * 1025])
def test_creation_and_reset_reject_weak_or_unbounded_password(auth_api, password):
    client, _ = auth_api
    admin = _login(client)
    headers = _headers(admin["access_token"])
    response = client.post("/auth/register", headers=headers, json={"username": "new-person", "password": password})
    assert response.status_code in {400, 422}
    response = client.put(f"/auth/users/{admin['user']['user_id']}/password", headers=headers, json={"password": password})
    assert response.status_code in {400, 422}


def test_production_rejects_default_auth_configuration(monkeypatch):
    monkeypatch.setenv("MANISOV_ENV", "production")
    monkeypatch.setattr(main, "JWT_SECRET_KEY", "change-me-in-production")
    with pytest.raises(RuntimeError):
        main._validate_production_auth()
    monkeypatch.setattr(main, "JWT_SECRET_KEY", "synthetic-secret-" * 3)
    monkeypatch.setenv("JWT_SECRET_KEY", "synthetic-secret-" * 3)
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    with pytest.raises(RuntimeError):
        main._validate_production_auth()
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "synthetic-test-password")
    main._validate_production_auth()


def test_throttle_state_is_bounded_and_expires(monkeypatch):
    monkeypatch.setattr(main, "LOGIN_TRACKED_KEYS_LIMIT", 2)
    request = Request({"type": "http", "client": ("192.0.2.10", 1234), "headers": []})
    main._login_throttle_record_failure(request, "one")
    main._login_throttle_record_failure(request, "two")
    with pytest.raises(HTTPException) as error:
        main._login_throttle_record_failure(request, "three")
    assert error.value.status_code == 429
    assert len(main._LOGIN_LAST_ATTEMPT) == 2
    main._login_throttle_apply_expired_unlocks(main.time.time() + main.LOGIN_LOCKOUT_SECONDS + 1)
    assert not main._LOGIN_LAST_ATTEMPT
    assert not main._LOGIN_FAIL_COUNT


def test_development_bootstrap_uses_valid_password(monkeypatch):
    monkeypatch.delenv("MANISOV_ENV", raising=False)
    monkeypatch.delenv("DEFAULT_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("DEFAULT_ADMIN_PASSWORD", raising=False)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with sessionmaker(engine)() as db:
            main._ensure_default_auth_data(db)
            user = db.query(User).filter_by(username="admin").one()
            assert main._verify_password("admin12345", user.password_hash)
            assert user.auth_version
            original_hash = user.password_hash
            monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "admin123")
            main._ensure_default_auth_data(db)
            assert user.password_hash == original_hash
    finally:
        engine.dispose()
