from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_returns_ok(tmp_path):
    database_path = tmp_path / "health.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        jwt_secret_key="test-only-secret-key-with-more-than-32-characters",
        document_storage_dir=tmp_path / "private-documents",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert database_path.is_file()


def test_configured_frontend_origin_can_send_bearer_preflight(tmp_path):
    app = create_app(Settings(
        database_url=f"sqlite:///{tmp_path / 'cors.db'}",
        jwt_secret_key="test-only-secret-key-with-more-than-32-characters",
        document_storage_dir=tmp_path / "cors-documents",
        cors_origins="http://localhost:5173",
    ))
    with TestClient(app) as client:
        response = client.options(
            "/api/applications",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_vite_port_8080_can_read_health_with_cors(tmp_path):
    app = create_app(Settings(
        database_url=f"sqlite:///{tmp_path / 'health-cors.db'}",
        jwt_secret_key="test-only-secret-key-with-more-than-32-characters",
        document_storage_dir=tmp_path / "health-cors-documents",
    ))
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:8080"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_unconfigured_frontend_origin_is_not_allowed(tmp_path):
    app = create_app(Settings(
        database_url=f"sqlite:///{tmp_path / 'cors-deny.db'}",
        jwt_secret_key="test-only-secret-key-with-more-than-32-characters",
        document_storage_dir=tmp_path / "cors-deny-documents",
        cors_origins="http://localhost:5173",
    ))
    with TestClient(app) as client:
        response = client.options(
            "/api/applications",
            headers={
                "Origin": "https://unexpected.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert "access-control-allow-origin" not in response.headers
