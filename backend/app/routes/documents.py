"""Private document upload, metadata, content, and extracted-text endpoints."""

import hashlib
import os
from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.dependencies import get_db
from app.file_storage import (
    create_temporary_file,
    new_storage_key,
    resolve_storage_key,
)
from app.models import (
    ApplicationRecord,
    AuditEvent,
    AuditLog,
    DocumentCorrection,
    DocumentCorrectionExtraction,
    DocumentExtractionRecord,
    DocumentMetadata,
    User,
    UserRole,
    utc_now,
)
from app.pdf_extraction import extract_pdf_text
from app.schemas import (
    DocumentCategory,
    DocumentExtractionRead,
    DocumentMetadataRead,
    DocumentCorrectionRead,
    ExtractedDocumentFields,
    ExtractedTextRead,
)
from app.structured_extraction import StructuredDocumentExtractionService

router = APIRouter(prefix="/api/applications/{application_id}/documents", tags=["documents"])
PDF_SIGNATURE = b"%PDF-"
CHUNK_SIZE = 64 * 1024
SAFE_FILENAME_CHARS = re.compile(r"[^\w .()\-]+", flags=re.UNICODE)


def _authorized_application(application_id: str, user: User, db: Session) -> ApplicationRecord:
    if user.role == UserRole.APPLICANT:
        application = db.scalar(
            select(ApplicationRecord).where(
                ApplicationRecord.id == application_id,
                ApplicationRecord.owner_user_id == user.id,
            )
        )
    elif user.role == UserRole.OFFICIAL_REVIEWER:
        application = db.get(ApplicationRecord, application_id)
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions to access application documents.")
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


def _display_filename(client_filename: str | None) -> str:
    if not client_filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    basename = client_filename.replace("\\", "/").split("/")[-1]
    cleaned = SAFE_FILENAME_CHARS.sub("_", basename).strip(" .")[:512]
    if not cleaned:
        raise HTTPException(status_code=400, detail="A filename is required.")
    return cleaned


async def _read_to_private_temp(upload: UploadFile, storage_root: Path, max_bytes: int) -> tuple[Path, int, str]:
    descriptor, temporary_path = create_temporary_file(storage_root)
    digest = hashlib.sha256()
    size = 0
    header = bytearray()
    try:
        with os.fdopen(descriptor, "wb") as destination:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail="PDF exceeds the configured upload size limit.")
                if len(header) < len(PDF_SIGNATURE):
                    header.extend(chunk[: len(PDF_SIGNATURE) - len(header)])
                digest.update(chunk)
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if bytes(header) != PDF_SIGNATURE:
            raise HTTPException(status_code=415, detail="The file does not have a valid PDF signature.")
        return temporary_path, size, digest.hexdigest()
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


@router.post("", response_model=DocumentMetadataRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    application_id: str,
    request: Request,
    category: DocumentCategory = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentMetadata:
    application = _authorized_application(application_id, user, db)
    display_filename = _display_filename(file.filename)
    if Path(display_filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only .pdf files are accepted.")
    content_type = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if content_type and content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="The uploaded MIME type must be application/pdf.")

    storage_root: Path = request.app.state.storage_root
    temporary_path: Path | None = None
    final_path: Path | None = None
    try:
        temporary_path, size_bytes, file_hash = await _read_to_private_temp(
            file, storage_root, request.app.state.settings.max_document_size_bytes
        )
        extraction = extract_pdf_text(
            temporary_path,
            request.app.state.settings.max_extracted_text_chars,
            max_pages=request.app.state.settings.pdf_max_pages,
            ocr_max_pages=request.app.state.settings.ocr_max_pages,
            ocr_dpi=request.app.state.settings.ocr_dpi,
            ocr_min_digital_chars=request.app.state.settings.ocr_min_digital_chars,
            ocr_max_page_pixels=request.app.state.settings.ocr_max_page_pixels,
            ocr_page_timeout_seconds=request.app.state.settings.ocr_page_timeout_seconds,
            processing_timeout_seconds=request.app.state.settings.pdf_processing_timeout_seconds,
        )
        duplicate_hash = db.scalar(
            select(DocumentMetadata.id).where(DocumentMetadata.sha256 == file_hash).limit(1)
        ) is not None
        storage_key = new_storage_key()
        final_path = resolve_storage_key(storage_root, storage_key)
        os.link(temporary_path, final_path)
        temporary_path.unlink()
        temporary_path = None

        document = DocumentMetadata(
            application_id=application.id,
            category=category,
            filename=display_filename,
            storage_key=storage_key,
            sha256=file_hash,
            size_bytes=size_bytes,
            uploaded_at=utc_now(),
            processing_status="Upload error" if extraction.status in {"corrupt", "failed"} else "Awaiting manual fields",
            field_source="none",
            issuer="",
            document_number="",
            issue_date=None,
            expiry_date=None,
            institution_id_on_doc="",
            extracted_text=extraction.text,
            extraction_status=extraction.status,
            extracted_at=extraction.extracted_at,
            duplicate_hash_detected=duplicate_hash,
        )
        db.add(document)
        try:
            db.flush()
            db.add(AuditLog(actor=user.email, application_id=application.id, action=f"Uploaded document: {category}"))
            db.commit()
        except IntegrityError as error:
            db.rollback()
            final_path.unlink(missing_ok=True)
            final_path = None
            raise HTTPException(
                status_code=409,
                detail="A document in this category already exists for the application.",
            ) from error
        db.refresh(document)
        return document
    except HTTPException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="The document could not be stored safely.") from error
    except SQLAlchemyError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Document metadata could not be saved.") from error
    finally:
        await file.close()


def _correction_read(correction: DocumentCorrection) -> DocumentCorrectionRead:
    latest = max(correction.structured_extractions, key=lambda item: item.created_at, default=None)
    return DocumentCorrectionRead(
        id=correction.id,
        application_id=correction.application_id,
        document_id=correction.document_id,
        version=correction.version,
        filename=correction.filename,
        sha256=correction.sha256,
        size_bytes=correction.size_bytes,
        extraction_status=correction.extraction_status,
        extracted_text_char_count=len(correction.extracted_text),
        uploaded_by=correction.uploaded_by,
        uploaded_at=correction.uploaded_at,
        structured_extraction_status=latest.status if latest else None,
    )


@router.post("/{document_id}/corrections", response_model=DocumentCorrectionRead, status_code=201)
async def upload_document_correction(
    application_id: str,
    document_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentCorrectionRead:
    if user.role != UserRole.APPLICANT:
        raise HTTPException(status_code=403, detail="Only the owning Applicant / Institution can upload a correction.")
    application = _authorized_application(application_id, user, db)
    original = db.scalar(select(DocumentMetadata).where(
        DocumentMetadata.id == document_id,
        DocumentMetadata.application_id == application.id,
    ))
    if original is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    display_filename = _display_filename(file.filename)
    if Path(display_filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only .pdf files are accepted.")
    content_type = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if content_type and content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="The uploaded MIME type must be application/pdf.")

    storage_root: Path = request.app.state.storage_root
    temporary_path: Path | None = None
    final_path: Path | None = None
    try:
        temporary_path, size_bytes, file_hash = await _read_to_private_temp(
            file, storage_root, request.app.state.settings.max_document_size_bytes
        )
        extraction = extract_pdf_text(
            temporary_path,
            request.app.state.settings.max_extracted_text_chars,
            max_pages=request.app.state.settings.pdf_max_pages,
            ocr_max_pages=request.app.state.settings.ocr_max_pages,
            ocr_dpi=request.app.state.settings.ocr_dpi,
            ocr_min_digital_chars=request.app.state.settings.ocr_min_digital_chars,
            ocr_max_page_pixels=request.app.state.settings.ocr_max_page_pixels,
            ocr_page_timeout_seconds=request.app.state.settings.ocr_page_timeout_seconds,
            processing_timeout_seconds=request.app.state.settings.pdf_processing_timeout_seconds,
        )
        previous_version = db.scalar(
            select(DocumentCorrection.version)
            .where(DocumentCorrection.document_id == original.id)
            .order_by(DocumentCorrection.version.desc())
            .limit(1)
        ) or 0
        storage_key = new_storage_key()
        final_path = resolve_storage_key(storage_root, storage_key)
        os.link(temporary_path, final_path)
        temporary_path.unlink()
        temporary_path = None
        correction = DocumentCorrection(
            application_id=application.id,
            document_id=original.id,
            version=previous_version + 1,
            filename=display_filename,
            storage_key=storage_key,
            sha256=file_hash,
            size_bytes=size_bytes,
            extracted_text=extraction.text,
            extraction_status=extraction.status,
            extracted_at=extraction.extracted_at,
            uploaded_by=user.email,
            uploaded_at=utc_now(),
        )
        db.add(correction)
        db.flush()
        db.add(AuditLog(
            actor=user.email,
            application_id=application.id,
            action=f"Uploaded corrected document version {correction.version}: {original.category}",
        ))
        db.commit()
        db.refresh(correction)
        return _correction_read(correction)
    except HTTPException:
        db.rollback()
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    except (OSError, SQLAlchemyError) as error:
        db.rollback()
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="The corrected document could not be stored safely.") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()


@router.get("/{document_id}/corrections", response_model=list[DocumentCorrectionRead])
def list_document_corrections(
    application_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentCorrectionRead]:
    application = _authorized_application(application_id, user, db)
    original = db.scalar(select(DocumentMetadata).where(
        DocumentMetadata.id == document_id, DocumentMetadata.application_id == application.id
    ))
    if original is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    corrections = db.scalars(
        select(DocumentCorrection).where(DocumentCorrection.document_id == original.id)
        .order_by(DocumentCorrection.version.desc())
    ).all()
    return [_correction_read(item) for item in corrections]


@router.post("/{document_id}/corrections/{correction_id}/structured-extraction", response_model=DocumentExtractionRead, status_code=201)
async def extract_correction_fields(
    application_id: str,
    document_id: str,
    correction_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentExtractionRead:
    application = _authorized_application(application_id, user, db)
    correction = db.scalar(select(DocumentCorrection).where(
        DocumentCorrection.id == correction_id,
        DocumentCorrection.document_id == document_id,
        DocumentCorrection.application_id == application.id,
    ))
    if correction is None:
        raise HTTPException(status_code=404, detail="Corrected document not found.")
    original = db.get(DocumentMetadata, document_id)
    provider = request.app.state.llm_provider
    outcome = await StructuredDocumentExtractionService(
        provider, request.app.state.settings.max_llm_input_chars
    ).extract(correction.extracted_text, original.category)
    record = DocumentCorrectionExtraction(
        correction_id=correction.id,
        provider=provider.name if provider is not None else "unconfigured",
        model=provider.model if provider is not None else None,
        status=outcome.status,
        result_json=outcome.result.model_dump(mode="json") if outcome.result else None,
        error_message=outcome.error_message,
    )
    db.add(record)
    db.add(AuditEvent(
        application_id=application.id,
        actor=user.email,
        event_type="corrected_document_structured_extraction",
        entity_type="document_correction",
        entity_id=correction.id,
        details_json={"status": outcome.status},
    ))
    db.commit()
    db.refresh(record)
    return DocumentExtractionRead(
        id=record.id,
        document_id=correction.id,
        provider=record.provider,
        model=record.model,
        status=record.status,
        result=ExtractedDocumentFields.model_validate(record.result_json) if record.result_json else None,
        error_message=record.error_message,
        created_at=record.created_at,
    )


@router.get("", response_model=list[DocumentMetadataRead])
def list_documents(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentMetadata]:
    application = _authorized_application(application_id, user, db)
    return list(
        db.scalars(
            select(DocumentMetadata)
            .where(DocumentMetadata.application_id == application.id)
            .order_by(DocumentMetadata.created_at, DocumentMetadata.id)
        ).all()
    )


@router.get("/{document_id}/content")
def download_document(
    application_id: str,
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    application = _authorized_application(application_id, user, db)
    document = db.scalar(
        select(DocumentMetadata).where(
            DocumentMetadata.id == document_id,
            DocumentMetadata.application_id == application.id,
        )
    )
    if document is None or document.storage_key is None:
        raise HTTPException(status_code=404, detail="Document content not found.")
    try:
        path = resolve_storage_key(request.app.state.storage_root, document.storage_key)
    except ValueError:
        raise HTTPException(status_code=404, detail="Document content not found.") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document content not found.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.filename or "document.pdf",
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{document_id}/extracted-text", response_model=ExtractedTextRead)
def get_extracted_text(
    application_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExtractedTextRead:
    application = _authorized_application(application_id, user, db)
    document = db.scalar(
        select(DocumentMetadata).where(
            DocumentMetadata.id == document_id,
            DocumentMetadata.application_id == application.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return ExtractedTextRead(
        document_id=document.id,
        extraction_status=document.extraction_status,
        text=document.extracted_text or "",
    )


@router.post("/{document_id}/structured-extraction", response_model=DocumentExtractionRead, status_code=201)
async def extract_structured_fields(
    application_id: str,
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentExtractionRead:
    application = _authorized_application(application_id, user, db)
    document = db.scalar(
        select(DocumentMetadata).where(
            DocumentMetadata.id == document_id,
            DocumentMetadata.application_id == application.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    provider = request.app.state.llm_provider
    service = StructuredDocumentExtractionService(
        provider,
        request.app.state.settings.max_llm_input_chars,
    )
    outcome = await service.extract(document.extracted_text or "", document.category)
    provider_name = provider.name if provider is not None else "unconfigured"
    provider_model = provider.model if provider is not None else None
    record = DocumentExtractionRecord(
        document_id=document.id,
        provider=provider_name,
        model=provider_model,
        status=outcome.status,
        result_json=outcome.result.model_dump(mode="json") if outcome.result is not None else None,
        error_message=outcome.error_message,
    )
    db.add(record)
    db.add(
        AuditLog(
            actor=user.email,
            application_id=application.id,
            action=f"Structured document extraction: {outcome.status}",
        )
    )
    db.commit()
    db.refresh(record)
    return _record_read(record)


@router.get("/{document_id}/structured-extractions", response_model=list[DocumentExtractionRead])
def list_structured_extractions(
    application_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentExtractionRead]:
    application = _authorized_application(application_id, user, db)
    document = db.scalar(
        select(DocumentMetadata).where(
            DocumentMetadata.id == document_id,
            DocumentMetadata.application_id == application.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    records = db.scalars(
        select(DocumentExtractionRecord)
        .where(DocumentExtractionRecord.document_id == document.id)
        .order_by(DocumentExtractionRecord.created_at.desc(), DocumentExtractionRecord.id)
    ).all()
    return [_record_read(item) for item in records]


def _record_read(record: DocumentExtractionRecord) -> DocumentExtractionRead:
    return DocumentExtractionRead(
        id=record.id,
        document_id=record.document_id,
        provider=record.provider,
        model=record.model,
        status=record.status,
        result=ExtractedDocumentFields.model_validate(record.result_json) if record.result_json else None,
        error_message=record.error_message,
        created_at=record.created_at,
    )
