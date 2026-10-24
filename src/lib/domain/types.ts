export type ApplicationCategory =
  | "New Institution"
  | "Extension of Approval"
  | "Increase in Intake"
  | "Change of Name";

export const APPLICATION_CATEGORIES: ApplicationCategory[] = [
  "New Institution",
  "Extension of Approval",
  "Increase in Intake",
  "Change of Name",
];

export type DocCategory =
  | "affiliation_certificate"
  | "fire_safety"
  | "building_completion"
  | "faculty_list"
  | "land_document"
  | "audited_accounts";

export const DOC_CATEGORY_LABELS: Record<DocCategory, string> = {
  affiliation_certificate: "Affiliation Certificate",
  fire_safety: "Fire Safety Certificate",
  building_completion: "Building Completion Certificate",
  faculty_list: "Faculty List",
  land_document: "Land Ownership Document",
  audited_accounts: "Audited Accounts Statement",
};

export const DOC_CATEGORIES = Object.keys(DOC_CATEGORY_LABELS) as DocCategory[];

export type ProcessingStatus =
  | "Declared – file pending"
  | "Awaiting manual fields"
  | "Ready for validation"
  | "Upload error";

export type VerificationStatus =
  | "Verified"
  | "Mismatch Detected"
  | "Expired"
  | "Verification Pending"
  | "Source Unavailable"
  | "Manual Review Required";

export interface VerificationResult {
  status: VerificationStatus;
  checkedAt: string;
  message: string;
  mock: true;
}

export interface AppDocument {
  id: string;
  category: DocCategory;
  filename: string | null;
  sha256: string | null;
  sizeBytes: number | null;
  uploadedAt: string | null;
  processingStatus: ProcessingStatus;
  /** Fields are entered manually or come from synthetic data — PDF text extraction is not implemented. */
  fieldSource: "manual" | "synthetic" | "none";
  issuer: string;
  documentNumber: string;
  issueDate: string | null;
  expiryDate: string | null;
  institutionIdOnDoc: string;
  verification: VerificationResult | null;
}

export type FindingStatus = "Open" | "Under Review" | "Resolved" | "Escalated";
export const FINDING_STATUSES: FindingStatus[] = ["Open", "Under Review", "Resolved", "Escalated"];

export type Severity = "High" | "Medium" | "Low";

export interface Finding {
  id: string;
  ruleId: string;
  ruleName: string;
  severity: Severity;
  target: string;
  expected?: string;
  actual?: string;
  message: string;
  recommendation: string;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
  findingId?: string;
  from?: string;
  to?: string;
  note?: string;
}

export interface Application {
  id: string;
  institutionId: string;
  institutionName: string;
  category: ApplicationCategory | "";
  referenceNumber: string;
  submittedAt: string;
  declaredFacultyCount: number | null;
  documents: AppDocument[];
  findingStatuses: Record<string, FindingStatus>;
  audit: AuditEntry[];
}

export interface InstitutionRecord {
  institutionId: string;
  name: string;
  facultyCount: number;
  state: string;
}

export interface ValidationConfig {
  checklist: Record<ApplicationCategory, DocCategory[]>;
  mandatoryFields: (keyof Application)[];
  expiryWarningDays: number;
}
