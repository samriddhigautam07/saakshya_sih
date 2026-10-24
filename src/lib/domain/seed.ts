import type { AppDocument, Application, DocCategory, InstitutionRecord, ValidationConfig } from "./types";

/** SYNTHETIC institutional records used for cross-checks. Not real AICTE data. */
export const INSTITUTION_RECORDS: InstitutionRecord[] = [
  { institutionId: "SYN-INST-1001", name: "Demo Institute of Technology, Pune", facultyCount: 84, state: "Maharashtra" },
  { institutionId: "SYN-INST-1002", name: "Sample College of Engineering, Jaipur", facultyCount: 62, state: "Rajasthan" },
  { institutionId: "SYN-INST-1003", name: "Placeholder Polytechnic, Bhopal", facultyCount: 40, state: "Madhya Pradesh" },
  { institutionId: "SYN-INST-1004", name: "Mock School of Management, Kochi", facultyCount: 35, state: "Kerala" },
  { institutionId: "SYN-INST-1005", name: "Example Institute of Pharmacy, Lucknow", facultyCount: 96, state: "Uttar Pradesh" },
  { institutionId: "SYN-INST-1006", name: "Test Engineering Academy, Guwahati", facultyCount: 51, state: "Assam" },
];

export const DEFAULT_CONFIG: ValidationConfig = {
  checklist: {
    "New Institution": ["land_document", "building_completion", "fire_safety", "faculty_list"],
    "Extension of Approval": ["affiliation_certificate", "fire_safety", "faculty_list", "audited_accounts"],
    "Increase in Intake": ["affiliation_certificate", "building_completion", "faculty_list"],
    "Change of Name": ["affiliation_certificate", "audited_accounts"],
  },
  mandatoryFields: ["institutionId", "institutionName", "category", "referenceNumber", "declaredFacultyCount"],
  expiryWarningDays: 30,
};

const ISSUERS: Record<DocCategory, string> = {
  affiliation_certificate: "Synthetic State University (Demo)",
  fire_safety: "Synthetic Fire Services Dept. (Demo)",
  building_completion: "Synthetic Municipal Corporation (Demo)",
  faculty_list: "Self-declared by institution",
  land_document: "Synthetic Land Registry (Demo)",
  audited_accounts: "Synthetic Chartered Accountants (Demo)",
};

function doc(
  appNo: number,
  category: DocCategory,
  institutionId: string,
  overrides: Partial<AppDocument> = {},
): AppDocument {
  const id = `DOC-${appNo}-${category}`;
  return {
    id,
    category,
    filename: `${category}_${institutionId}.pdf`,
    sha256: `synthetic-hash-${appNo}-${category}`,
    sizeBytes: 180_000 + appNo * 1000,
    uploadedAt: "2026-09-1" + appNo + "T10:00:00.000Z",
    processingStatus: "Ready for validation",
    fieldSource: "synthetic",
    issuer: ISSUERS[category],
    documentNumber: `${category.slice(0, 3).toUpperCase()}-${institutionId.slice(-4)}-${appNo}`,
    issueDate: "2025-06-01",
    expiryDate: category === "fire_safety" || category === "affiliation_certificate" ? "2028-05-31" : null,
    institutionIdOnDoc: institutionId,
    verification: null,
    ...overrides,
  };
}

function app(
  n: number,
  institutionId: string,
  institutionName: string,
  declaredFacultyCount: number,
  docs: AppDocument[],
): Application {
  return {
    id: `APP-2026-00${n}`,
    institutionId,
    institutionName,
    category: "Extension of Approval",
    referenceNumber: `SYN-REF-26-${1000 + n}`,
    submittedAt: `2026-09-${10 + n}`,
    declaredFacultyCount,
    documents: docs,
    findingStatuses: {},
    audit: [{ id: `AUD-${n}-0`, at: `2026-09-${10 + n}T09:00:00.000Z`, actor: "System", action: "Synthetic application loaded" }],
  };
}

const EOA: DocCategory[] = ["affiliation_certificate", "fire_safety", "faculty_list", "audited_accounts"];

export const SEED_APPLICATIONS: Application[] = [
  // 1. Complete application, no discrepancies
  app(1, "SYN-INST-1001", "Demo Institute of Technology, Pune", 84, EOA.map((c) => doc(1, c, "SYN-INST-1001"))),
  // 2. Missing mandatory document (fire safety)
  app(2, "SYN-INST-1002", "Sample College of Engineering, Jaipur", 62,
    EOA.filter((c) => c !== "fire_safety").map((c) => doc(2, c, "SYN-INST-1002"))),
  // 3. Expired certificate
  app(3, "SYN-INST-1003", "Placeholder Polytechnic, Bhopal", 40,
    EOA.map((c) => doc(3, c, "SYN-INST-1003", c === "fire_safety" ? { issueDate: "2022-04-01", expiryDate: "2025-03-31" } : {}))),
  // 4. Institution ID mismatch on a document
  app(4, "SYN-INST-1004", "Mock School of Management, Kochi", 35,
    EOA.map((c) => doc(4, c, "SYN-INST-1004", c === "affiliation_certificate" ? { institutionIdOnDoc: "SYN-INST-1040" } : {}))),
  // 5. Conflicting faculty count vs synthetic records (120 declared vs 96 on record)
  app(5, "SYN-INST-1005", "Example Institute of Pharmacy, Lucknow", 120, EOA.map((c) => doc(5, c, "SYN-INST-1005"))),
  // 6. Potential duplicate document (same file hash submitted under two categories)
  app(6, "SYN-INST-1006", "Test Engineering Academy, Guwahati", 51,
    EOA.map((c) => doc(6, c, "SYN-INST-1006", c === "audited_accounts" ? { sha256: "synthetic-hash-6-faculty_list" } : {}))),
];
