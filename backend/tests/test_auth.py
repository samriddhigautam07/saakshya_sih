from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.config import Settings
from app.main import create_app
from app.models import User, UserRole, ValidationFinding


PASSWORD = "a-long-test-password-123"


def login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def bearer(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_returns_short_lived_bearer_and_me(client, user_factory):
    user_factory(email="member@example.test")

    response = login(client, "MEMBER@example.test")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["user"]["email"] == "member@example.test"
    assert "password" not in body["user"]
    me = client.get("/api/auth/me", headers=bearer(response))
    assert me.status_code == 200
    assert me.json()["role"] == UserRole.APPLICANT.value


def test_invalid_credentials_use_generic_401(client, user_factory):
    user_factory(email="member@example.test")

    bad_password = login(client, "member@example.test", "wrong-password")
    unknown_email = login(client, "unknown@example.test", "wrong-password")

    assert bad_password.status_code == unknown_email.status_code == 401
    assert bad_password.json()["detail"] == unknown_email.json()["detail"]


def test_malformed_stored_password_hash_fails_closed(client, user_factory):
    user_id = user_factory(email="bad-hash@example.test")
    with client.app.state.session_factory() as session:
        user = session.get(User, user_id)
        user.password_hash = "not-a-valid-password-hash"
        session.commit()

    response = login(client, "bad-hash@example.test")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_inactive_user_cannot_login_or_use_existing_token(client, user_factory):
    user_id = user_factory(email="inactive@example.test")
    token = login(client, "inactive@example.test")
    factory = client.app.state.session_factory
    with factory() as session:
        user = session.get(User, user_id)
        user.is_active = False
        session.commit()

    response = login(client, "inactive@example.test")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_invalid_bearer_token_returns_401(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_application_api_requires_authentication(client):
    assert client.get("/api/applications").status_code == 401


def test_server_refuses_to_start_without_jwt_secret(tmp_path):
    # Ignore any developer-local .env so this test really exercises missing-secret startup.
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'no-secret.db'}", _env_file=None))

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        from fastapi.testclient import TestClient

        with TestClient(app):
            pass


def test_public_self_registration_is_not_available(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "self@example.test", "password": PASSWORD, "role": UserRole.RULES_MANAGER.value},
    )
    assert response.status_code == 404


def test_role_guard_rejects_applicant_from_rules_manager_actions():
    guard = require_roles(UserRole.RULES_MANAGER)
    applicant = SimpleNamespace(role=UserRole.APPLICANT.value)

    with pytest.raises(HTTPException) as error:
        guard(current_user=applicant)

    assert error.value.status_code == 403


def test_applicant_cannot_access_another_users_application(client, user_factory):
    owner_id = user_factory(email="owner@example.test")
    other_id = user_factory(email="other@example.test")
    owner_token = login(client, "owner@example.test")
    other_token = login(client, "other@example.test")
    created = client.post("/api/applications", json={"institution_name": "Owned"}, headers=bearer(owner_token)).json()
    other_headers = bearer(other_token)

    assert created["owner_user_id"] == owner_id
    assert client.get(f"/api/applications/{created['id']}", headers=other_headers).status_code == 404
    assert client.patch(
        f"/api/applications/{created['id']}",
        json={"institution_name": "Hijacked"},
        headers=other_headers,
    ).status_code == 404
    assert client.get("/api/applications", headers=other_headers).json() == []


def test_official_reviewer_can_read_all_but_only_reviewer_can_record_decision(client, user_factory):
    user_factory(email="applicant@example.test")
    user_factory(email="reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    user_factory(email="rules@example.test", role=UserRole.RULES_MANAGER.value)
    applicant_token = login(client, "applicant@example.test")
    reviewer_token = login(client, "reviewer@example.test")
    rules_token = login(client, "rules@example.test")
    created = client.post(
        "/api/applications", json={"institution_name": "Review Target"}, headers=bearer(applicant_token)
    ).json()

    factory = client.app.state.session_factory
    with factory() as session:  # type: Session
        finding = ValidationFinding(
            id="finding-review-test",
            application_id=created["id"],
            finding_key="R1:institution_id",
            rule_id="R1",
            rule_name="Missing mandatory field",
            severity="High",
            target="Institution ID",
            message="Required value missing.",
            recommendation="Request the missing value.",
        )
        session.add(finding)
        session.commit()

    assert len(client.get("/api/applications", headers=bearer(reviewer_token)).json()) == 1
    decision_url = f"/api/applications/{created['id']}/decisions"
    payload = {"finding_id": "finding-review-test", "status": "Under Review", "note": "Checked evidence."}
    assert client.post(decision_url, json=payload, headers=bearer(applicant_token)).status_code == 403
    assert client.post(decision_url, json=payload, headers=bearer(rules_token)).status_code == 403
    invalid_resolution = {**payload, "status": "Resolved", "note": "  "}
    assert client.post(
        decision_url, json=invalid_resolution, headers=bearer(reviewer_token)
    ).status_code == 422

    decision = client.post(decision_url, json=payload, headers=bearer(reviewer_token))
    assert decision.status_code == 201
    assert decision.json()["actor"] == "reviewer@example.test"


def test_rules_manager_can_use_only_explicit_rules_manager_guard():
    guard = require_roles(UserRole.RULES_MANAGER)
    manager = SimpleNamespace(role=UserRole.RULES_MANAGER.value)
    assert guard(current_user=manager) is manager
