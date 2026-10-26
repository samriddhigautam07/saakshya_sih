from datetime import date, timedelta
from sqlalchemy import select

from app.models import (
    ApplicationRecord,
    DocumentExtractionRecord,
    DocumentMetadata,
    InstitutionalReferenceRecord,
    RegulatoryRule,
    RegulatorySource,
    RegulatorySourcePassage,
    UserRole,
    ValidationFinding,
    ValidationRun,
    ValidationRunResult,
    new_id,
)


def create_application(client, headers, reference="VALIDATION-APP", category="Extension of Approval"):
    response = client.post("/api/applications", headers=headers, json={
        "institution_id": "INST-VAL-1",
        "institution_name": "Application Institute",
        "category": category,
        "reference_number": reference,
    })
    assert response.status_code == 201
    return response.json()["id"]


def token_for(client, email):
    response = client.post("/api/auth/login", json={
        "email": email, "password": "a-long-test-password-123"
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add_source_and_rule(
    client,
    application_category="Extension of Approval",
    validation_type="presence",
    parameters=None,
    *,
    source_status="verified",
    source_version="1.0",
    rule_source_version=None,
    rule_status="active",
    is_demo=False,
    conditions=None,
    rule_id=None,
):
    source_id = new_id()
    passage_id = new_id()
    rule_id = rule_id or f"TEST-RULE-{new_id()[:8]}"
    with client.app.state.session_factory() as db:
        source = RegulatorySource(
            id=source_id,
            title="Synthetic verified test regulation",
            issuing_authority="Synthetic Authority",
            document_version=source_version,
            retrieval_date=date.today(),
            status=source_status,
            extraction_status="text_extracted",
            registered_by="test-manager@example.test",
        )
        passage = RegulatorySourcePassage(
            id=passage_id,
            source_id=source_id,
            page_number=1,
            text="Synthetic evidence: the institution must maintain faculty records.",
        )
        rule = RegulatoryRule(
            rule_id=rule_id,
            version=1,
            source_id=source_id,
            source_version=rule_source_version or source_version,
            source_passage_id=passage_id,
            rule_title=f"Test {validation_type} rule",
            supporting_quotation="the institution must maintain faculty records",
            page_number=1,
            application_category=application_category,
            requirement=f"Test {validation_type} requirement",
            conditions=conditions or [],
            required_evidence="Synthetic evidence",
            validation_type=validation_type,
            validation_parameters=parameters or {},
            status=rule_status,
            is_demo=is_demo,
            created_by="test-manager@example.test",
        )
        db.add(source)
        db.flush()
        db.add(passage)
        db.flush()
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule.id


def add_document(client, application_id, category="faculty_list", fields=None):
    with client.app.state.session_factory() as db:
        document = DocumentMetadata(
            application_id=application_id,
            category=category,
            filename=f"{new_id()}.pdf",
            processing_status="Awaiting manual fields",
            field_source="none",
            issuer="",
            document_number="",
            institution_id_on_doc="",
            extracted_text="synthetic page-labeled extracted text",
            extraction_status="text_extracted",
        )
        db.add(document)
        db.flush()
        if fields is not None:
            result = {
                field: {
                    "value": value,
                    "evidence": evidence,
                    "page_number": page,
                    "confidence": 0.9,
                }
                for field, (value, evidence, page) in fields.items()
            }
            db.add(DocumentExtractionRecord(
                document_id=document.id,
                provider="synthetic-test-provider",
                model="test-model",
                status="partial",
                result_json=result,
            ))
        db.commit()
        db.refresh(document)
        return document.id


def run_validation(client, application_id, headers):
    return client.post(f"/api/applications/{application_id}/validation-runs", headers=headers)


def test_rule_engine_supports_presence_date_numeric_text_match_and_manual_review(client, applicant_headers):
    application_id = create_application(client, applicant_headers)
    document_id = add_document(client, application_id, "fire_safety", {
        "expiry_date": ((date.today() - timedelta(days=1)).isoformat(), "Expired 2025-01-01", 2),
        "faculty_count": (30, "Faculty count: 30", 3),
        "institution_name": ("Alpha Institute", "Alpha Institute", 1),
    })
    add_source_and_rule(client, "Extension of Approval", "presence", {"document_category": "fire_safety"}, rule_id="PRESENCE")
    add_source_and_rule(client, "Extension of Approval", "date", {
        "document_category": "fire_safety", "field": "expiry_date", "comparison": "not_expired"
    }, rule_id="DATE")
    add_source_and_rule(client, "Extension of Approval", "numeric", {
        "document_category": "fire_safety", "field": "faculty_count", "comparison": "min", "expected": 20
    }, rule_id="NUMERIC")
    add_source_and_rule(client, "Extension of Approval", "text_match", {
        "document_category": "fire_safety", "field": "institution_name", "comparison": "exact", "expected": "Alpha Institute"
    }, rule_id="TEXT")
    add_source_and_rule(client, "Extension of Approval", "manual_review", {}, rule_id="MANUAL")

    response = run_validation(client, application_id, applicant_headers)

    assert response.status_code == 201
    results = {item["rule_id"]: item for item in response.json()["results"]}
    assert results["PRESENCE"]["result_status"] == "pass"
    assert results["DATE"]["result_status"] == "mismatch"
    assert results["NUMERIC"]["result_status"] == "pass"
    assert results["TEXT"]["result_status"] == "pass"
    assert results["MANUAL"]["result_status"] == "manual_review"
    date_result = results["DATE"]
    assert date_result["document_ids_json"] == [document_id]
    assert date_result["evidence_json"][0]["page_number"] == 2
    assert response.json()["status"] == "completed_with_manual_review"


def test_missing_documents_and_fields_are_explicit_and_category_rules_are_scoped(client, applicant_headers):
    application_id = create_application(client, applicant_headers, category="New Institution")
    add_source_and_rule(client, "New Institution", "presence", {"document_category": "fire_safety"}, rule_id="MISSING-DOC")
    add_source_and_rule(client, "New Institution", "presence", {
        "document_category": "faculty_list", "field": "institution_id"
    }, rule_id="MISSING-FIELD")
    add_source_and_rule(client, "Extension of Approval", "presence", {"document_category": "land_document"}, rule_id="WRONG-CATEGORY")
    add_document(client, application_id, "faculty_list")

    response = run_validation(client, application_id, applicant_headers)

    assert response.status_code == 201
    results = {item["rule_id"]: item for item in response.json()["results"]}
    assert results["MISSING-DOC"]["result_status"] == "mismatch"
    assert results["MISSING-FIELD"]["result_status"] == "unable_to_verify"
    assert "WRONG-CATEGORY" not in results


def test_cross_document_conflicts_are_evidence_linked_and_missing_values_are_not_conflicts(client, applicant_headers):
    application_id = create_application(client, applicant_headers)
    first_id = add_document(client, application_id, "faculty_list", {
        "institution_name": ("Alpha College", "Alpha College", 1),
        "institution_id": ("INST-A", "Institution ID INST-A", 1),
        "document_reference_number": ("REF-1", "Reference REF-1", 2),
    })
    second_id = add_document(client, application_id, "fire_safety", {
        "institution_name": ("Beta College", "Beta College", 3),
        "institution_id": ("INST-B", "Institution ID INST-B", 1),
        "document_reference_number": ("REF-2", "Reference REF-2", 1),
    })
    add_document(client, application_id, "land_document")

    response = run_validation(client, application_id, applicant_headers)

    assert response.status_code == 201
    results = [item for item in response.json()["results"] if item["source_kind"] == "cross_document"]
    assert {item["rule_id"] for item in results} == {
        "cross_document.institution_name", "cross_document.institution_id",
        "cross_document.document_reference_number",
    }
    assert all(item["result_status"] == "manual_review" for item in results)
    assert all(set(item["document_ids_json"]) == {first_id, second_id} for item in results)
    assert all("not a fraud" in item["message"] for item in results)


def test_authorized_reference_record_only_is_used_for_configured_comparison(client, applicant_headers):
    application_id = create_application(client, applicant_headers)
    add_document(client, application_id, "faculty_list", {
        "faculty_count": (30, "Faculty count: 30", 4),
    })
    with client.app.state.session_factory() as db:
        db.add(InstitutionalReferenceRecord(
            institution_id="INST-VAL-1", name="Application Institute", faculty_count=35,
            source_label="synthetic trusted registry", is_authorized=False,
        ))
        db.commit()
    add_source_and_rule(client, "Extension of Approval", "numeric", {
        "document_category": "faculty_list", "field": "faculty_count", "comparison": "equals",
        "reference_record_id": "INST-VAL-1",
    }, rule_id="REFERENCE")

    unauthorized = run_validation(client, application_id, applicant_headers).json()
    result = next(item for item in unauthorized["results"] if item["rule_id"] == "REFERENCE")
    assert result["result_status"] == "unable_to_verify"
    assert not any("reference_record_id" in item for item in result["evidence_json"])

    with client.app.state.session_factory() as db:
        record = db.get(InstitutionalReferenceRecord, "INST-VAL-1")
        record.is_authorized = True
        db.commit()
    authorized = run_validation(client, application_id, applicant_headers).json()
    result = next(item for item in authorized["results"] if item["rule_id"] == "REFERENCE")
    assert result["result_status"] == "mismatch"
    assert result["expected"] == "35"
    assert result["evidence_json"][-1]["authorized"] is True


def test_only_active_verified_current_non_demo_supported_rules_execute(client, applicant_headers):
    application_id = create_application(client, applicant_headers)
    add_source_and_rule(client, rule_id="VALID-RULE", validation_type="manual_review")
    add_source_and_rule(client, rule_id="DRAFT-RULE", rule_status="draft")
    add_source_and_rule(client, rule_id="APPROVED-RULE", rule_status="approved")
    add_source_and_rule(client, rule_id="INACTIVE-SOURCE", source_status="inactive")
    add_source_and_rule(client, rule_id="SUPERSEDED-VERSION", source_version="2", rule_source_version="1")
    add_source_and_rule(client, rule_id="DEMO-RULE", is_demo=True)
    add_source_and_rule(client, rule_id="UNSUPPORTED-RULE", validation_type="execute_python")

    response = run_validation(client, application_id, applicant_headers)

    assert response.status_code == 201
    assert [item["rule_id"] for item in response.json()["results"]] == ["VALID-RULE"]
    assert response.json()["results"][0]["result_status"] == "manual_review"


def test_repeated_runs_keep_history_and_reuse_same_finding_without_resetting_review_decision(
    client, applicant_headers, user_factory
):
    application_id = create_application(client, applicant_headers)
    add_source_and_rule(client, "Extension of Approval", "presence", {"document_category": "fire_safety"}, rule_id="MISSING-FIRE")

    first = run_validation(client, application_id, applicant_headers).json()
    finding_id = first["results"][0]["finding_id"]
    user_factory(email="validation-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    reviewer_headers = token_for(client, "validation-reviewer@example.test")
    decision = client.post(f"/api/applications/{application_id}/decisions", headers=reviewer_headers, json={
        "finding_id": finding_id, "status": "Resolved", "note": "Confirmed and resolved by reviewer."
    })
    assert decision.status_code == 201

    second = run_validation(client, application_id, applicant_headers).json()

    assert second["id"] != first["id"]
    assert second["results"][0]["finding_id"] == finding_id
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(ValidationRun).where(ValidationRun.application_id == application_id)).all()) == 2
        assert len(db.scalars(select(ValidationFinding).where(ValidationFinding.application_id == application_id)).all()) == 1
        finding = db.get(ValidationFinding, finding_id)
        assert finding.status == "Resolved"
        assert len(db.scalars(select(ValidationRunResult).where(ValidationRunResult.finding_id == finding_id)).all()) == 2


def test_validation_api_enforces_owner_reviewer_and_manager_access(client, applicant_headers, user_factory):
    application_id = create_application(client, applicant_headers)
    user_factory(email="different-applicant@example.test")
    other_headers = token_for(client, "different-applicant@example.test")
    user_factory(email="run-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    reviewer_headers = token_for(client, "run-reviewer@example.test")
    user_factory(email="run-manager@example.test", role=UserRole.RULES_MANAGER.value)
    manager_headers = token_for(client, "run-manager@example.test")
    endpoint = f"/api/applications/{application_id}/validation-runs"

    assert client.post(endpoint).status_code == 401
    assert client.post(endpoint, headers=other_headers).status_code == 404
    assert client.post(endpoint, headers=manager_headers).status_code == 403
    assert client.post(endpoint, headers=reviewer_headers).status_code == 201
    assert client.get(f"/api/applications/{application_id}/validation-runs", headers=other_headers).status_code == 404
