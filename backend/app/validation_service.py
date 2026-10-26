"""Persisted validation runs combining verified rules and document consistency checks."""

from datetime import date
import hashlib
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ApplicationRecord,
    AuditEvent,
    DocumentMetadata,
    DocumentCorrection,
    InstitutionalReferenceRecord,
    RegulatoryRule,
    RegulatorySource,
    ValidationFinding,
    ValidationRun,
    ValidationRunResult,
    utc_now,
)
from app.validation_engine import Evaluation, evaluate_cross_document, evaluate_rule

SUPPORTED_VALIDATION_TYPES = {"presence", "date", "numeric", "text_match", "manual_review"}


def _finding_key(issue_key: str) -> str:
    digest = hashlib.sha256(issue_key.encode("utf-8")).hexdigest()[:48]
    return f"validation:{digest}"


def execute_validation(db: Session, application: ApplicationRecord, actor: str) -> ValidationRun:
    today = date.today()
    base_documents = list(db.scalars(
        select(DocumentMetadata)
        .where(DocumentMetadata.application_id == application.id)
        .options(selectinload(DocumentMetadata.structured_extractions))
        .order_by(DocumentMetadata.created_at, DocumentMetadata.id)
    ).all())
    corrections = db.scalars(
        select(DocumentCorrection)
        .where(DocumentCorrection.application_id == application.id)
        .options(selectinload(DocumentCorrection.structured_extractions))
        .order_by(DocumentCorrection.version.desc(), DocumentCorrection.created_at.desc())
    ).all()
    latest_correction: dict[str, DocumentCorrection] = {}
    for correction in corrections:
        latest_correction.setdefault(correction.document_id, correction)
    documents = []
    for document in base_documents:
        correction = latest_correction.get(document.id)
        if correction is None:
            documents.append(SimpleNamespace(
                id=document.id,
                base_document_id=document.id,
                category=document.category,
                structured_extractions=document.structured_extractions,
            ))
        else:
            documents.append(SimpleNamespace(
                id=correction.id,
                base_document_id=document.id,
                category=document.category,
                structured_extractions=correction.structured_extractions,
            ))

    verified_rules = db.execute(
        select(RegulatoryRule, RegulatorySource)
        .join(RegulatorySource, RegulatorySource.id == RegulatoryRule.source_id)
        .where(
            RegulatoryRule.status == "active",
            RegulatoryRule.is_demo.is_(False),
            RegulatoryRule.application_category == application.category,
            RegulatorySource.status == "verified",
            RegulatoryRule.source_version == RegulatorySource.document_version,
        )
    ).all()
    rules = [
        rule for rule, _source in verified_rules
        if rule.validation_type in SUPPORTED_VALIDATION_TYPES
        if (rule.applicable_from is None or rule.applicable_from <= today)
        and (rule.applicable_until is None or rule.applicable_until >= today)
    ]
    reference_ids = {
        rule.validation_parameters.get("reference_record_id")
        for rule in rules
        if isinstance(rule.validation_parameters, dict)
        and isinstance(rule.validation_parameters.get("reference_record_id"), str)
    }
    reference_records = []
    if application.institution_id and reference_ids:
        reference_records = list(db.scalars(
            select(InstitutionalReferenceRecord).where(
                InstitutionalReferenceRecord.institution_id == application.institution_id,
                InstitutionalReferenceRecord.is_authorized.is_(True),
                InstitutionalReferenceRecord.institution_id.in_(reference_ids),
            )
        ).all())

    cross_document_evaluations = evaluate_cross_document(documents)
    evaluations: list[Evaluation] = [
        evaluate_rule(rule, documents, application, today, reference_records)
        for rule in rules
    ]
    evaluations.extend(cross_document_evaluations)

    actionable = [item for item in evaluations if item.result_status != "pass"]
    manual_count = sum(item.result_status in {"manual_review", "unable_to_verify"} for item in evaluations)
    if not rules and not cross_document_evaluations:
        run_status = "no_verified_rules"
    elif manual_count:
        run_status = "completed_with_manual_review"
    else:
        run_status = "completed"
    run = ValidationRun(
        application_id=application.id,
        actor=actor,
        status=run_status,
        summary_json={
            "verified_rules_evaluated": len(rules),
            "cross_document_checks": len(cross_document_evaluations),
            "results": len(evaluations),
            "passed": sum(item.result_status == "pass" for item in evaluations),
            "mismatches": sum(item.result_status == "mismatch" for item in evaluations),
            "unable_to_verify": sum(item.result_status == "unable_to_verify" for item in evaluations),
            "manual_review": sum(item.result_status == "manual_review" for item in evaluations),
            "findings": len(actionable),
        },
        created_at=utc_now(),
    )
    db.add(run)
    db.flush()

    revalidation_states = []
    for evaluation in evaluations:
        finding = None
        key = _finding_key(evaluation.issue_key)
        finding = db.scalar(select(ValidationFinding).where(
            ValidationFinding.application_id == application.id,
            ValidationFinding.finding_key == key,
        ))
        revalidation_state = None
        if evaluation.result_status != "pass":
            if finding is None:
                finding = ValidationFinding(
                    application_id=application.id,
                    finding_key=key,
                    rule_id=evaluation.rule_id,
                    rule_name=evaluation.rule_name,
                    rule_version=evaluation.rule_version,
                    severity=evaluation.severity,
                    target=evaluation.rule_name,
                    expected=evaluation.expected,
                    actual=evaluation.actual,
                    status="Open",
                    document_id=(
                        evaluation.evidence[0].get("base_document_id", evaluation.document_ids[0])
                        if len(evaluation.document_ids) == 1 and evaluation.evidence else None
                    ),
                    document_ids_json=evaluation.document_ids,
                    evidence_json=evaluation.evidence,
                    message=evaluation.message,
                    recommendation="Review the recorded evidence and resolve the finding or request manual assessment.",
                )
                db.add(finding)
                db.flush()
                revalidation_state = "newly_detected"
            else:
                revalidation_state = "persistent"
                if finding.resolution_type == "resolved_by_new_evidence":
                    finding.resolution_type = None
                    finding.status = "Open"
                # Keep the review status and decision history. Per-run evidence remains immutable below.
                finding.rule_name = evaluation.rule_name
                finding.rule_version = evaluation.rule_version
                finding.severity = evaluation.severity
                finding.expected = evaluation.expected
                finding.actual = evaluation.actual
                finding.document_id = (
                    evaluation.evidence[0].get("base_document_id", evaluation.document_ids[0])
                    if len(evaluation.document_ids) == 1 and evaluation.evidence else None
                )
                finding.document_ids_json = evaluation.document_ids
                finding.evidence_json = evaluation.evidence
                finding.message = evaluation.message
                finding.updated_at = utc_now()
        elif finding is not None:
            revalidation_state = "resolved_by_new_evidence"
            if finding.resolution_type != "dismissed_by_reviewer":
                finding.resolution_type = "resolved_by_new_evidence"
                finding.status = "Resolved"
                finding.updated_at = utc_now()

        issue_key = evaluation.issue_key
        if len(issue_key) > 230:
            issue_key = f"{issue_key[:170]}:{hashlib.sha256(issue_key.encode()).hexdigest()[:48]}"
        revalidation_states.append(revalidation_state)
        db.add(ValidationRunResult(
            run_id=run.id,
            finding_id=finding.id if finding is not None else None,
            issue_key=issue_key,
            source_kind=evaluation.source_kind,
            rule_id=evaluation.rule_id,
            rule_version=evaluation.rule_version,
            rule_name=evaluation.rule_name,
            result_status=evaluation.result_status,
            severity=evaluation.severity,
            expected=evaluation.expected,
            actual=evaluation.actual,
            document_ids_json=evaluation.document_ids,
            evidence_json=evaluation.evidence,
            revalidation_state=revalidation_state,
            message=evaluation.message,
            created_at=utc_now(),
        ))
    run.summary_json = {
        **run.summary_json,
        "newly_detected": revalidation_states.count("newly_detected"),
        "persistent": revalidation_states.count("persistent"),
        "resolved_by_new_evidence": revalidation_states.count("resolved_by_new_evidence"),
    }
    db.add(AuditEvent(
        application_id=application.id,
        actor=actor,
        event_type="validation_run_completed",
        entity_type="validation_run",
        entity_id=run.id,
        details_json={"status": run.status, "summary": run.summary_json},
    ))
    db.commit()
    db.refresh(run)
    return run
