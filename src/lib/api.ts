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
export const me = () => api<User>("/api/auth/me");
export const listApplications = () => api<Application[]>("/api/applications");
export const getApplication = (id: string) => api<Application>(`/api/applications/${encodeURIComponent(id)}`);
export const createApplication = (payload: Pick<Application, "institution_id" | "institution_name" | "category" | "reference_number" | "submitted_at" | "declared_faculty_count">) => api<Application>("/api/applications", { method: "POST", body: JSON.stringify(payload) });
export const listDocuments = (id: string) => api<Document[]>(`/api/applications/${encodeURIComponent(id)}/documents`);
export function uploadDocument(id: string, category: string, file: File) {
  const form = new FormData(); form.set("category", category); form.set("file", file);
  return api<Document>(`/api/applications/${encodeURIComponent(id)}/documents`, { method: "POST", body: form });
}
export const runValidation = (id: string) => api<ValidationRun>(`/api/applications/${encodeURIComponent(id)}/validation-runs`, { method: "POST" });
export const listValidationRuns = (id: string) => api<ValidationRun[]>(`/api/applications/${encodeURIComponent(id)}/validation-runs`);
export const listFindings = (id: string) => api<Finding[]>(`/api/applications/${encodeURIComponent(id)}/findings`);
