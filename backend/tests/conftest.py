import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import User
from app.security import hash_password

TEST_JWT_SECRET = "test-only-secret-key-with-more-than-32-characters"


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "applications-test.db"
    app = create_app(
        Settings(
            database_url=f"sqlite:///{database_path}",
            jwt_secret_key=TEST_JWT_SECRET,
            document_storage_dir=tmp_path / "private-documents",
        )
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_factory(client):
    def create_user(
        email="applicant@example.test",
        role="Applicant / Institution",
        active=True,
        password="a-long-test-password-123",
    ):
        factory = client.app.state.session_factory
        with factory() as session:  # type: Session
            user = User(
                email=email.lower(),
                password_hash=hash_password(password),
                role=role,
                is_active=active,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user.id

    return create_user


@pytest.fixture
def applicant_headers(client, user_factory):
    user_factory()
    response = client.post(
        "/api/auth/login",
        json={"email": "applicant@example.test", "password": "a-long-test-password-123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def pdf_bytes():
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Synthetic PDF extraction test")
    payload = document.tobytes()
    document.close()
    return payload
