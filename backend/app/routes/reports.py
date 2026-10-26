"""Read-only audit history and application review reports."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import (
    ApplicationRecord,
    AuditEvent,
    AuditLog,
    DocumentMetadata,
    RegulatoryRule,
    RegulatorySource,
    ReviewerDecision,
    User,
    UserRole,
    ValidationFinding,
    ValidationRun,
    ValidationRunResult,
    VerificationRecord,
)
from app.auth import get_current_user
from app.schemas import ApplicationReviewReport, AuditHistoryEntry, ReportRuleReference

router = APIRouter(tags=["reports", "audit"])


def _application_access(application_id: str, user: User, db: Session) -> ApplicationRecord:
    if user.role == UserRole.APPLICANT:
        application = db.scalar(select(ApplicationRecord).where(
            ApplicationRecord.id == application_id,
            ApplicationRecord.owner_user_id == user.id,
        ))
    elif user.role == UserRole.OFFICIAL_REVIEWER:
        application = db.get(ApplicationRecord, application_id)
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


def _event_entry(event: AuditEvent) -> AuditHistoryEntry:
    return AuditHistoryEntry(
        id=event.id,
        application_id=event.application_id,
        actor=event.actor,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        details=event.details_json,
        created_at=event.created_at,
    )


def _legacy_entry(event: AuditLog) -> AuditHistoryEntry:
    return AuditHistoryEntry(
        id=event.id,
        application_id=event.application_id,
        actor=event.actor,
        event_type="audit_log",
        entity_type="finding" if event.finding_id else "application",
        entity_id=event.finding_id or event.application_id,
        details={"action": event.action, "note": event.note},
        created_at=event.created_at,
    )


@router.get("/api/applications/{application_id}/audit-history", response_model=list[AuditHistoryEntry])
def application_audit_history(
    application_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AuditHistoryEntry]:
    _application_access(application_id, user, db)
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.application_id == application_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(limit)
    ).all()
    logs = db.scalars(
        select(AuditLog).where(AuditLog.application_id == application_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit)
    ).all()
    entries = [_event_entry(event) for event in events] + [_legacy_entry(log) for log in logs]
    return sorted(entries, key=lambda item: (item.created_at, item.id), reverse=True)[:limit]


@router.get("/api/audit-history", response_model=list[AuditHistoryEntry])
def regulatory_audit_history(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AuditHistoryEntry]:
    if user.role != UserRole.RULES_MANAGER:
        raise HTTPException(status_code=403, detail="Rules Manager / Administrator role required.")
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(limit)).all()
    return [_event_entry(event) for event in events]


@router.get("/api/applications/{application_id}/report", response_model=ApplicationReviewReport)
def application_review_report(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationReviewReport:
    application = _application_access(application_id, user, db)
    latest_run = db.scalar(
        select(ValidationRun).where(ValidationRun.application_id == application.id)
        .order_by(ValidationRun.created_at.desc(), ValidationRun.id.desc()).limit(1)
    )
    latest_results = []
    if latest_run is not None:
        latest_results = db.scalars(
            select(ValidationRunResult).where(ValidationRunResult.run_id == latest_run.id)
            .order_by(ValidationRunResult.created_at, ValidationRunResult.id)
        ).all()

    current_results: dict[str, ValidationRunResult] = {
        item.finding_id: item for item in latest_results if item.finding_id
    }
    findings = db.scalars(
        select(ValidationFinding).where(ValidationFinding.application_id == application.id)
        .order_by(ValidationFinding.created_at, ValidationFinding.finding_key)
    ).all()
    finding_items = []
    for finding in findings:
        result = current_results.get(finding.id)
        if result is not None:
            disposition = {
                "pass": "Passed",
                "mismatch": "Issue Found",
                "unable_to_verify": "Unable to Verify",
                "manual_review": "Manual Review Required",
            }[result.result_status]
        elif finding.resolution_type == "resolved_by_new_evidence":
            disposition = "Passed"
        elif finding.resolution_type == "dismissed_by_reviewer":
            disposition = "Dismissed by Official Reviewer"
        else:
            disposition = finding.status
        finding_items.append({
            "id": finding.id,
            "rule_id": finding.rule_id,
            "rule_version": finding.rule_version,
            "title": finding.rule_name,
            "status": finding.status,
            "resolution_type": finding.resolution_type,
            "report_disposition": disposition,
            "severity": finding.severity,
            "expected": finding.expected,
            "observed": finding.actual,
            "document_ids": finding.document_ids_json,
            "evidence": finding.evidence_json,
            "message": finding.message,
        })

    rule_references = []
    seen_rules: set[tuple[str, int]] = set()
    for result in latest_results:
        if result.source_kind != "regulatory" or result.rule_version is None:
            continue
        key = (result.rule_id, result.rule_version)
        if key in seen_rules:
            continue
        seen_rules.add(key)
        rule = db.scalar(select(RegulatoryRule).where(
            RegulatoryRule.rule_id == result.rule_id,
            RegulatoryRule.version == result.rule_version,
        ))
        if rule is None:
            continue
        source = db.get(RegulatorySource, rule.source_id)
        if source is None:
            continue
        rule_references.append(ReportRuleReference(
            rule_id=rule.rule_id,
            version=rule.version,
            title=rule.rule_title,
            source_title=source.title,
            source_version=rule.source_version,
            clause_reference=rule.clause_reference,
            annexure_reference=rule.annexure_reference,
            page_number=rule.page_number,
            supporting_quotation=rule.supporting_quotation,
        ))

    verifications = db.scalars(
        select(VerificationRecord).where(VerificationRecord.application_id == application.id)
        .order_by(VerificationRecord.checked_at.desc(), VerificationRecord.id)
    ).all()
    decisions = db.scalars(
        select(ReviewerDecision).where(ReviewerDecision.application_id == application.id)
        .order_by(ReviewerDecision.created_at, ReviewerDecision.id)
    ).all()
    documents = db.scalars(select(DocumentMetadata).where(DocumentMetadata.application_id == application.id)).all()
    return ApplicationReviewReport(
        application={
            "id": application.id,
            "institution_id": application.institution_id,
            "institution_name": application.institution_name,
            "category": application.category,
            "reference_number": application.reference_number,
            "submitted_at": application.submitted_at.isoformat(),
        },
        synthetic_data=application.is_synthetic or any(item.field_source == "synthetic" for item in documents),
        latest_validation_run=(
            {"id": latest_run.id, "status": latest_run.status, "summary": latest_run.summary_json,
             "created_at": latest_run.created_at.isoformat(),
             "results": [{
                 "rule_id": item.rule_id, "rule_version": item.rule_version,
                 "status": {
                     "pass": "Passed", "mismatch": "Issue Found",
                     "unable_to_verify": "Unable to Verify", "manual_review": "Manual Review Required",
                 }[item.result_status],
                 "message": item.message, "expected": item.expected, "observed": item.actual,
                 "document_ids": item.document_ids_json, "evidence": item.evidence_json,
             } for item in latest_results]}
            if latest_run else None
        ),
        applicable_rule_references=rule_references,
        findings=finding_items,
        verification_status=[{
            "document_id": item.document_id,
            "status": item.status,
            "checked_at": item.checked_at.isoformat(),
            "message": item.message,
            "provider": item.provider,
            "is_mock": item.is_mock,
        } for item in verifications],
        mock_verification_present=any(item.is_mock for item in verifications),
        reviewer_decisions=[{
            "id": item.id,
            "finding_id": item.finding_id,
            "decision": item.decision_type,
            "workflow_status": item.status,
            "previous_status": item.previous_status,
            "reviewer": item.actor,
            "reason": item.note,
            "created_at": item.created_at.isoformat(),
        } for item in decisions],
    )
