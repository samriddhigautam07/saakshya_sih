"""Application-owned validation run and finding endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.dependencies import get_db
from app.models import (
    ApplicationRecord,
    User,
    UserRole,
    ValidationFinding,
    ValidationRun,
    ValidationRunResult,
)
from app.schemas import ValidationFindingRead, ValidationRunRead, ValidationRunResultRead
from app.validation_service import execute_validation

router = APIRouter(prefix="/api/applications/{application_id}", tags=["validation"])


def _authorized_application(application_id: str, user: User, db: Session) -> ApplicationRecord:
    if user.role == UserRole.APPLICANT:
        application = db.scalar(select(ApplicationRecord).where(
            ApplicationRecord.id == application_id,
            ApplicationRecord.owner_user_id == user.id,
        ))
    elif user.role == UserRole.OFFICIAL_REVIEWER:
        application = db.get(ApplicationRecord, application_id)
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions to validate applications.")
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


def _result_read(result: ValidationRunResult) -> ValidationRunResultRead:
    return ValidationRunResultRead(
        id=result.id,
        run_id=result.run_id,
        finding_id=result.finding_id,
        issue_key=result.issue_key,
        source_kind=result.source_kind,
        rule_id=result.rule_id,
        rule_version=result.rule_version,
        rule_name=result.rule_name,
        result_status=result.result_status,
        severity=result.severity,
        expected=result.expected,
        actual=result.actual,
        document_ids_json=result.document_ids_json,
        evidence_json=result.evidence_json,
        revalidation_state=result.revalidation_state,
        message=result.message,
        created_at=result.created_at,
    )


def _run_read(run: ValidationRun, db: Session) -> ValidationRunRead:
    results = db.scalars(
        select(ValidationRunResult)
        .where(ValidationRunResult.run_id == run.id)
        .order_by(ValidationRunResult.created_at, ValidationRunResult.id)
    ).all()
    return ValidationRunRead(
        id=run.id,
        application_id=run.application_id,
        actor=run.actor,
        status=run.status,
        summary_json=run.summary_json,
        results=[_result_read(item) for item in results],
        created_at=run.created_at,
    )


@router.post("/validation-runs", response_model=ValidationRunRead, status_code=status.HTTP_201_CREATED)
def run_validation(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ValidationRunRead:
    application = _authorized_application(application_id, user, db)
    run = execute_validation(db, application, user.email)
    return _run_read(run, db)


@router.get("/validation-runs", response_model=list[ValidationRunRead])
def list_validation_runs(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ValidationRunRead]:
    _authorized_application(application_id, user, db)
    runs = db.scalars(
        select(ValidationRun)
        .where(ValidationRun.application_id == application_id)
        .order_by(ValidationRun.created_at.desc(), ValidationRun.id)
    ).all()
    return [_run_read(run, db) for run in runs]


@router.get("/validation-runs/{run_id}", response_model=ValidationRunRead)
def get_validation_run(
    application_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ValidationRunRead:
    _authorized_application(application_id, user, db)
    run = db.scalar(select(ValidationRun).where(
        ValidationRun.id == run_id,
        ValidationRun.application_id == application_id,
    ))
    if run is None:
        raise HTTPException(status_code=404, detail="Validation run not found.")
    return _run_read(run, db)


@router.get("/findings", response_model=list[ValidationFindingRead])
def list_application_findings(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ValidationFinding]:
    _authorized_application(application_id, user, db)
    return list(db.scalars(
        select(ValidationFinding)
        .where(ValidationFinding.application_id == application_id)
        .order_by(ValidationFinding.created_at, ValidationFinding.finding_key)
    ).all())
