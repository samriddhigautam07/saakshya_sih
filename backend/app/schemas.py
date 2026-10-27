"""Pydantic request and response schemas for application APIs."""

from datetime import date, datetime
from ipaddress import ip_address
from urllib.parse import urlsplit
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import UserRole

ApplicationCategory = Literal[
    "New Institution", "Extension of Approval", "Increase in Intake", "Change of Name", ""
]
DocumentCategory = Literal[
    "affiliation_certificate",
    "fire_safety",
    "building_completion",
    "faculty_list",
    "land_document",
    "audited_accounts",
]
ProcessingStatus = Literal[
    "Declared – file pending", "Awaiting manual fields", "Ready for validation", "Upload error"
]
ExtractionStatus = Literal[
    "not_processed",
    "text_extracted",
    "text_extracted_with_scanned_pages",
    "scanned_ocr_unavailable",
    "empty",
    "encrypted",
    "corrupt",
    "failed",
    "text_truncated",
    "text_extracted_with_ocr",
    "ocr_unavailable",
    "ocr_page_limit_exceeded",
    "ocr_page_too_large",
    "ocr_partial_failure",
    "processing_timeout",
    "page_limit_exceeded",
]
StructuredExtractionStatus = Literal[
    "complete",
    "partial",
    "uncertain",
    "no_fields_found",
    "no_text",
    "provider_unavailable",
    "provider_error",
    "invalid_output",
    "invalid_evidence",
    "input_too_large",
]
FieldSource = Literal["manual", "synthetic", "none"]
VerificationStatus = Literal[
    "Verified",
    "Mismatch Detected",
    "Expired",
    "Verification Pending",
    "Source Unavailable",
    "Manual Review Required",
]
FindingStatus = Literal["Open", "Under Review", "Resolved", "Escalated"]
Severity = Literal["High", "Medium", "Low"]


class ApiSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_email_shape(self) -> "LoginRequest":
        normalized = self.email.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address.")
        object.__setattr__(self, "email", normalized)
        return self


class InstitutionRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def validate_email_shape(self) -> "InstitutionRegistrationRequest":
        normalized = self.email.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address.")
        object.__setattr__(self, "email", normalized)
        return self


class UserRead(ApiSchema):
    id: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(ApiSchema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead


class DocumentMetadataCreate(ApiSchema):
    category: DocumentCategory
    filename: str | None = Field(default=None, max_length=512)
    sha256: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")
    size_bytes: int | None = Field(default=None, ge=0)
    uploaded_at: datetime | None = None
    processing_status: ProcessingStatus = "Declared – file pending"
    field_source: FieldSource = "none"
    issuer: str = Field(default="", max_length=300)
    document_number: str = Field(default="", max_length=200)
    issue_date: date | None = None
    expiry_date: date | None = None
    institution_id_on_doc: str = Field(default="", max_length=100)


class DocumentMetadataRead(DocumentMetadataCreate):
    id: str
    application_id: str
    created_at: datetime
    processing_status: str
    extraction_status: ExtractionStatus
    extracted_at: datetime | None
    duplicate_hash_detected: bool
    extracted_text_char_count: int
    content_available: bool


class DocumentCorrectionRead(BaseModel):
    id: str
    application_id: str
    document_id: str
    version: int
    filename: str
    sha256: str
    size_bytes: int
    extraction_status: ExtractionStatus
    extracted_text_char_count: int
    uploaded_by: str
    uploaded_at: datetime
    structured_extraction_status: StructuredExtractionStatus | None = None


class ReviewerFindingDecisionCreate(BaseModel):
    decision: Literal["confirmed_issue", "dismissed_finding", "clarification_required"]
    reason: str = Field(min_length=3, max_length=4000)


class ReviewerFindingDecisionRead(BaseModel):
    id: str
    application_id: str
    finding_id: str
    decision: Literal["confirmed_issue", "dismissed_finding", "clarification_required"]
    previous_status: FindingStatus | None
    status: FindingStatus
    actor: str
    reason: str
    created_at: datetime


class AuditHistoryEntry(BaseModel):
    id: str
    application_id: str | None
    actor: str
    event_type: str
    entity_type: str
    entity_id: str
    details: dict
    created_at: datetime


class ReportRuleReference(BaseModel):
    rule_id: str
    version: int
    title: str
    source_title: str
    source_version: str
    clause_reference: str | None
    annexure_reference: str | None
    page_number: int
    supporting_quotation: str


class ApplicationReviewReport(BaseModel):
    report_type: Literal["prototype_review_support"] = "prototype_review_support"
    disclaimer: str = "This report is review support only and is not an official AICTE decision."
    application: dict
    synthetic_data: bool
    latest_validation_run: dict | None
    applicable_rule_references: list[ReportRuleReference]
    findings: list[dict]
    verification_status: list[dict]
    mock_verification_present: bool
    reviewer_decisions: list[dict]


class ExtractedTextRead(BaseModel):
    document_id: str
    extraction_status: ExtractionStatus
    text: str


class _EvidenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: str | None = Field(default=None, min_length=1, max_length=1200)
    page_number: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class TextEvidenceValue(_EvidenceValue):
    value: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_evidence_pair(self) -> "TextEvidenceValue":
        _validate_value_evidence(self.value, self.evidence, self.page_number)
        return self


class DateEvidenceValue(_EvidenceValue):
    value: date | None = None

    @model_validator(mode="after")
    def validate_evidence_pair(self) -> "DateEvidenceValue":
        _validate_value_evidence(self.value, self.evidence, self.page_number)
        return self


class IntegerEvidenceValue(_EvidenceValue):
    value: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_evidence_pair(self) -> "IntegerEvidenceValue":
        _validate_value_evidence(self.value, self.evidence, self.page_number)
        return self


def _validate_value_evidence(value: object, evidence: str | None, page_number: int | None) -> None:
    if value is not None and not evidence:
        raise ValueError("Every extracted value requires an evidence snippet.")
    if value is None and (evidence is not None or page_number is not None):
        raise ValueError("Evidence and page references must be omitted when a value is unknown.")


class ExtractedDocumentFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution_name: TextEvidenceValue = Field(default_factory=TextEvidenceValue)
    institution_id: TextEvidenceValue = Field(default_factory=TextEvidenceValue)
    document_type: TextEvidenceValue = Field(default_factory=TextEvidenceValue)
    document_reference_number: TextEvidenceValue = Field(default_factory=TextEvidenceValue)
    issue_date: DateEvidenceValue = Field(default_factory=DateEvidenceValue)
    expiry_date: DateEvidenceValue = Field(default_factory=DateEvidenceValue)
    issuer: TextEvidenceValue = Field(default_factory=TextEvidenceValue)
    faculty_count: IntegerEvidenceValue = Field(default_factory=IntegerEvidenceValue)
    uncertainty: list[str] = Field(default_factory=list, max_length=30)


class RegulatorySourceCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    issuing_authority: str = Field(min_length=2, max_length=300)
    source_url: str | None = Field(default=None, max_length=2000)
    document_version: str = Field(min_length=1, max_length=120)
    publication_date: date | None = None
    effective_date: date | None = None
    retrieval_date: date = Field(default_factory=date.today)
    supersedes_source_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def validate_source_url(self) -> "RegulatorySourceCreate":
        if self.source_url is None:
            return self
        parsed = urlsplit(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Source URLs must be HTTPS URLs without embedded credentials.")
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".test")):
            raise ValueError("Private or local source URLs are not allowed.")
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if address is not None and (not address.is_global):
            raise ValueError("Private or non-public source URLs are not allowed.")
        return self


class RegulatorySourceRead(BaseModel):
    id: str
    supersedes_source_id: str | None
    title: str
    issuing_authority: str
    source_url: str | None
    original_filename: str | None
    document_version: str
    publication_date: date | None
    effective_date: date | None
    retrieval_date: date
    status: Literal["registered", "ingested", "verified", "inactive"]
    extraction_status: str
    passage_count: int = 0
    created_at: datetime


class RegulatorySourcePassageRead(BaseModel):
    id: str
    page_number: int
    text: str


class RuleProposalRequest(BaseModel):
    application_category: ApplicationCategory
    passage_id: str = Field(min_length=1, max_length=36)


class RuleDraftFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_title: str = Field(min_length=3, max_length=300)
    supporting_quotation: str = Field(min_length=10, max_length=4000)
    clause_reference: str | None = Field(default=None, max_length=200)
    annexure_reference: str | None = Field(default=None, max_length=200)
    page_number: int = Field(ge=1)
    application_category: ApplicationCategory
    requirement: str = Field(min_length=3, max_length=4000)
    conditions: list[str] = Field(default_factory=list, max_length=30)
    required_evidence: str = Field(min_length=2, max_length=300)
    validation_type: Literal["presence", "date", "numeric", "text_match", "manual_review"]
    validation_parameters: dict = Field(default_factory=dict)
    applicable_from: date | None = None
    applicable_until: date | None = None
    uncertainty_notes: list[str] = Field(default_factory=list, max_length=30)


class RegulatoryRuleRead(RuleDraftFields):
    id: str
    rule_id: str
    version: int
    source_id: str
    source_version: str
    status: Literal["draft", "manual_review", "approved", "active", "retired"]
    is_demo: bool
    created_by: str
    reviewed_by: str | None
    created_at: datetime
    updated_at: datetime


class RuleTransitionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RuleRevisionRequest(RuleDraftFields):
    source_id: str | None = Field(default=None, max_length=36)
    passage_id: str | None = Field(default=None, max_length=36)


class CategoryConfigureRequest(BaseModel):
    application_category: ApplicationCategory
    enabled: bool = True


class ChecklistItem(BaseModel):
    rule_id: str
    version: int
    title: str
    requirement: str
    required_evidence: str
    supporting_quotation: str
    source_title: str
    source_version: str
    page_number: int
    classification: Literal["verified_regulatory", "demo"]


class ChecklistRead(BaseModel):
    application_category: ApplicationCategory
    configured: bool
    items: list[ChecklistItem]


class DocumentExtractionRead(BaseModel):
    id: str
    document_id: str
    provider: str
    model: str | None
    status: StructuredExtractionStatus
    result: ExtractedDocumentFields | None
    error_message: str | None
    created_at: datetime


class VerificationRecordRead(ApiSchema):
    id: str
    application_id: str
    document_id: str | None
    status: VerificationStatus
    checked_at: datetime
    message: str
    provider: str
    is_mock: bool


class ValidationFindingRead(ApiSchema):
    id: str
    application_id: str
    document_id: str | None
    finding_key: str
    rule_id: str
    rule_name: str
    severity: Severity
    target: str
    expected: str | None
    actual: str | None
    rule_version: int | None = None
    status: FindingStatus = "Open"
    document_ids_json: list[str] = Field(default_factory=list)
    evidence_json: list[dict] = Field(default_factory=list)
    resolution_type: Literal["resolved_by_new_evidence", "dismissed_by_reviewer"] | None = None
    message: str
    recommendation: str
    created_at: datetime
    updated_at: datetime


class ValidationRunResultRead(BaseModel):
    id: str
    run_id: str
    finding_id: str | None
    issue_key: str
    source_kind: Literal["regulatory", "cross_document", "institution_reference"]
    rule_id: str
    rule_version: int | None
    rule_name: str
    result_status: Literal["pass", "mismatch", "unable_to_verify", "manual_review"]
    severity: Severity
    expected: str | None
    actual: str | None
    document_ids_json: list[str]
    evidence_json: list[dict]
    revalidation_state: Literal["newly_detected", "persistent", "resolved_by_new_evidence"] | None = None
    message: str
    created_at: datetime


class ValidationRunRead(BaseModel):
    id: str
    application_id: str
    actor: str
    status: Literal["completed", "completed_with_manual_review", "no_verified_rules"]
    summary_json: dict
    results: list[ValidationRunResultRead] = Field(default_factory=list)
    created_at: datetime


class ReviewerDecisionRead(ApiSchema):
    id: str
    application_id: str
    finding_id: str | None
    status: FindingStatus
    decision_type: Literal["confirmed_issue", "dismissed_finding", "clarification_required"] | None = None
    previous_status: FindingStatus | None
    actor: str
    note: str | None
    created_at: datetime


class AuditLogRead(ApiSchema):
    id: str
    application_id: str
    finding_id: str | None
    actor: str
    action: str
    note: str | None
    created_at: datetime


class ApplicationCreate(ApiSchema):
    institution_id: str = Field(default="", max_length=100)
    institution_name: str = Field(default="", max_length=300)
    category: ApplicationCategory = ""
    reference_number: str = Field(default="", max_length=120)
    submitted_at: date = Field(default_factory=date.today)
    declared_faculty_count: int | None = Field(default=None, ge=0)
    documents: list[DocumentMetadataCreate] = Field(default_factory=list)


class ApplicationPatch(ApiSchema):
    institution_id: str | None = Field(default=None, max_length=100)
    institution_name: str | None = Field(default=None, max_length=300)
    category: ApplicationCategory | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    submitted_at: date | None = None
    declared_faculty_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def require_patch_fields(cls, value: object) -> object:
        if isinstance(value, dict) and not value:
            raise ValueError("At least one application field must be provided.")
        return value

    @model_validator(mode="after")
    def reject_null_for_nonnullable_fields(self) -> "ApplicationPatch":
        for field in self.model_fields_set - {"declared_faculty_count"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class ApplicationRead(ApiSchema):
    id: str
    institution_id: str
    institution_name: str
    category: ApplicationCategory
    reference_number: str
    submitted_at: date
    declared_faculty_count: int | None
    owner_user_id: str | None
    created_at: datetime
    updated_at: datetime
    documents: list[DocumentMetadataRead]
    findings: list[ValidationFindingRead]
    verification_records: list[VerificationRecordRead]
    reviewer_decisions: list[ReviewerDecisionRead]
    audit_logs: list[AuditLogRead]


class ReviewerDecisionCreate(BaseModel):
    finding_id: str = Field(min_length=1, max_length=64)
    status: FindingStatus
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_resolution_reason(self) -> "ReviewerDecisionCreate":
        if self.status in {"Resolved", "Escalated"} and not (self.note and self.note.strip()):
            raise ValueError("A note is required when resolving or escalating a finding.")
        return self
