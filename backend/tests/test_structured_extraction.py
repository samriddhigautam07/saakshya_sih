import json

from conftest import TEST_JWT_SECRET
from app.models import UserRole


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
