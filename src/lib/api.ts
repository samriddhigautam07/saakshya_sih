/** Typed browser client for the Phase 8 FastAPI API. */
export const API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] || "http://127.0.0.1:8000").replace(/\/$/, "");

export type Role = "Applicant / Institution" | "Official Reviewer" | "Rules Manager / Administrator";
export interface User { id: string; email: string; role: Role; is_active: boolean; created_at: string; updated_at: string }
export interface LoginResponse { access_token: string; token_type: "bearer"; expires_in: number; user: User }
export interface Document {
  id: string; application_id: string; category: string; filename: string | null; sha256: string | null;
  size_bytes: number | null; uploaded_at: string | null; processing_status: string; extraction_status: string;
  extracted_at: string | null; duplicate_hash_detected: boolean; extracted_text_char_count: number;
  content_available: boolean; field_source: string; issuer: string; document_number: string;
  issue_date: string | null; expiry_date: string | null; institution_id_on_doc: string;
}
export interface DocumentCorrection {
  id: string; application_id: string; document_id: string; version: number; filename: string;
  sha256: string; size_bytes: number; extraction_status: string; extracted_text_char_count: number;
  uploaded_by: string; uploaded_at: string; structured_extraction_status: string | null;
}
export interface Finding {
  id: string; application_id: string; document_id: string | null; finding_key: string; rule_id: string;
  rule_name: string; severity: "High" | "Medium" | "Low"; target: string; expected: string | null;
  actual: string | null; rule_version: number | null; status: string; document_ids_json: string[];
  evidence_json: Array<Record<string, unknown>>; resolution_type: string | null; message: string;
  recommendation: string; created_at: string; updated_at: string;
}
export interface Application {
  id: string; institution_id: string; institution_name: string;
  category: "New Institution" | "Extension of Approval" | "Increase in Intake" | "Change of Name" | "";
  reference_number: string; submitted_at: string; declared_faculty_count: number | null;
  owner_user_id: string | null; created_at: string; updated_at: string; documents: Document[];
  findings: Finding[]; reviewer_decisions: Array<Record<string, unknown>>; audit_logs: Array<Record<string, unknown>>;
}
export interface ValidationResult {
  id: string; run_id: string; finding_id: string | null; issue_key: string; source_kind: string;
  rule_id: string; rule_version: number | null; rule_name: string; result_status: string;
  severity: string; expected: string | null; actual: string | null; document_ids_json: string[];
  evidence_json: Array<Record<string, unknown>>; revalidation_state: string | null; message: string; created_at: string;
}
export interface ValidationRun {
  id: string; application_id: string; actor: string; status: string; summary_json: Record<string, number>;
  results: ValidationResult[]; created_at: string;
}

export interface ExtractedValue<T = string | number> { value: T | null; evidence: string | null; page_number: number | null; confidence: number | null }
export interface StructuredFields {
  institution_name: ExtractedValue; institution_id: ExtractedValue; document_type: ExtractedValue;
  document_reference_number: ExtractedValue; issue_date: ExtractedValue; expiry_date: ExtractedValue;
  issuer: ExtractedValue; faculty_count: ExtractedValue<number>; uncertainty: string[];
}
export interface DocumentExtraction {
  id: string; document_id: string; provider: string; model: string | null; status: string;
  result: StructuredFields | null; error_message: string | null; created_at: string;
}
export function newestDocumentExtraction(records: DocumentExtraction[]): DocumentExtraction | null {
  return records.reduce<DocumentExtraction | null>((newest, record) => {
    if (!newest) return record;
    return Date.parse(record.created_at) > Date.parse(newest.created_at) ? record : newest;
  }, null);
}
export interface ChecklistItem {
  rule_id: string; version: number; title: string; requirement: string; required_evidence: string;
  supporting_quotation: string; source_title: string; source_version: string; page_number: number;
  classification: "verified_regulatory" | "demo";
}
export interface Checklist { application_category: string; configured: boolean; items: ChecklistItem[] }
export interface RegulatorySource {
  id: string; supersedes_source_id: string | null; title: string; issuing_authority: string;
  source_url: string | null; original_filename: string | null; document_version: string;
  publication_date: string | null; effective_date: string | null; retrieval_date: string;
  status: "registered" | "ingested" | "verified" | "inactive"; extraction_status: string;
  passage_count: number; created_at: string;
}
export interface RegulatoryPassage { id: string; page_number: number; text: string }
export interface RegulatoryRule {
  id: string; rule_id: string; version: number; source_id: string; source_version: string;
  rule_title: string; supporting_quotation: string; clause_reference: string | null;
  annexure_reference: string | null; page_number: number; application_category: string;
  requirement: string; conditions: string[]; required_evidence: string; validation_type: string;
  validation_parameters: Record<string, unknown>; applicable_from: string | null; applicable_until: string | null;
  uncertainty_notes: string[]; is_demo: boolean; status: "draft" | "manual_review" | "approved" | "active" | "retired";
  created_by: string; reviewed_by: string | null; created_at: string; updated_at: string;
}
export interface RegulatorySourceCreate {
  title: string; issuing_authority: string; source_url?: string; document_version: string;
  publication_date?: string; effective_date?: string; retrieval_date?: string; supersedes_source_id?: string;
}
export type RuleDraftPayload = Pick<RegulatoryRule,
  "rule_title" | "supporting_quotation" | "clause_reference" | "annexure_reference" | "page_number" |
  "application_category" | "requirement" | "conditions" | "required_evidence" | "validation_type" |
  "validation_parameters" | "applicable_from" | "applicable_until" | "uncertainty_notes">;
export interface ReviewDecision {
  id: string; application_id: string; finding_id: string; decision: "confirmed_issue" | "dismissed_finding" | "clarification_required";
  previous_status: string; status: string; actor: string; reason: string; created_at: string;
}
export interface AuditEvent {
  id: string; application_id: string | null; actor: string; event_type: string; entity_type: string;
  entity_id: string; details: Record<string, unknown>; created_at: string;
}
export interface ReviewReport {
  report_type: "prototype_review_support"; disclaimer: string; application: Record<string, unknown>;
  synthetic_data: boolean; latest_validation_run: Record<string, unknown> | null;
  applicable_rule_references: Array<Record<string, unknown>>; findings: Array<Record<string, unknown>>;
  verification_status: Array<Record<string, unknown>>; mock_verification_present: boolean;
  reviewer_decisions: Array<Record<string, unknown>>;
}

let accessToken: string | null = null;
const subscribers = new Set<() => void>();
export function getToken() { return accessToken; }
export function setToken(token: string | null) { accessToken = token; subscribers.forEach((fn) => fn()); }
export function subscribeSession(fn: () => void) { subscribers.add(fn); return () => subscribers.delete(fn); }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = "ApiError"; }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try { response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers }); }
  catch {
    const pageOrigin = typeof window === "undefined" ? "this page" : window.location.origin;
    throw new ApiError(0, `The browser could not complete a request to ${API_BASE_URL} from ${pageOrigin}. Check that the backend is running, VITE_API_BASE_URL is correct, and backend CORS_ORIGINS allows this exact frontend origin.`);
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const payload = await response.json() as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
      else if (Array.isArray(payload.detail)) detail = payload.detail.map((item: { msg?: string; loc?: string[] }) => `${item.loc?.slice(-1)[0] ?? "Field"}: ${item.msg ?? "invalid value"}`).join("; ");
    } catch { /* use status message */ }
    if (response.status === 401) setToken(null);
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const login = (email: string, password: string) => api<LoginResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const registerInstitution = (email: string, password: string) => api<User>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
export const me = () => api<User>("/api/auth/me");
export const listApplications = () => api<Application[]>("/api/applications");
export const getApplication = (id: string) => api<Application>(`/api/applications/${encodeURIComponent(id)}`);
export const createApplication = (payload: Pick<Application, "institution_id" | "institution_name" | "category" | "reference_number" | "submitted_at" | "declared_faculty_count">) => api<Application>("/api/applications", { method: "POST", body: JSON.stringify(payload) });
export const listDocuments = (id: string) => api<Document[]>(`/api/applications/${encodeURIComponent(id)}/documents`);
export function uploadDocument(id: string, category: string, file: File) {
  const form = new FormData(); form.set("category", category); form.set("file", file);
  return api<Document>(`/api/applications/${encodeURIComponent(id)}/documents`, { method: "POST", body: form });
}
export function uploadDocumentCorrection(applicationId: string, documentId: string, file: File) {
  const form = new FormData(); form.set("file", file);
  return api<DocumentCorrection>(`/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(documentId)}/corrections`, { method: "POST", body: form });
}
export const listDocumentCorrections = (applicationId: string, documentId: string) => api<DocumentCorrection[]>(`/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(documentId)}/corrections`);
export const extractCorrectedDocumentFields = (applicationId: string, documentId: string, correctionId: string) => api<DocumentExtraction>(`/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(documentId)}/corrections/${encodeURIComponent(correctionId)}/structured-extraction`, { method: "POST" });
export const runValidation = (id: string) => api<ValidationRun>(`/api/applications/${encodeURIComponent(id)}/validation-runs`, { method: "POST" });
export const listValidationRuns = (id: string) => api<ValidationRun[]>(`/api/applications/${encodeURIComponent(id)}/validation-runs`);
export const listFindings = (id: string) => api<Finding[]>(`/api/applications/${encodeURIComponent(id)}/findings`);
export const extractDocumentFields = (applicationId: string, documentId: string) => api<DocumentExtraction>(`/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(documentId)}/structured-extraction`, { method: "POST" });
export const reprocessDocumentText = (applicationId: string, documentId: string) => api<Document>(`/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(documentId)}/reprocess-text`, { method: "POST" });
export const listDocumentExtractions = (applicationId: string, documentId: string) => api<DocumentExtraction[]>(`/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(documentId)}/structured-extractions`);
export const getCategoryChecklist = (category: string) => api<Checklist>(`/api/regulatory/checklists/${encodeURIComponent(category)}`);
export const listRegulatorySources = () => api<RegulatorySource[]>("/api/regulatory/sources");
export const registerRegulatorySource = (payload: RegulatorySourceCreate) => api<RegulatorySource>("/api/regulatory/sources", { method: "POST", body: JSON.stringify(payload) });
export function uploadRegulatorySource(sourceId: string, file: File) { const form = new FormData(); form.set("file", file); return api<RegulatorySource>(`/api/regulatory/sources/${encodeURIComponent(sourceId)}/upload`, { method: "POST", body: form }); }
export const listRegulatoryPassages = (sourceId: string) => api<RegulatoryPassage[]>(`/api/regulatory/sources/${encodeURIComponent(sourceId)}/passages`);
export const searchRegulatoryPassages = (sourceId: string, query: string) => api<RegulatoryPassage[]>(`/api/regulatory/sources/${encodeURIComponent(sourceId)}/search?query=${encodeURIComponent(query)}`);
export const verifyRegulatorySource = (sourceId: string) => api<RegulatorySource>(`/api/regulatory/sources/${encodeURIComponent(sourceId)}/verify`, { method: "POST" });
export const listRegulatoryRules = () => api<RegulatoryRule[]>("/api/regulatory/rules");
export const proposeRegulatoryRule = (sourceId: string, passageId: string, applicationCategory: string) => api<RegulatoryRule>(`/api/regulatory/sources/${encodeURIComponent(sourceId)}/proposals`, { method: "POST", body: JSON.stringify({ passage_id: passageId, application_category: applicationCategory }) });
const ruleTransition = (id: string, action: "approve" | "activate" | "retire") => api<RegulatoryRule>(`/api/regulatory/rules/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({}) });
export const approveRegulatoryRule = (id: string) => ruleTransition(id, "approve");
export const activateRegulatoryRule = (id: string) => ruleTransition(id, "activate");
export const retireRegulatoryRule = (id: string) => ruleTransition(id, "retire");
export const reviseRegulatoryRule = (id: string, payload: RuleDraftPayload) => api<RegulatoryRule>(`/api/regulatory/rules/${encodeURIComponent(id)}/revise`, { method: "POST", body: JSON.stringify(payload) });
export const configureRegulatoryCategory = (applicationCategory: string, enabled: boolean) => api<{ application_category: string; enabled: boolean }>("/api/regulatory/categories", { method: "PUT", body: JSON.stringify({ application_category: applicationCategory, enabled }) });
export const getRegulatoryAuditHistory = () => api<AuditEvent[]>("/api/audit-history");
export const listReviewRuns = listValidationRuns;
export const submitReviewDecision = (applicationId: string, findingId: string, decision: ReviewDecision["decision"], reason: string) => api<ReviewDecision>(`/api/applications/${encodeURIComponent(applicationId)}/findings/${encodeURIComponent(findingId)}/reviews`, { method: "POST", body: JSON.stringify({ decision, reason }) });
export const getFindingReviewHistory = (applicationId: string, findingId: string) => api<ReviewDecision[]>(`/api/applications/${encodeURIComponent(applicationId)}/findings/${encodeURIComponent(findingId)}/reviews`);
export const getApplicationAuditHistory = (applicationId: string) => api<AuditEvent[]>(`/api/applications/${encodeURIComponent(applicationId)}/audit-history`);
export const getApplicationReviewReport = (applicationId: string) => api<ReviewReport>(`/api/applications/${encodeURIComponent(applicationId)}/report`);
