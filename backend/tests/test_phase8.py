from datetime import date

import json
import pymupdf
from sqlalchemy import select

from app.models import (
    ApplicationRecord,
    AuditEvent,
    DocumentCorrection,
    DocumentMetadata,
    DocumentCorrectionExtraction,
    RegulatoryRule,
    RegulatorySource,
    RegulatorySourcePassage,
    ReviewerDecision,
    UserRole,
    ValidationFinding,
    ValidationRun,
    ValidationRunResult,
    VerificationRecord,
    new_id,
)


def token_for(client, email):
    response = client.post("/api/auth/login", json={
        "email": email, "password": "a-long-test-password-123"
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_application(client, headers, reference):
    response = client.post("/api/applications", headers=headers, json={
        "institution_id": "INST-P8",
        "institution_name": "Phase Eight Institute",
        "category": "Extension of Approval",
        "reference_number": reference,
    })
    assert response.status_code == 201
    return response.json()["id"]


def source_and_field_rule(client, application_id):
    source_id, passage_id = new_id(), new_id()
    with client.app.state.session_factory() as db:
        source = RegulatorySource(
            id=source_id,
            title="Synthetic Phase 8 Rule Source",
            issuing_authority="Synthetic Authority",
            document_version="1",
            retrieval_date=date.today(),
            status="verified",
            registered_by="rules@example.test",
        )
        db.add(source)
        db.flush()
        passage = RegulatorySourcePassage(
            id=passage_id,
            source_id=source_id,
            page_number=1,
            text="The institution shall include its institution ID.",
        )
        db.add(passage)
        db.flush()
        rule = RegulatoryRule(
            rule_id=f"P8-{new_id()[:8]}",
            version=1,
            source_id=source_id,
            source_version="1",
            source_passage_id=passage_id,
            rule_title="Include institution ID",
            supporting_quotation="The institution shall include its institution ID.",
            page_number=1,
            application_category="Extension of Approval",
            requirement="Include institution ID.",
            conditions=[],
            required_evidence="Affiliation certificate",
            validation_type="presence",
            validation_parameters={"document_category": "affiliation_certificate", "field": "institution_id"},
            status="active",
            created_by="rules@example.test",
        )
        db.add(rule)
        db.commit()
        return rule.rule_id


def create_pdf(text):
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


class CorrectedDocumentProvider:
    name = "synthetic-phase8-provider"
    model = "test-model"

    async def generate_json(self, system_prompt, user_content):
        return json.dumps({
            "institution_id": {
                "value": "INST-P8",
                "evidence": "Institution ID: INST-P8",
                "page_number": 1,
                "confidence": 0.95,
            }
        })


class EmptyProvider:
    name = "empty"
    model = "test"

    async def generate_json(self, system_prompt, user_content):
        return "{}"


def test_official_review_decision_history_and_applicant_restrictions(client, applicant_headers, user_factory):
    application_id = create_application(client, applicant_headers, "P8-DECISION-1")
    with client.app.state.session_factory() as db:
        finding = ValidationFinding(
            application_id=application_id,
            finding_key="p8-review-finding",
            rule_id="P8-RULE-1",
            rule_name="Synthetic review finding",
            severity="Medium",
            target="institution_id",
            expected="INST-P8",
            actual="INST-WRONG",
            message="Conflicting synthetic values.",
            recommendation="Review evidence.",
            evidence_json=[{"document_id": "DOC-SYNTHETIC", "page_number": 2, "evidence": "INST-WRONG"}],
        )
        db.add(finding)
        db.commit()
        finding_id = finding.id

    user_factory(email="phase8-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    reviewer_headers = token_for(client, "phase8-reviewer@example.test")
    endpoint = f"/api/applications/{application_id}/findings/{finding_id}/reviews"

    assert client.post(endpoint, headers=applicant_headers, json={
        "decision": "dismissed_finding", "reason": "Applicant cannot decide this."
    }).status_code == 403
    assert client.get(f"/api/applications/{application_id}/findings", headers=reviewer_headers).status_code == 200
    confirmed = client.post(endpoint, headers=reviewer_headers, json={
        "decision": "confirmed_issue", "reason": "Evidence supports the issue."
    })
    dismissed = client.post(endpoint, headers=reviewer_headers, json={
        "decision": "dismissed_finding", "reason": "Corrected by the institution and checked."
    })
    assert confirmed.status_code == dismissed.status_code == 201
    assert confirmed.json()["actor"] == "phase8-reviewer@example.test"
    assert confirmed.json()["created_at"]
    history = client.get(endpoint, headers=applicant_headers)
    assert [item["decision"] for item in history.json()] == ["confirmed_issue", "dismissed_finding"]
    with client.app.state.session_factory() as db:
        record = db.get(ValidationFinding, finding_id)
        decisions = db.scalars(select(ReviewerDecision).where(ReviewerDecision.finding_id == finding_id)).all()
        assert record.status == "Resolved"
        assert record.resolution_type == "dismissed_by_reviewer"
        assert len(decisions) == 2


def test_correction_upload_and_revalidation_classify_new_persistent_and_resolved_findings(client, applicant_headers):
    application_id = create_application(client, applicant_headers, "P8-CORRECT-1")
    source_and_field_rule(client, application_id)
    original = client.post(
        f"/api/applications/{application_id}/documents",
        headers=applicant_headers,
        data={"category": "affiliation_certificate"},
        files={"file": ("affiliation.pdf", create_pdf("Institution ID missing"), "application/pdf")},
    )
    assert original.status_code == 201
    run_url = f"/api/applications/{application_id}/validation-runs"
    first = client.post(run_url, headers=applicant_headers).json()
    first_result = first["results"][0]
    assert first_result["result_status"] == "unable_to_verify"
    assert first_result["revalidation_state"] == "newly_detected"
    finding_id = first_result["finding_id"]

    persistent = client.post(run_url, headers=applicant_headers).json()
    assert persistent["results"][0]["finding_id"] == finding_id
    assert persistent["results"][0]["revalidation_state"] == "persistent"

    correction = client.post(
        f"/api/applications/{application_id}/documents/{original.json()['id']}/corrections",
        headers=applicant_headers,
        files={"file": ("affiliation-corrected.pdf", create_pdf("Institution ID: INST-P8"), "application/pdf")},
    )
    assert correction.status_code == 201
    assert correction.json()["version"] == 1
    client.app.state.llm_provider = CorrectedDocumentProvider()
    extraction = client.post(
        f"/api/applications/{application_id}/documents/{original.json()['id']}/corrections/"
        f"{correction.json()['id']}/structured-extraction",
        headers=applicant_headers,
    )
    assert extraction.status_code == 201
    resolved = client.post(run_url, headers=applicant_headers).json()
    result = next(item for item in resolved["results"] if item["rule_id"] == first_result["rule_id"])
    assert result["result_status"] == "pass"
    assert result["revalidation_state"] == "resolved_by_new_evidence"
    assert result["finding_id"] == finding_id
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(ValidationRun).where(ValidationRun.application_id == application_id)).all()) == 3
        finding = db.get(ValidationFinding, finding_id)
        assert finding.status == "Resolved"
        assert finding.resolution_type == "resolved_by_new_evidence"
        runs = db.scalars(select(ValidationRunResult).where(ValidationRunResult.finding_id == finding_id)).all()
        assert len(runs) == 3
        assert runs[-1].evidence_json[0]["page_number"] == 1


def test_audit_history_and_report_include_decisions_evidence_mock_and_disclaimer(client, applicant_headers, user_factory):
    application_id = create_application(client, applicant_headers, "P8-REPORT-1")
    source_id, passage_id, rule_id = new_id(), new_id(), "REPORT-RULE"
    with client.app.state.session_factory() as db:
        application = db.get(ApplicationRecord, application_id)
        application.is_synthetic = True
        source = RegulatorySource(
            id=source_id, title="Synthetic report source", issuing_authority="Synthetic Authority",
            document_version="report-v1", retrieval_date=date.today(), status="verified",
            registered_by="rules@example.test",
        )
        db.add(source)
        db.flush()
        passage = RegulatorySourcePassage(
            id=passage_id, source_id=source_id, page_number=4, text="Report source requirement."
        )
        db.add(passage)
        db.flush()
        db.add(RegulatoryRule(
            rule_id=rule_id, version=1, source_id=source_id, source_version="report-v1",
            source_passage_id=passage_id, rule_title="Report requirement",
            supporting_quotation="Report source requirement.", page_number=4,
            application_category="Extension of Approval", requirement="Manual evidence review.",
            conditions=[], required_evidence="Certificate", validation_type="manual_review",
            validation_parameters={}, status="active", created_by="rules@example.test",
        ))
        db.add(VerificationRecord(
            application_id=application_id, status="Source Unavailable", checked_at=__import__("app.models", fromlist=["utc_now"]).utc_now(),
            message="Mock issuer unavailable.", provider="mock-issuer", is_mock=True,
        ))
        db.commit()
    run = client.post(f"/api/applications/{application_id}/validation-runs", headers=applicant_headers)
    assert run.status_code == 201
    finding_id = run.json()["results"][0]["finding_id"]
    user_factory(email="report-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    reviewer_headers = token_for(client, "report-reviewer@example.test")
    decision = client.post(
        f"/api/applications/{application_id}/findings/{finding_id}/reviews",
        headers=reviewer_headers,
        json={"decision": "clarification_required", "reason": "Please provide a clearer copy."},
    )
    assert decision.status_code == 201

    report = client.get(f"/api/applications/{application_id}/report", headers=applicant_headers)
    assert report.status_code == 200
    body = report.json()
    assert body["report_type"] == "prototype_review_support"
    assert "not an official AICTE decision" in body["disclaimer"]
    assert body["synthetic_data"] is True
    assert body["mock_verification_present"] is True
    assert body["verification_status"][0]["is_mock"] is True
    assert body["applicable_rule_references"][0]["page_number"] == 4
    assert body["latest_validation_run"]["results"][0]["status"] == "Manual Review Required"
    assert body["reviewer_decisions"][0]["decision"] == "clarification_required"

    audit = client.get(f"/api/applications/{application_id}/audit-history", headers=applicant_headers)
    assert audit.status_code == 200
    assert any(item["event_type"] == "validation_run_completed" for item in audit.json())
    assert any(item["event_type"] == "audit_log" and "Official finding decision" in item["details"]["action"] for item in audit.json())
    manager_user = "phase8-audit-manager@example.test"
    user_factory(email=manager_user, role=UserRole.RULES_MANAGER.value)
    manager_headers = token_for(client, manager_user)
    global_audit = client.get("/api/audit-history", headers=manager_headers)
    assert global_audit.status_code == 200
    assert any(item["event_type"] == "regulatory_rule_proposed" for item in global_audit.json()) is False
    assert client.get("/api/audit-history", headers=applicant_headers).status_code == 403
