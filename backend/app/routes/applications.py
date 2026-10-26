"""Application create, list, detail, and update endpoints."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import ensure_application_read_access, get_current_user, require_roles
from app.dependencies import get_db
from app.models import (
    ApplicationRecord,
    AuditLog,
    DocumentMetadata,
    ReviewerDecision,
    User,
    UserRole,
    ValidationFinding,
)
from app.schemas import (
    ApplicationCreate,
    ApplicationPatch,
    ApplicationRead,
    ReviewerDecisionCreate,
    ReviewerDecisionRead,
    ReviewerFindingDecisionCreate,
    ReviewerFindingDecisionRead,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _with_details():
    return (
        selectinload(ApplicationRecord.documents).selectinload(DocumentMetadata.verification_records),
        selectinload(ApplicationRecord.findings),
        selectinload(ApplicationRecord.verification_records),
        selectinload(ApplicationRecord.reviewer_decisions),
        selectinload(ApplicationRecord.audit_logs),
    )


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.APPLICANT)),
) -> ApplicationRecord:
    application = ApplicationRecord(
        id=f"APP-{uuid4().hex[:12].upper()}",
        owner_user_id=user.id,
        **payload.model_dump(exclude={"documents"}),
    )
    application.documents = [DocumentMetadata(**item.model_dump()) for item in payload.documents]
    application.audit_logs.append(AuditLog(actor="System", action="Application created"))
    db.add(application)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The application data conflicts with an existing unique record.",
        ) from error
    db.refresh(application)
    return db.scalar(select(ApplicationRecord).where(ApplicationRecord.id == application.id).options(*_with_details()))


@router.get("", response_model=list[ApplicationRead])
def list_applications(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ApplicationRecord]:
    ensure_application_read_access(user)
    statement = (
        select(ApplicationRecord)
        .options(*_with_details())
        .order_by(ApplicationRecord.created_at.desc(), ApplicationRecord.id)
        .offset(offset)
        .limit(limit)
    )
    if user.role == UserRole.APPLICANT:
        statement = statement.where(ApplicationRecord.owner_user_id == user.id)
    return list(db.scalars(statement).all())


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationRecord:
    ensure_application_read_access(user)
    statement = select(ApplicationRecord).where(ApplicationRecord.id == application_id).options(*_with_details())
    if user.role == UserRole.APPLICANT:
        statement = statement.where(ApplicationRecord.owner_user_id == user.id)
    application = db.scalar(statement)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


@router.patch("/{application_id}", response_model=ApplicationRead)
def patch_application(
    application_id: str,
    payload: ApplicationPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.APPLICANT)),
) -> ApplicationRecord:
    application = db.scalar(
        select(ApplicationRecord).where(
            ApplicationRecord.id == application_id,
            ApplicationRecord.owner_user_id == user.id,
        )
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(application, field, value)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The application data conflicts with an existing unique record.",
        ) from error

    return db.scalar(
        select(ApplicationRecord)
        .where(ApplicationRecord.id == application_id)
        .options(*_with_details())
    )


@router.post(
    "/{application_id}/decisions",
    response_model=ReviewerDecisionRead,
    status_code=status.HTTP_201_CREATED,
)
def record_reviewer_decision(
    application_id: str,
    payload: ReviewerDecisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OFFICIAL_REVIEWER)),
) -> ReviewerDecision:
    application = db.get(ApplicationRecord, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    finding = db.scalar(
        select(ValidationFinding).where(
            ValidationFinding.id == payload.finding_id,
            ValidationFinding.application_id == application_id,
        )
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found for this application.")

    decision = ReviewerDecision(
        application_id=application_id,
        finding_id=finding.id,
        status=payload.status,
        actor=user.email,
        note=payload.note,
    )
    finding.status = payload.status
    db.add(decision)
    db.add(
        AuditLog(
            application_id=application_id,
            finding_id=finding.id,
            actor=user.email,
            action=f"Official review decision recorded: {payload.status}",
            note=payload.note,
        )
    )
    db.commit()
    db.refresh(decision)
    return decision


@router.post(
    "/{application_id}/findings/{finding_id}/reviews",
    response_model=ReviewerFindingDecisionRead,
    status_code=status.HTTP_201_CREATED,
)
def record_official_finding_decision(
    application_id: str,
    finding_id: str,
    payload: ReviewerFindingDecisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OFFICIAL_REVIEWER)),
) -> ReviewerFindingDecisionRead:
    application = db.get(ApplicationRecord, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    finding = db.scalar(select(ValidationFinding).where(
        ValidationFinding.id == finding_id,
        ValidationFinding.application_id == application_id,
    ))
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found for this application.")
    previous_status = finding.status
    status_by_decision = {
        "confirmed_issue": "Under Review",
        "dismissed_finding": "Resolved",
        "clarification_required": "Under Review",
    }
    current_status = status_by_decision[payload.decision]
    decision = ReviewerDecision(
        application_id=application_id,
        finding_id=finding.id,
        status=current_status,
        decision_type=payload.decision,
        previous_status=previous_status,
        actor=user.email,
        note=payload.reason.strip(),
    )
    finding.status = current_status
    if payload.decision == "dismissed_finding":
        finding.resolution_type = "dismissed_by_reviewer"
    elif finding.resolution_type == "dismissed_by_reviewer":
        finding.resolution_type = None
    db.add(decision)
    db.add(AuditLog(
        application_id=application_id,
        finding_id=finding.id,
        actor=user.email,
        action=f"Official finding decision: {payload.decision}",
        note=payload.reason.strip(),
    ))
    db.commit()
    db.refresh(decision)
    return ReviewerFindingDecisionRead(
        id=decision.id,
        application_id=decision.application_id,
        finding_id=finding.id,
        decision=payload.decision,
        previous_status=previous_status,
        status=current_status,
        actor=decision.actor,
        reason=decision.note or "",
        created_at=decision.created_at,
    )


@router.get(
    "/{application_id}/findings/{finding_id}/reviews",
    response_model=list[ReviewerFindingDecisionRead],
)
def get_finding_review_history(
    application_id: str,
    finding_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReviewerFindingDecisionRead]:
    ensure_application_read_access(user)
    application_query = select(ApplicationRecord).where(ApplicationRecord.id == application_id)
    if user.role == UserRole.APPLICANT:
        application_query = application_query.where(ApplicationRecord.owner_user_id == user.id)
    application = db.scalar(application_query)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    finding = db.scalar(select(ValidationFinding).where(
        ValidationFinding.id == finding_id,
        ValidationFinding.application_id == application_id,
    ))
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found for this application.")
    decisions = db.scalars(select(ReviewerDecision).where(
        ReviewerDecision.finding_id == finding.id,
        ReviewerDecision.decision_type.is_not(None),
    ).order_by(ReviewerDecision.created_at, ReviewerDecision.id)).all()
    return [ReviewerFindingDecisionRead(
        id=item.id,
        application_id=item.application_id,
        finding_id=finding.id,
        decision=item.decision_type,
        previous_status=item.previous_status,
        status=item.status,
        actor=item.actor,
        reason=item.note or "",
        created_at=item.created_at,
    ) for item in decisions]
