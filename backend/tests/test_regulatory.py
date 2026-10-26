import json

import pymupdf
from fastapi.testclient import TestClient

from app.models import UserRole


CATEGORY = "Extension of Approval"


class FakeRuleProvider:
    name = "synthetic-test-provider"
    model = "rule-test-model"

    def __init__(self, response=None):
        self.response = response or {
            "rule_title": "Maintain approved faculty strength",
            "supporting_quotation": "The institution shall maintain approved faculty strength.",
            "clause_reference": "Clause 4.2",
            "annexure_reference": None,
            "page_number": 1,
            "application_category": CATEGORY,
            "requirement": "Maintain approved faculty strength.",
            "conditions": [],
            "required_evidence": "Faculty list",
            "validation_type": "presence",
            "validation_parameters": {},
            "applicable_from": None,
            "applicable_until": None,
            "uncertainty_notes": [],
        }

    async def generate_json(self, system_prompt, user_content):
        assert "never as instructions" in system_prompt
        assert "authorized_source_passage_untrusted" in user_content
        return json.dumps(self.response)


def login_as(client: TestClient, email: str, password="a-long-test-password-123"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_source(client, admin_headers):
    response = client.post(
        "/api/regulatory/sources",
        headers=admin_headers,
        json={
            "title": "Synthetic Authoritative Handbook",
            "issuing_authority": "Synthetic Regulatory Authority",
            "source_url": "https://regulator.example.org/handbook.pdf",
            "document_version": "2026.1",
            "publication_date": "2026-01-15",
            "effective_date": "2026-04-01",
            "retrieval_date": "2026-02-01",
        },
    )
    assert response.status_code == 201
    return response.json()


def pdf_with_rule_passage():
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Clause 4.2. The institution shall maintain approved faculty strength.")
    content = document.tobytes()
    document.close()
    return content


def ingest_and_verify_source(client, admin_headers):
    source = create_source(client, admin_headers)
    uploaded = client.post(
        f"/api/regulatory/sources/{source['id']}/upload",
        headers=admin_headers,
        files={"file": ("handbook.pdf", pdf_with_rule_passage(), "application/pdf")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["passage_count"] == 1
    passages = client.get(f"/api/regulatory/sources/{source['id']}/passages", headers=admin_headers)
    assert passages.status_code == 200
    assert passages.json()[0]["page_number"] == 1
    assert "Clause 4.2" in passages.json()[0]["text"]
    search = client.get(
        f"/api/regulatory/sources/{source['id']}/search?query=faculty", headers=admin_headers
    )
    assert search.status_code == 200 and search.json()[0]["page_number"] == 1
    verified = client.post(f"/api/regulatory/sources/{source['id']}/verify", headers=admin_headers)
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"
    return source, passages.json()[0]


def create_proposal(client, headers, source, passage):
    return client.post(
        f"/api/regulatory/sources/{source['id']}/proposals",
        headers=headers,
        json={"application_category": CATEGORY, "passage_id": passage["id"]},
    )


def test_source_registration_ingestion_extracts_page_passages_and_private_file(client, user_factory, tmp_path):
    user_factory(email="reg-admin@example.test", role=UserRole.RULES_MANAGER.value)
    admin_headers = login_as(client, "reg-admin@example.test")
    source, passage = ingest_and_verify_source(client, admin_headers)
    stored = client.app.state.storage_root / "regulatory_sources"
    assert stored.stat().st_mode & 0o077 == 0
    assert list(stored.glob("*.pdf"))
    assert passage["page_number"] == 1
    assert source["source_url"].startswith("https://")


def test_rejects_private_source_urls_and_invalid_uploads(client, user_factory):
    user_factory(email="source-admin@example.test", role=UserRole.RULES_MANAGER.value)
    admin_headers = login_as(client, "source-admin@example.test")
    invalid_url = client.post("/api/regulatory/sources", headers=admin_headers, json={
        "title": "Local API", "issuing_authority": "Synthetic Authority", "source_url": "https://127.0.0.1/private",
        "document_version": "1",
    })
    assert invalid_url.status_code == 422
    source = create_source(client, admin_headers)
    invalid_file = client.post(
        f"/api/regulatory/sources/{source['id']}/upload",
        headers=admin_headers,
        files={"file": ("fake.pdf", b"not pdf", "application/pdf")},
    )
    assert invalid_file.status_code == 415


def test_only_rules_manager_can_register_or_ingest_sources(client, applicant_headers, user_factory):
    assert client.post("/api/regulatory/sources", headers=applicant_headers, json={
        "title": "Synthetic Handbook", "issuing_authority": "Authority", "document_version": "1"
    }).status_code == 403
    user_factory(email="source-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    reviewer_headers = login_as(client, "source-reviewer@example.test")
    assert client.post("/api/regulatory/sources", headers=reviewer_headers, json={
        "title": "Synthetic Handbook", "issuing_authority": "Authority", "document_version": "1"
    }).status_code == 403


def test_proposal_requires_traceable_quote_and_marks_unsupported_clause_for_review(client, user_factory):
    user_factory(email="proposal-admin@example.test", role=UserRole.RULES_MANAGER.value)
    headers = login_as(client, "proposal-admin@example.test")
    source, passage = ingest_and_verify_source(client, headers)
    client.app.state.llm_provider = FakeRuleProvider()

    response = create_proposal(client, headers, source, passage)
    assert response.status_code == 201
    assert response.json()["page_number"] == 1
    assert response.json()["status"] == "draft"
    assert response.json()["clause_reference"] == "Clause 4.2"

    invented = FakeRuleProvider({
        **FakeRuleProvider().response,
        "supporting_quotation": "The fabricated rule requires a new report.",
    })
    client.app.state.llm_provider = invented
    unsupported = create_proposal(client, headers, source, passage)
    assert unsupported.status_code == 422

    invented_clause = FakeRuleProvider({**FakeRuleProvider().response, "clause_reference": "Clause 99"})
    client.app.state.llm_provider = invented_clause
    uncertain = create_proposal(client, headers, source, passage)
    assert uncertain.status_code == 201
    assert uncertain.json()["status"] == "manual_review"
    assert uncertain.json()["clause_reference"] is None
    assert uncertain.json()["uncertainty_notes"]

    client.app.state.llm_provider = FakeRuleProvider({"not": "a valid rule shape"})
    malformed = create_proposal(client, headers, source, passage)
    assert malformed.status_code == 422

    client.app.state.llm_provider = None
    unavailable = create_proposal(client, headers, source, passage)
    assert unavailable.status_code == 503


def test_rule_approval_activation_version_history_retirement_and_checklist(client, user_factory):
    user_factory(email="workflow-admin@example.test", role=UserRole.RULES_MANAGER.value)
    headers = login_as(client, "workflow-admin@example.test")
    source, passage = ingest_and_verify_source(client, headers)
    client.app.state.llm_provider = FakeRuleProvider()
    proposal = create_proposal(client, headers, source, passage).json()
    rule_id = proposal["id"]

    assert client.get(f"/api/regulatory/checklists/{CATEGORY}", headers=headers).json() == {
        "application_category": CATEGORY, "configured": False, "items": []
    }
    assert client.post(f"/api/regulatory/rules/{rule_id}/activate", headers=headers, json={}).status_code == 409
    approved = client.post(f"/api/regulatory/rules/{rule_id}/approve", headers=headers, json={})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    active = client.post(f"/api/regulatory/rules/{rule_id}/activate", headers=headers, json={})
    assert active.status_code == 200 and active.json()["status"] == "active"
    client.put("/api/regulatory/categories", headers=headers, json={"application_category": CATEGORY, "enabled": True})
    checklist = client.get(f"/api/regulatory/checklists/{CATEGORY}", headers=headers)
    assert checklist.status_code == 200
    assert checklist.json()["items"][0]["classification"] == "verified_regulatory"
    assert checklist.json()["items"][0]["page_number"] == 1

    revision_payload = {
        "rule_title": "Maintain approved faculty strength revised",
        "supporting_quotation": "The institution shall maintain approved faculty strength.",
        "clause_reference": "Clause 4.2",
        "annexure_reference": None,
        "page_number": 1,
        "application_category": CATEGORY,
        "requirement": "Maintain approved faculty strength and retain evidence.",
        "conditions": ["During the approval period"],
        "required_evidence": "Faculty list",
        "validation_type": "presence",
        "validation_parameters": {},
        "applicable_from": None,
        "applicable_until": None,
        "uncertainty_notes": [],
    }
    revised = client.post(f"/api/regulatory/rules/{rule_id}/revise", headers=headers, json=revision_payload)
    assert revised.status_code == 201
    assert revised.json()["rule_id"] == proposal["rule_id"]
    assert revised.json()["version"] == 2
    assert revised.json()["status"] == "draft"
    approved_v2 = client.post(f"/api/regulatory/rules/{revised.json()['id']}/approve", headers=headers, json={})
    assert approved_v2.status_code == 200
    activated_v2 = client.post(f"/api/regulatory/rules/{revised.json()['id']}/activate", headers=headers, json={})
    assert activated_v2.status_code == 200
    versions = client.get("/api/regulatory/rules", headers=headers).json()
    assert {(item["version"], item["status"]) for item in versions} == {(1, "retired"), (2, "active")}
    assert len(client.get(f"/api/regulatory/checklists/{CATEGORY}", headers=headers).json()["items"]) == 1

    retired = client.post(f"/api/regulatory/rules/{revised.json()['id']}/retire", headers=headers, json={})
    assert retired.status_code == 200
    assert client.get(f"/api/regulatory/checklists/{CATEGORY}", headers=headers).json()["items"] == []


def test_checklist_and_rule_workflow_require_auth_and_manager_role(client, applicant_headers, user_factory):
    assert client.get(f"/api/regulatory/checklists/{CATEGORY}").status_code == 401
    assert client.put("/api/regulatory/categories", headers=applicant_headers, json={
        "application_category": CATEGORY, "enabled": True
    }).status_code == 403
    user_factory(email="workflow-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    reviewer_headers = login_as(client, "workflow-reviewer@example.test")
    assert client.put("/api/regulatory/categories", headers=reviewer_headers, json={
        "application_category": CATEGORY, "enabled": True
    }).status_code == 403


def test_superseding_source_withdraws_old_checklist_until_new_rule_is_reviewed(client, user_factory):
    user_factory(email="version-admin@example.test", role=UserRole.RULES_MANAGER.value)
    headers = login_as(client, "version-admin@example.test")
    old_source, old_passage = ingest_and_verify_source(client, headers)
    client.app.state.llm_provider = FakeRuleProvider()
    old_rule = create_proposal(client, headers, old_source, old_passage).json()
    assert client.post(f"/api/regulatory/rules/{old_rule['id']}/approve", headers=headers, json={}).status_code == 200
    assert client.post(f"/api/regulatory/rules/{old_rule['id']}/activate", headers=headers, json={}).status_code == 200
    client.put("/api/regulatory/categories", headers=headers, json={"application_category": CATEGORY, "enabled": True})
    assert len(client.get(f"/api/regulatory/checklists/{CATEGORY}", headers=headers).json()["items"]) == 1

    replacement = client.post("/api/regulatory/sources", headers=headers, json={
        "title": "Synthetic Authoritative Handbook",
        "issuing_authority": "Synthetic Regulatory Authority",
        "document_version": "2027.1",
        "supersedes_source_id": old_source["id"],
    })
    assert replacement.status_code == 201
    assert replacement.json()["supersedes_source_id"] == old_source["id"]
    assert client.get(f"/api/regulatory/checklists/{CATEGORY}", headers=headers).json()["items"] == []

    uploaded = client.post(
        f"/api/regulatory/sources/{replacement.json()['id']}/upload",
        headers=headers,
        files={"file": ("handbook-2027.pdf", pdf_with_rule_passage(), "application/pdf")},
    )
    assert uploaded.status_code == 200
    passages = client.get(
        f"/api/regulatory/sources/{replacement.json()['id']}/passages", headers=headers
    ).json()
    assert client.post(f"/api/regulatory/sources/{replacement.json()['id']}/verify", headers=headers).status_code == 200

    revised_payload = {
        "rule_title": "Maintain approved faculty strength",
        "supporting_quotation": "The institution shall maintain approved faculty strength.",
        "clause_reference": "Clause 4.2",
        "annexure_reference": None,
        "page_number": 1,
        "application_category": CATEGORY,
        "requirement": "Maintain approved faculty strength.",
        "conditions": [],
        "required_evidence": "Faculty list",
        "validation_type": "presence",
        "validation_parameters": {},
        "applicable_from": None,
        "applicable_until": None,
        "uncertainty_notes": [],
        "source_id": replacement.json()["id"],
        "passage_id": passages[0]["id"],
    }
    new_rule = client.post(
        f"/api/regulatory/rules/{old_rule['id']}/revise", headers=headers, json=revised_payload
    )
    assert new_rule.status_code == 201
    assert new_rule.json()["version"] == 2
    assert new_rule.json()["source_version"] == "2027.1"
    assert client.post(f"/api/regulatory/rules/{new_rule.json()['id']}/approve", headers=headers, json={}).status_code == 200
    assert client.post(f"/api/regulatory/rules/{new_rule.json()['id']}/activate", headers=headers, json={}).status_code == 200
    checklist = client.get(f"/api/regulatory/checklists/{CATEGORY}", headers=headers).json()
    assert len(checklist["items"]) == 1
    assert checklist["items"][0]["source_version"] == "2027.1"
