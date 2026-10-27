import json
import asyncio
import logging
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from conftest import TEST_JWT_SECRET
from app.config import Settings
from app.main import create_app
from app.models import UserRole
from app.structured_extraction import OpenAICompatibleProvider, StructuredDocumentExtractionService, configured_provider


class FakeProvider:
    name = "fake"
    model = "deterministic-test-model"

    def __init__(self, response):
        self.response = response
        self.system_prompt = None

    async def generate_json(self, system_prompt, user_content):
        self.system_prompt = system_prompt
        assert "UNTRUSTED_DOCUMENT_TEXT_JSON" in user_content
        return self.response


def mocked_provider_service(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_async_client(transport=transport, **kwargs))
    provider = OpenAICompatibleProvider(
        api_key="mock-only-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-3.8-flash",
        timeout_seconds=30,
    )
    return StructuredDocumentExtractionService(provider, 50_000)


def test_provider_configuration_is_optional_when_required_settings_are_missing(monkeypatch):
    for name in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert configured_provider(Settings(_env_file=None)) is None
    assert configured_provider(Settings(_env_file=None, llm_api_key=SecretStr("dummy-only"))) is None
    assert configured_provider(Settings(_env_file=None, llm_model="gemini-3.8-flash")) is None


def test_provider_configuration_loads_exact_names_from_an_env_file(tmp_path, monkeypatch):
    for name in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_API_KEY=dummy-test-credential\n"
        "LLM_MODEL=gemini-3.8-flash\n"
        "LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/\n"
    )

    settings = Settings(_env_file=env_file)
    provider = configured_provider(settings)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "gemini-3.8-flash"
    assert Path(Settings.model_config["env_file"]) == Path(__file__).resolve().parents[1] / ".env"


def test_startup_diagnostic_logs_presence_flags_without_secret_values(tmp_path, caplog):
    dummy_credential = "dummy-startup-credential"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'startup-diagnostic.db'}",
        jwt_secret_key=TEST_JWT_SECRET,
        document_storage_dir=tmp_path / "private-documents",
        llm_api_key=SecretStr(dummy_credential),
        llm_model="gemini-3.8-flash",
        llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    app = create_app(settings)

    with caplog.at_level(logging.INFO, logger="verifywise"):
        with TestClient(app):
            pass

    messages = [record.getMessage() for record in caplog.records if "Structured extraction configuration" in record.getMessage()]
    assert messages == ["Structured extraction configuration: LLM_API_KEY_present=True LLM_MODEL_present=True provider_ready=True"]
    assert dummy_credential not in caplog.text


def test_gemini_openai_compatible_provider_uses_mocked_chat_completion(monkeypatch):
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"uncertainty": []})}}]})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_async_client(transport=transport, **kwargs))
    settings = Settings(
        _env_file=None,
        llm_api_key=SecretStr("mock-only-key"),
        llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        llm_model="gemini-3.8-flash",
    )
    provider = configured_provider(settings)

    assert isinstance(provider, OpenAICompatibleProvider)
    result = asyncio.run(provider.generate_json("system instruction", "document content"))

    assert json.loads(result) == {"uncertainty": []}
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert captured["authorization"] == "Bearer mock-only-key"
    assert captured["payload"]["model"] == "gemini-3.8-flash"
    assert captured["payload"]["reasoning_effort"] == "low"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["messages"] == [
        {"role": "system", "content": "system instruction"},
        {"role": "user", "content": "document content"},
    ]


def test_upstream_http_failure_reports_only_status_not_response_body():
    class RejectedProvider:
        name = "mock"
        model = "mock-model"

        async def generate_json(self, _system_prompt, _user_content):
            request = httpx.Request("POST", "https://provider.invalid/chat/completions")
            response = httpx.Response(401, request=request, json={"error": {"message": "private provider detail"}})
            raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    from app.structured_extraction import StructuredDocumentExtractionService

    outcome = asyncio.run(StructuredDocumentExtractionService(RejectedProvider(), 5000).extract("page text", "certificate"))

    assert outcome.status == "provider_error"
    assert "HTTP 401" in (outcome.error_message or "")
    assert "private provider detail" not in (outcome.error_message or "")


def test_http_503_retries_once_then_reports_transient_availability(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503, request=request, json={"error": {"message": "upstream details are not exposed"}})

    service = mocked_provider_service(monkeypatch, handler)
    outcome = asyncio.run(service.extract("[Page 1 | Digital]\nExample content", "certificate"))

    assert len(requests) == 2
    assert outcome.status == "provider_error"
    assert "HTTP 503" in (outcome.error_message or "")
    assert "temporarily unavailable" in (outcome.error_message or "")
    assert "upstream details" not in (outcome.error_message or "")


def test_timeout_is_distinguished_and_not_retried(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("mock timeout", request=request)

    service = mocked_provider_service(monkeypatch, handler)
    outcome = asyncio.run(service.extract("[Page 1 | Digital]\nExample content", "certificate"))

    assert len(requests) == 1
    assert outcome.status == "provider_error"
    assert "timed out" in (outcome.error_message or "")


@pytest.mark.parametrize(
    ("status_code", "message_fragment"),
    [
        (401, "rejected authentication"),
        (402, "requires billing"),
        (403, "not permitted"),
        (404, "endpoint or model was not found"),
        (429, "rate or quota limit"),
    ],
)
def test_auth_billing_permission_model_and_quota_errors_are_distinguished(monkeypatch, status_code, message_fragment):
    def handler(request):
        return httpx.Response(status_code, request=request, json={"error": {"message": "private provider response"}})

    service = mocked_provider_service(monkeypatch, handler)
    outcome = asyncio.run(service.extract("[Page 1 | Digital]\nExample content", "certificate"))

    assert outcome.status == "provider_error"
    assert message_fragment in (outcome.error_message or "")
    assert "private provider response" not in (outcome.error_message or "")


def test_successful_mocked_gemini_structured_response_is_validated(monkeypatch):
    document_text = "[Page 1 | Digital]\nInstitution Name: Example Institute"
    generated = {
        "institution_name": {
            "value": "Example Institute",
            "evidence": "Institution Name: Example Institute",
            "page_number": 1,
            "confidence": 0.95,
        },
        "uncertainty": ["Document reference number was not present."],
    }
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, request=request, json={"choices": [{"message": {"content": json.dumps(generated)}}]})

    service = mocked_provider_service(monkeypatch, handler)
    outcome = asyncio.run(service.extract(document_text, "affiliation_certificate"))

    assert len(requests) == 1
    assert outcome.status == "uncertain"
    assert outcome.result is not None
    assert outcome.result.institution_name.value == "Example Institute"
    assert outcome.result.institution_name.page_number == 1


def create_app_and_document(client, headers, pdf_bytes):
    application_response = client.post(
        "/api/applications",
        json={"institution_name": "Extraction Test Institute", "reference_number": "STRUCT-APP-1"},
        headers=headers,
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["id"]
    upload_response = client.post(
        f"/api/applications/{application_id}/documents",
        data={"category": "fire_safety"},
        files={"file": ("certificate.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert upload_response.status_code == 201
    return application_id, upload_response.json()["id"]


def extraction_url(application_id, document_id):
    return f"/api/applications/{application_id}/documents/{document_id}/structured-extraction"


def test_valid_structured_extraction_validates_and_persists_evidence(client, applicant_headers, pdf_bytes):
    application_id, document_id = create_app_and_document(client, applicant_headers, pdf_bytes)
    provider = FakeProvider(json.dumps({
        "institution_name": {
            "value": "Synthetic PDF extraction test",
            "evidence": "Synthetic PDF extraction test",
            "confidence": 0.91,
        },
        "document_reference_number": {},
        "issue_date": {},
        "expiry_date": {},
    }))
    client.app.state.llm_provider = provider

    response = client.post(extraction_url(application_id, document_id), headers=applicant_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "partial"
    assert body["result"]["institution_name"]["value"] == "Synthetic PDF extraction test"
    assert body["result"]["institution_name"]["page_number"] == 1
    assert "untrusted" in provider.system_prompt.lower()
    listed = client.get(
        f"/api/applications/{application_id}/documents/{document_id}/structured-extractions",
        headers=applicant_headers,
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]


def test_malformed_model_output_is_recorded_as_invalid(client, applicant_headers, pdf_bytes):
    application_id, document_id = create_app_and_document(client, applicant_headers, pdf_bytes)
    client.app.state.llm_provider = FakeProvider("not json")

    response = client.post(extraction_url(application_id, document_id), headers=applicant_headers)

    assert response.status_code == 201
    assert response.json()["status"] == "invalid_output"
    assert response.json()["result"] is None


def test_missing_fields_are_null_and_not_invented(client, applicant_headers, pdf_bytes):
    application_id, document_id = create_app_and_document(client, applicant_headers, pdf_bytes)
    client.app.state.llm_provider = FakeProvider(json.dumps({"uncertainty": ["Reference number is absent."]}))

    response = client.post(extraction_url(application_id, document_id), headers=applicant_headers)

    assert response.status_code == 201
    assert response.json()["status"] == "no_fields_found"
    assert response.json()["result"]["document_reference_number"]["value"] is None


def test_fabricated_evidence_is_rejected(client, applicant_headers, pdf_bytes):
    application_id, document_id = create_app_and_document(client, applicant_headers, pdf_bytes)
    client.app.state.llm_provider = FakeProvider(json.dumps({
        "institution_name": {"value": "Invented College", "evidence": "Invented College", "page_number": 1}
    }))

    response = client.post(extraction_url(application_id, document_id), headers=applicant_headers)

    assert response.status_code == 201
    assert response.json()["status"] == "invalid_evidence"
    assert response.json()["result"] is None


def test_unconfigured_provider_does_not_break_app_and_reports_status(client, applicant_headers, pdf_bytes):
    application_id, document_id = create_app_and_document(client, applicant_headers, pdf_bytes)

    assert client.get("/health").status_code == 200
    response = client.post(extraction_url(application_id, document_id), headers=applicant_headers)

    assert response.status_code == 201
    assert response.json()["status"] == "provider_unavailable"
    assert "LLM_API_KEY" in response.json()["error_message"]


def test_empty_extracted_text_is_reported_without_calling_configured_provider(client, applicant_headers):
    application_response = client.post(
        "/api/applications",
        json={"institution_name": "Empty Text Institute", "reference_number": "EMPTY-TEXT-1"},
        headers=applicant_headers,
    )
    application_id = application_response.json()["id"]
    upload_response = client.post(
        f"/api/applications/{application_id}/documents",
        data={"category": "fire_safety"},
        files={"file": ("corrupt.pdf", b"%PDF-1.7 not a valid pdf", "application/pdf")},
        headers=applicant_headers,
    )
    assert upload_response.status_code == 201
    assert upload_response.json()["extracted_text_char_count"] == 0
    provider = FakeProvider("{}")
    client.app.state.llm_provider = provider

    response = client.post(extraction_url(application_id, upload_response.json()["id"]), headers=applicant_headers)

    assert response.status_code == 201
    assert response.json()["status"] == "no_text"
    assert response.json()["error_message"] == "No extracted document text is available."
    assert provider.system_prompt is None


def test_extraction_enforces_document_authorization(client, applicant_headers, user_factory, pdf_bytes):
    application_id, document_id = create_app_and_document(client, applicant_headers, pdf_bytes)
    user_factory(email="another-extractor@example.test")
    login = client.post("/api/auth/login", json={
        "email": "another-extractor@example.test", "password": "a-long-test-password-123"
    })
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    user_factory(email="extract-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    reviewer_login = client.post("/api/auth/login", json={
        "email": "extract-reviewer@example.test", "password": "a-long-test-password-123"
    })
    reviewer_headers = {"Authorization": f"Bearer {reviewer_login.json()['access_token']}"}
    client.app.state.llm_provider = FakeProvider("{}")

    assert client.post(extraction_url(application_id, document_id)).status_code == 401
    assert client.post(extraction_url(application_id, document_id), headers=other_headers).status_code == 404
    assert client.post(extraction_url(application_id, document_id), headers=reviewer_headers).status_code == 201
