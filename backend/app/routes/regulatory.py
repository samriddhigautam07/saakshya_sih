"""Authenticated regulatory source registry, rule review, and checklist APIs."""

import hashlib
import os
from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.dependencies import get_db
from app.file_storage import create_temporary_file, resolve_storage_key
from app.models import (
    AuditEvent,
    RegulatoryCategoryConfig,
    RegulatoryRule,
    RegulatorySource,
    RegulatorySourcePassage,
    User,
    UserRole,
)
from app.pdf_extraction import extract_pdf_text
from app.regulatory_service import RuleProposalError, propose_rule
from app.schemas import (
    CategoryConfigureRequest,
    ChecklistItem,
    ChecklistRead,
    RegulatoryRuleRead,
    RegulatorySourceCreate,
    RegulatorySourcePassageRead,
    RegulatorySourceRead,
    RuleDraftFields,
    RuleProposalRequest,
    RuleRevisionRequest,
    RuleTransitionRequest,
)

router = APIRouter(prefix="/api/regulatory", tags=["regulatory"])
PDF_SIGNATURE = b"%PDF-"
MAX_SOURCE_FILE_BYTES = 20 * 1024 * 1024
SAFE_SOURCE_FILENAME = re.compile(r"[^\w .()\-]+", flags=re.UNICODE)


def _rule_manager(user: User = Depends(require_roles(UserRole.RULES_MANAGER))) -> User:
    return user


def _source_or_404(db: Session, source_id: str) -> RegulatorySource:
    source = db.get(RegulatorySource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Regulatory source not found.")
    return source


def _audit_change(db: Session, actor: str, event_type: str, entity_type: str, entity_id: str, details: dict) -> None:
    db.add(AuditEvent(
        actor=actor,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=details,
    ))


def _read_source(source: RegulatorySource) -> RegulatorySourceRead:
    return RegulatorySourceRead(
        id=source.id,
        supersedes_source_id=source.supersedes_source_id,
        title=source.title,
        issuing_authority=source.issuing_authority,
        source_url=source.source_url,
        original_filename=source.original_filename,
        document_version=source.document_version,
        publication_date=source.publication_date,
        effective_date=source.effective_date,
        retrieval_date=source.retrieval_date,
        status=source.status,
        extraction_status=source.extraction_status,
        passage_count=len(source.passages),
        created_at=source.created_at,
    )


def _read_rule(rule: RegulatoryRule) -> RegulatoryRuleRead:
    return RegulatoryRuleRead(
        id=rule.id,
        rule_id=rule.rule_id,
        version=rule.version,
        source_id=rule.source_id,
        source_version=rule.source_version,
        rule_title=rule.rule_title,
        supporting_quotation=rule.supporting_quotation,
        clause_reference=rule.clause_reference,
        annexure_reference=rule.annexure_reference,
        page_number=rule.page_number,
        application_category=rule.application_category,
        requirement=rule.requirement,
        conditions=rule.conditions,
        required_evidence=rule.required_evidence,
        validation_type=rule.validation_type,
        validation_parameters=rule.validation_parameters,
        applicable_from=rule.applicable_from,
        applicable_until=rule.applicable_until,
        uncertainty_notes=rule.uncertainty_notes,
        is_demo=rule.is_demo,
        status=rule.status,
        created_by=rule.created_by,
        reviewed_by=rule.reviewed_by,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _page_passages(text: str) -> list[tuple[int, str]]:
    parts = re.split(r"(?m)^\[Page\s+(\d+)(?:\s*\|[^\]]+)?\]\s*$", text)
    passages: list[tuple[int, str]] = []
    for index in range(1, len(parts), 2):
        page_number = int(parts[index])
        content = parts[index + 1].strip()
        if content:
            passages.append((page_number, content))
    return passages


@router.post("/sources", response_model=RegulatorySourceRead, status_code=status.HTTP_201_CREATED)
def register_source(
    payload: RegulatorySourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_rule_manager),
) -> RegulatorySourceRead:
    prior = None
    if payload.supersedes_source_id:
        prior = _source_or_404(db, payload.supersedes_source_id)
        if prior.issuing_authority.casefold() != payload.issuing_authority.casefold():
            raise HTTPException(status_code=422, detail="A replacement source must have the same issuing authority.")
        if prior.document_version == payload.document_version:
            raise HTTPException(status_code=422, detail="A superseding source must use a new document version.")
    source = RegulatorySource(**payload.model_dump(), registered_by=user.email)
    db.add(source)
    if prior is not None:
        prior.status = "inactive"
    db.flush()
    _audit_change(db, user.email, "regulatory_source_registered", "regulatory_source", source.id,
                  {"title": source.title, "version": source.document_version,
                   "supersedes_source_id": source.supersedes_source_id})
    db.commit()
    db.refresh(source)
    return _read_source(source)


@router.get("/sources", response_model=list[RegulatorySourceRead])
def list_sources(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RegulatorySourceRead]:
    rows = db.scalars(select(RegulatorySource).order_by(RegulatorySource.created_at.desc())).all()
    return [_read_source(row) for row in rows]


@router.post("/sources/{source_id}/upload", response_model=RegulatorySourceRead)
async def upload_source_pdf(
    source_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_rule_manager),
) -> RegulatorySourceRead:
    source = _source_or_404(db, source_id)
    if source.storage_key:
        raise HTTPException(status_code=409, detail="A source file is already attached to this source version.")
    filename = file.filename or ""
    safe_name = SAFE_SOURCE_FILENAME.sub("_", filename.replace("\\", "/").split("/")[-1]).strip(" .")[:512]
    if not safe_name or Path(safe_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only PDF regulatory source files are accepted.")
    mime = (file.content_type or "").split(";", 1)[0].lower()
    if mime and mime != "application/pdf":
        raise HTTPException(status_code=415, detail="Source file MIME type must be application/pdf.")

    private_root: Path = request.app.state.storage_root.resolve()
    root: Path = private_root / "regulatory_sources"
    root.mkdir(mode=0o700, exist_ok=True)
    root = root.resolve()
    if root.parent != private_root:
        raise HTTPException(status_code=500, detail="Private regulatory storage is not safely configured.")
    if root.stat().st_mode & 0o077:
        os.chmod(root, 0o700)
    descriptor, temp_path = create_temporary_file(root)
    digest = hashlib.sha256()
    total = 0
    header = bytearray()
    try:
        with os.fdopen(descriptor, "wb") as output:
            while chunk := await file.read(64 * 1024):
                total += len(chunk)
                if total > MAX_SOURCE_FILE_BYTES:
                    raise HTTPException(status_code=413, detail="Regulatory source PDF exceeds 20 MiB.")
                if len(header) < len(PDF_SIGNATURE):
                    header.extend(chunk[: len(PDF_SIGNATURE) - len(header)])
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if bytes(header) != PDF_SIGNATURE:
            raise HTTPException(status_code=415, detail="Source file does not have a valid PDF signature.")

        extraction = extract_pdf_text(
            temp_path,
            request.app.state.settings.max_extracted_text_chars,
            max_pages=request.app.state.settings.pdf_max_pages,
            ocr_max_pages=request.app.state.settings.ocr_max_pages,
            ocr_dpi=request.app.state.settings.ocr_dpi,
            ocr_min_digital_chars=request.app.state.settings.ocr_min_digital_chars,
            ocr_max_page_pixels=request.app.state.settings.ocr_max_page_pixels,
            ocr_page_timeout_seconds=request.app.state.settings.ocr_page_timeout_seconds,
            processing_timeout_seconds=request.app.state.settings.pdf_processing_timeout_seconds,
        )
        storage_key = f"{uuid4().hex}.pdf"
        target = resolve_storage_key(root, storage_key)
        os.link(temp_path, target)
        source.storage_key = storage_key
        source.original_filename = safe_name
        source.sha256 = digest.hexdigest()
        source.size_bytes = total
        source.extraction_status = extraction.status
        source.status = "ingested"
        source.passages = [
            RegulatorySourcePassage(page_number=page_number, text=page_text)
            for page_number, page_text in _page_passages(extraction.text)
        ]
        _audit_change(db, user.email, "regulatory_source_ingested", "regulatory_source", source.id,
                      {"version": source.document_version, "extraction_status": extraction.status,
                       "passage_count": len(source.passages)})
        db.commit()
        db.refresh(source)
        return _read_source(source)
    except HTTPException:
        db.rollback()
        raise
    except OSError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Regulatory source could not be stored safely.") from error
    finally:
        temp_path.unlink(missing_ok=True)
        await file.close()


@router.get("/sources/{source_id}/passages", response_model=list[RegulatorySourcePassageRead])
def list_source_passages(
    source_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RegulatorySourcePassageRead]:
    _source_or_404(db, source_id)
    passages = db.scalars(
        select(RegulatorySourcePassage)
        .where(RegulatorySourcePassage.source_id == source_id)
        .order_by(RegulatorySourcePassage.page_number)
    ).all()
    return [RegulatorySourcePassageRead.model_validate(item, from_attributes=True) for item in passages]


@router.get("/sources/{source_id}/search", response_model=list[RegulatorySourcePassageRead])
def search_source_passages(
    source_id: str,
    query: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RegulatorySourcePassageRead]:
    _source_or_404(db, source_id)
    matches = db.scalars(
        select(RegulatorySourcePassage)
        .where(
            RegulatorySourcePassage.source_id == source_id,
            RegulatorySourcePassage.text.ilike(f"%{query.strip()}%"),
        )
        .order_by(RegulatorySourcePassage.page_number)
        .limit(limit)
    ).all()
    return [RegulatorySourcePassageRead.model_validate(item, from_attributes=True) for item in matches]


@router.post("/sources/{source_id}/verify", response_model=RegulatorySourceRead)
def verify_source(
    source_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(_rule_manager),
) -> RegulatorySourceRead:
    source = _source_or_404(db, source_id)
    if not source.passages:
        raise HTTPException(status_code=409, detail="Ingest a readable PDF before verifying the source.")
    source.status = "verified"
    _audit_change(db, _user.email, "regulatory_source_verified", "regulatory_source", source.id,
                  {"version": source.document_version, "passage_count": len(source.passages)})
    db.commit()
    db.refresh(source)
    return _read_source(source)


@router.post("/sources/{source_id}/proposals", response_model=RegulatoryRuleRead, status_code=201)
async def create_rule_proposal(
    source_id: str,
    payload: RuleProposalRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_rule_manager),
) -> RegulatoryRuleRead:
    source = _source_or_404(db, source_id)
    if source.status != "verified":
        raise HTTPException(status_code=409, detail="A human must verify the source before rule proposals are allowed.")
    passage = db.scalar(
        select(RegulatorySourcePassage).where(
            RegulatorySourcePassage.id == payload.passage_id,
            RegulatorySourcePassage.source_id == source_id,
        )
    )
    if passage is None:
        raise HTTPException(status_code=404, detail="Source passage not found.")
    provider = request.app.state.llm_provider
    if provider is None:
        raise HTTPException(status_code=503, detail="No LLM provider is configured for rule proposals.")
    try:
        fields, manual_review = await propose_rule(
            provider,
            passage.text,
            passage.page_number,
            payload.application_category,
            source.publication_date,
            source.effective_date,
        )
    except RuleProposalError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Configured rule proposal provider request failed.") from error
    rule = RegulatoryRule(
        rule_id=f"VW-RULE-{uuid4().hex[:12].upper()}",
        version=1,
        source_id=source.id,
        source_version=source.document_version,
        source_passage_id=passage.id,
        **fields.model_dump(),
        status="manual_review" if manual_review else "draft",
        created_by=user.email,
        is_demo=False,
    )
    db.add(rule)
    db.flush()
    _audit_change(db, user.email, "regulatory_rule_proposed", "regulatory_rule", rule.id,
                  {"rule_id": rule.rule_id, "version": rule.version, "status": rule.status})
    db.commit()
    db.refresh(rule)
    return _read_rule(rule)


@router.get("/rules", response_model=list[RegulatoryRuleRead])
def list_rules(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RegulatoryRuleRead]:
    statement = select(RegulatoryRule).order_by(RegulatoryRule.rule_id, RegulatoryRule.version.desc())
    if user.role != UserRole.RULES_MANAGER:
        statement = statement.where(RegulatoryRule.status == "active")
    return [_read_rule(item) for item in db.scalars(statement).all()]


@router.post("/rules/{rule_version_id}/approve", response_model=RegulatoryRuleRead)
def approve_rule(
    rule_version_id: str,
    _payload: RuleTransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_rule_manager),
) -> RegulatoryRuleRead:
    rule = db.get(RegulatoryRule, rule_version_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule version not found.")
    source = _source_or_404(db, rule.source_id)
    passage = db.get(RegulatorySourcePassage, rule.source_passage_id)
    if rule.status not in {"draft", "manual_review"}:
        raise HTTPException(status_code=409, detail="Only draft rules can be approved.")
    if source.status != "verified" or source.document_version != rule.source_version:
        raise HTTPException(status_code=409, detail="The source changed or is not verified; proposal requires re-review.")
    if passage is None or passage.source_id != source.id or rule.supporting_quotation not in passage.text:
        raise HTTPException(status_code=409, detail="Rule evidence is no longer verifiable against its source passage.")
    rule.status = "approved"
    rule.reviewed_by = user.email
    _audit_change(db, user.email, "regulatory_rule_approved", "regulatory_rule", rule.id,
                  {"rule_id": rule.rule_id, "version": rule.version})
    db.commit()
    db.refresh(rule)
    return _read_rule(rule)


@router.post("/rules/{rule_version_id}/activate", response_model=RegulatoryRuleRead)
def activate_rule(
    rule_version_id: str,
    _payload: RuleTransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_rule_manager),
) -> RegulatoryRuleRead:
    rule = db.get(RegulatoryRule, rule_version_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule version not found.")
    source = _source_or_404(db, rule.source_id)
    if rule.status != "approved":
        raise HTTPException(status_code=409, detail="Only approved rule versions can be activated.")
    if source.status != "verified" or source.document_version != rule.source_version:
        raise HTTPException(status_code=409, detail="The source changed or is not verified; rule requires re-review.")
    previous = db.scalars(
        select(RegulatoryRule).where(
            RegulatoryRule.rule_id == rule.rule_id,
            RegulatoryRule.status == "active",
        )
    ).all()
    for prior in previous:
        prior.status = "retired"
        _audit_change(db, user.email, "regulatory_rule_retired_on_replacement", "regulatory_rule", prior.id,
                      {"rule_id": prior.rule_id, "version": prior.version,
                       "replaced_by_version": rule.version})
    rule.status = "active"
    rule.reviewed_by = user.email
    _audit_change(db, user.email, "regulatory_rule_activated", "regulatory_rule", rule.id,
                  {"rule_id": rule.rule_id, "version": rule.version})
    db.commit()
    db.refresh(rule)
    return _read_rule(rule)


@router.post("/rules/{rule_version_id}/revise", response_model=RegulatoryRuleRead, status_code=201)
def revise_rule(
    rule_version_id: str,
    payload: RuleRevisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_rule_manager),
) -> RegulatoryRuleRead:
    prior = db.get(RegulatoryRule, rule_version_id)
    if prior is None:
        raise HTTPException(status_code=404, detail="Rule version not found.")
    if prior.status not in {"approved", "active", "retired"}:
        raise HTTPException(status_code=409, detail="Only reviewed rules can be revised.")
    target_source = _source_or_404(db, payload.source_id or prior.source_id)
    passage_id = payload.passage_id or prior.source_passage_id
    passage = db.get(RegulatorySourcePassage, passage_id)
    if (
        passage is None
        or passage.source_id != target_source.id
        or payload.page_number != passage.page_number
        or payload.supporting_quotation not in passage.text
    ):
        raise HTTPException(status_code=422, detail="Revised rule evidence must exactly match its cited source passage.")
    if target_source.status != "verified":
        raise HTTPException(status_code=409, detail="The revised rule requires a verified source version.")
    latest = db.scalar(
        select(RegulatoryRule.version).where(RegulatoryRule.rule_id == prior.rule_id)
        .order_by(RegulatoryRule.version.desc()).limit(1)
    ) or prior.version
    revision = RegulatoryRule(
        rule_id=prior.rule_id,
        version=latest + 1,
        source_id=target_source.id,
        source_version=target_source.document_version,
        source_passage_id=passage.id,
        **payload.model_dump(exclude={"source_id", "passage_id"}),
        status="manual_review" if payload.uncertainty_notes else "draft",
        created_by=user.email,
        is_demo=prior.is_demo,
    )
    db.add(revision)
    db.flush()
    _audit_change(db, user.email, "regulatory_rule_revised", "regulatory_rule", revision.id,
                  {"rule_id": revision.rule_id, "version": revision.version, "status": revision.status})
    db.commit()
    db.refresh(revision)
    return _read_rule(revision)


@router.post("/rules/{rule_version_id}/retire", response_model=RegulatoryRuleRead)
def retire_rule(
    rule_version_id: str,
    _payload: RuleTransitionRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_rule_manager),
) -> RegulatoryRuleRead:
    rule = db.get(RegulatoryRule, rule_version_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule version not found.")
    if rule.status not in {"approved", "active"}:
        raise HTTPException(status_code=409, detail="Only approved or active versions can be retired.")
    rule.status = "retired"
    _audit_change(db, _user.email, "regulatory_rule_retired", "regulatory_rule", rule.id,
                  {"rule_id": rule.rule_id, "version": rule.version})
    db.commit()
    db.refresh(rule)
    return _read_rule(rule)


@router.put("/categories", response_model=CategoryConfigureRequest)
def configure_category(
    payload: CategoryConfigureRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_rule_manager),
) -> CategoryConfigureRequest:
    category = db.get(RegulatoryCategoryConfig, payload.application_category)
    if category is None:
        category = RegulatoryCategoryConfig(
            application_category=payload.application_category,
            enabled=payload.enabled,
            configured_by=user.email,
        )
        db.add(category)
    else:
        category.enabled = payload.enabled
        category.configured_by = user.email
    _audit_change(db, user.email, "regulatory_category_configured", "category_config",
                  payload.application_category, {"enabled": payload.enabled})
    db.commit()
    return payload


@router.get("/checklists/{application_category}", response_model=ChecklistRead)
def get_category_checklist(
    application_category: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ChecklistRead:
    from app.schemas import ApplicationCategory

    if application_category not in ApplicationCategory.__args__ or not application_category:
        raise HTTPException(status_code=422, detail="Unknown application category.")
    config = db.get(RegulatoryCategoryConfig, application_category)
    if config is None or not config.enabled:
        return ChecklistRead(application_category=application_category, configured=False, items=[])
    rows = db.execute(
        select(RegulatoryRule, RegulatorySource)
        .join(RegulatorySource, RegulatorySource.id == RegulatoryRule.source_id)
        .where(
            RegulatoryRule.application_category == application_category,
            RegulatoryRule.status == "active",
            RegulatorySource.status == "verified",
            RegulatoryRule.source_version == RegulatorySource.document_version,
        )
        .order_by(RegulatoryRule.rule_id)
    ).all()
    items = [
        ChecklistItem(
            rule_id=rule.rule_id,
            version=rule.version,
            title=rule.rule_title,
            requirement=rule.requirement,
            required_evidence=rule.required_evidence,
            supporting_quotation=rule.supporting_quotation,
            source_title=source.title,
            source_version=rule.source_version,
            page_number=rule.page_number,
            classification="demo" if rule.is_demo else "verified_regulatory",
        )
        for rule, source in rows
    ]
    return ChecklistRead(application_category=application_category, configured=True, items=items)
