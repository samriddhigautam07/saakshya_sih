"""SQLAlchemy persistence models for applications and related review data."""

from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(StrEnum):
    APPLICANT = "Applicant / Institution"
    OFFICIAL_REVIEWER = "Official Reviewer"
    RULES_MANAGER = "Rules Manager / Administrator"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Applicant / Institution', 'Official Reviewer', 'Rules Manager / Administrator')",
            name="ck_users_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    owned_applications: Mapped[list["ApplicationRecord"]] = relationship(
        back_populates="owner", foreign_keys="ApplicationRecord.owner_user_id"
    )


class ApplicationRecord(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "declared_faculty_count IS NULL OR declared_faculty_count >= 0",
            name="ck_applications_faculty_nonnegative",
        ),
        Index(
            "uq_applications_reference_number_nonempty",
            "reference_number",
            unique=True,
            sqlite_where=text("reference_number <> ''"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    institution_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    reference_number: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    submitted_at: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    declared_faculty_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Nullable for existing Phase 2 records; these legacy unowned records are staff-only.
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    documents: Mapped[list["DocumentMetadata"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="DocumentMetadata.created_at"
    )
    document_corrections: Mapped[list["DocumentCorrection"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="DocumentCorrection.created_at"
    )
    findings: Mapped[list["ValidationFinding"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ValidationFinding.created_at"
    )
    verification_records: Mapped[list["VerificationRecord"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="VerificationRecord.checked_at"
    )
    reviewer_decisions: Mapped[list["ReviewerDecision"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ReviewerDecision.created_at"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="AuditLog.created_at"
    )
    owner: Mapped[User | None] = relationship(back_populates="owned_applications", foreign_keys=[owner_user_id])


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"
    __table_args__ = (
        UniqueConstraint("application_id", "category", name="uq_document_app_category"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_document_size_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(80), default="not_processed", nullable=False)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duplicate_hash_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(80), default="Declared – file pending", nullable=False)
    field_source: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    issuer: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    document_number: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    institution_id_on_doc: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application: Mapped[ApplicationRecord] = relationship(back_populates="documents")
    verification_records: Mapped[list["VerificationRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="VerificationRecord.checked_at"
    )
    findings: Mapped[list["ValidationFinding"]] = relationship(back_populates="document")
    structured_extractions: Mapped[list["DocumentExtractionRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentExtractionRecord.created_at"
    )
    corrections: Mapped[list["DocumentCorrection"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentCorrection.created_at"
    )

    @property
    def extracted_text_char_count(self) -> int:
        return len(self.extracted_text or "")

    @property
    def content_available(self) -> bool:
        return self.storage_key is not None


class DocumentExtractionRecord(Base):
    __tablename__ = "document_extraction_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('complete', 'partial', 'uncertain', 'no_fields_found', 'no_text', "
            "'provider_unavailable', 'provider_error', 'invalid_output', 'invalid_evidence', 'input_too_large')",
            name="ck_document_extraction_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document_metadata.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    document: Mapped[DocumentMetadata] = relationship(back_populates="structured_extractions")


class DocumentCorrection(Base):
    __tablename__ = "document_corrections"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_document_correction_size"),
        UniqueConstraint("document_id", "version", name="uq_document_correction_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document_metadata.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(80), nullable=False)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(254), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application: Mapped[ApplicationRecord] = relationship(back_populates="document_corrections")
    document: Mapped[DocumentMetadata] = relationship(back_populates="corrections")
    structured_extractions: Mapped[list["DocumentCorrectionExtraction"]] = relationship(
        back_populates="correction", cascade="all, delete-orphan", order_by="DocumentCorrectionExtraction.created_at"
    )


class DocumentCorrectionExtraction(Base):
    __tablename__ = "document_correction_extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    correction_id: Mapped[str] = mapped_column(
        ForeignKey("document_corrections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    correction: Mapped[DocumentCorrection] = relationship(back_populates="structured_extractions")


class ValidationFinding(Base):
    __tablename__ = "validation_findings"
    __table_args__ = (
        UniqueConstraint("application_id", "finding_key", name="uq_finding_key_per_application"),
        CheckConstraint("severity IN ('High', 'Medium', 'Low')", name="ck_finding_severity"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_metadata.id", ondelete="SET NULL"), nullable=True
    )
    finding_key: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(300), nullable=False)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="Open", nullable=False)
    document_ids_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resolution_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    application: Mapped[ApplicationRecord] = relationship(back_populates="findings")
    document: Mapped[DocumentMetadata | None] = relationship(back_populates="findings")
    reviewer_decisions: Mapped[list["ReviewerDecision"]] = relationship(back_populates="finding")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="finding")


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'completed_with_manual_review', 'no_verified_rules')",
            name="ck_validation_run_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ValidationRunResult(Base):
    __tablename__ = "validation_run_results"
    __table_args__ = (
        UniqueConstraint("run_id", "issue_key", name="uq_validation_result_per_run"),
        CheckConstraint(
            "result_status IN ('pass', 'mismatch', 'unable_to_verify', 'manual_review')",
            name="ck_validation_result_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("validation_findings.id", ondelete="SET NULL"), index=True, nullable=True
    )
    issue_key: Mapped[str] = mapped_column(String(240), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_name: Mapped[str] = mapped_column(String(300), nullable=False)
    result_status: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_ids_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    revalidation_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class VerificationRecord(Base):
    __tablename__ = "verification_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Verified', 'Mismatch Detected', 'Expired', "
            "'Verification Pending', 'Source Unavailable', 'Manual Review Required')",
            name="ck_verification_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_metadata.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    is_mock: Mapped[bool] = mapped_column(default=True, nullable=False)

    application: Mapped[ApplicationRecord] = relationship(back_populates="verification_records")
    document: Mapped[DocumentMetadata | None] = relationship(back_populates="verification_records")


class ReviewerDecision(Base):
    __tablename__ = "reviewer_decisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Open', 'Under Review', 'Resolved', 'Escalated')", name="ck_decision_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("validation_findings.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    decision_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    previous_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor: Mapped[str] = mapped_column(String(200), default="Reviewer (demo)", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application: Mapped[ApplicationRecord] = relationship(back_populates="reviewer_decisions")
    finding: Mapped[ValidationFinding | None] = relationship(back_populates="reviewer_decisions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("validation_findings.id", ondelete="SET NULL"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application: Mapped[ApplicationRecord] = relationship(back_populates="audit_logs")
    finding: Mapped[ValidationFinding | None] = relationship(back_populates="audit_logs")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "application_id IS NOT NULL OR entity_type IN ('regulatory_source', 'regulatory_rule', 'category_config')",
            name="ck_audit_event_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), index=True, nullable=True
    )
    actor: Mapped[str] = mapped_column(String(254), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class InstitutionalReferenceRecord(Base):
    __tablename__ = "institutional_reference_records"
    __table_args__ = (
        CheckConstraint("faculty_count >= 0", name="ck_institution_faculty_nonnegative"),
    )

    institution_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    faculty_count: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    source_label: Mapped[str] = mapped_column(String(120), default="synthetic", nullable=False)
    is_authorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RegulatorySource(Base):
    __tablename__ = "regulatory_sources"
    __table_args__ = (
        CheckConstraint("status IN ('registered', 'ingested', 'verified', 'inactive')", name="ck_reg_source_status"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_reg_source_size"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    supersedes_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("regulatory_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    issuing_authority: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_version: Mapped[str] = mapped_column(String(120), nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieval_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="registered", nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(80), default="not_processed", nullable=False)
    registered_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    passages: Mapped[list["RegulatorySourcePassage"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", order_by="RegulatorySourcePassage.page_number"
    )


class RegulatorySourcePassage(Base):
    __tablename__ = "regulatory_source_passages"
    __table_args__ = (UniqueConstraint("source_id", "page_number", name="uq_reg_source_page"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    source: Mapped[RegulatorySource] = relationship(back_populates="passages")


class RegulatoryRule(Base):
    __tablename__ = "regulatory_rules"
    __table_args__ = (
        UniqueConstraint("rule_id", "version", name="uq_reg_rule_version"),
        CheckConstraint("version >= 1", name="ck_reg_rule_version_positive"),
        CheckConstraint(
            "status IN ('draft', 'manual_review', 'approved', 'active', 'retired')", name="ck_reg_rule_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_sources.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source_version: Mapped[str] = mapped_column(String(120), nullable=False)
    source_passage_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_source_passages.id", ondelete="RESTRICT"), nullable=False
    )
    rule_title: Mapped[str] = mapped_column(String(300), nullable=False)
    supporting_quotation: Mapped[str] = mapped_column(Text, nullable=False)
    clause_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    annexure_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    application_category: Mapped[str] = mapped_column(String(100), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_evidence: Mapped[str] = mapped_column(String(300), nullable=False)
    validation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    validation_parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    applicable_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    applicable_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    uncertainty_notes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RegulatoryCategoryConfig(Base):
    __tablename__ = "regulatory_category_configs"

    application_category: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configured_by: Mapped[str] = mapped_column(String(254), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
