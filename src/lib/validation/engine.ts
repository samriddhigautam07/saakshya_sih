/**
 * Deterministic, rule-based validation engine. No AI/ML involved.
 * Rules are pure functions so they can be edited or extended independently of the UI.
 */
import {
  DOC_CATEGORY_LABELS,
  type Application,
  type Finding,
  type InstitutionRecord,
  type ValidationConfig,
} from "@/lib/domain/types";

export interface ValidationContext {
  records: InstitutionRecord[];
  allApplications: Application[];
  config: ValidationConfig;
  now: Date;
}

type Rule = {
  id: string;
  name: string;
  description: string;
  run: (app: Application, ctx: ValidationContext) => Omit<Finding, "ruleId" | "ruleName">[];
};

const FIELD_LABELS: Partial<Record<keyof Application, string>> = {
  institutionId: "Institution ID",
  institutionName: "Institution Name",
  category: "Application Category",
  referenceNumber: "Application Reference Number",
  declaredFacultyCount: "Declared Faculty Count",
};

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
const docLabel = (c: keyof typeof DOC_CATEGORY_LABELS) => DOC_CATEGORY_LABELS[c];

export const RULES: Rule[] = [
  {
    id: "R1",
    name: "Missing mandatory field",
    description: "Every configured mandatory application field must have a value.",
    run: (app, { config }) =>
      config.mandatoryFields
        .filter((f) => {
          const v = app[f];
          return v === null || v === undefined || (typeof v === "string" && v.trim() === "");
        })
        .map((f) => ({
          id: `R1:${String(f)}`,
          severity: "High",
          target: FIELD_LABELS[f] ?? String(f),
          expected: "A non-empty value",
          actual: "Empty",
          message: `${FIELD_LABELS[f] ?? String(f)} is required but was not provided.`,
          recommendation: "Request the institution to supply the missing field before review continues.",
        })),
  },
  {
    id: "R2",
    name: "Missing required document",
    description: "Documents in the configurable checklist for the application category must be present with an uploaded file.",
    run: (app, { config }) => {
      if (!app.category) return [];
      return config.checklist[app.category].flatMap((cat) => {
        const d = app.documents.find((x) => x.category === cat);
        if (!d)
          return [{
            id: `R2:${cat}`,
            severity: "High" as const,
            target: docLabel(cat),
            expected: "Document submitted",
            actual: "Not submitted",
            message: `${docLabel(cat)} is required for "${app.category}" but was not submitted.`,
            recommendation: "Raise a deficiency query asking the institution to submit this document.",
          }];
        if (!d.filename)
          return [{
            id: `R2:${cat}:file`,
            severity: "Medium" as const,
            target: docLabel(cat),
            expected: "PDF file uploaded",
            actual: "Declared, file not uploaded",
            message: `${docLabel(cat)} was declared but no file has been uploaded.`,
            recommendation: "Upload the PDF on the Document Upload page or request it from the institution.",
          }];
        return [];
      });
    },
  },
  {
    id: "R3",
    name: "Expired document",
    description: "Documents with a valid expiry date must not be expired (warns if expiring within the configured window).",
    run: (app, { config, now }) =>
      app.documents.flatMap((d) => {
        if (!d.expiryDate) return [];
        const exp = new Date(d.expiryDate + "T23:59:59");
        if (isNaN(exp.getTime())) return [];
        const days = Math.floor((exp.getTime() - now.getTime()) / 86_400_000);
        if (days < 0)
          return [{
            id: `R3:${d.id}`,
            severity: "High" as const,
            target: docLabel(d.category),
            expected: `Valid on ${now.toISOString().slice(0, 10)}`,
            actual: `Expired on ${d.expiryDate}`,
            message: `${docLabel(d.category)} expired ${-days} day(s) ago.`,
            recommendation: "Request a renewed certificate from the institution and re-verify with the issuer.",
          }];
        if (days <= config.expiryWarningDays)
          return [{
            id: `R3w:${d.id}`,
            severity: "Low" as const,
            target: docLabel(d.category),
            expected: `Valid for more than ${config.expiryWarningDays} days`,
            actual: `Expires on ${d.expiryDate} (${days} days)`,
            message: `${docLabel(d.category)} expires soon.`,
            recommendation: "Note in the review; ask for renewal proof if approval extends beyond expiry.",
          }];
        return [];
      }),
  },
  {
    id: "R4",
    name: "Institution ID mismatch",
    description: "The institution ID must exist in synthetic records and match the ID recorded on each document.",
    run: (app, { records }) => {
      const out: Omit<Finding, "ruleId" | "ruleName">[] = [];
      if (app.institutionId && !records.some((r) => r.institutionId === app.institutionId))
        out.push({
          id: "R4:record",
          severity: "High",
          target: "Institution ID",
          expected: "ID present in synthetic institutional records",
          actual: app.institutionId,
          message: "Institution ID was not found in the synthetic institutional records.",
          recommendation: "Confirm the institution ID with the applicant; verify registration manually.",
        });
      for (const d of app.documents) {
        if (d.institutionIdOnDoc && app.institutionId && d.institutionIdOnDoc !== app.institutionId)
          out.push({
            id: `R4:${d.id}`,
            severity: "High",
            target: docLabel(d.category),
            expected: app.institutionId,
            actual: d.institutionIdOnDoc,
            message: `Institution ID on ${docLabel(d.category)} does not match the application.`,
            recommendation:
              "Assign for manual review. A mismatch may be a clerical error; obtain clarification before drawing conclusions.",
          });
      }
      return out;
    },
  },
  {
    id: "R5",
    name: "Conflict with institutional records",
    description: "Application details must agree with synthetic institutional records (name, faculty count).",
    run: (app, { records }) => {
      const rec = records.find((r) => r.institutionId === app.institutionId);
      if (!rec) return [];
      const out: Omit<Finding, "ruleId" | "ruleName">[] = [];
      if (app.institutionName && norm(app.institutionName) !== norm(rec.name))
        out.push({
          id: "R5:name",
          severity: "Medium",
          target: "Institution Name",
          expected: rec.name,
          actual: app.institutionName,
          message: "Institution name differs from the synthetic institutional record.",
          recommendation: "Check for a pending name-change approval or a typing error.",
        });
      if (app.declaredFacultyCount !== null && app.declaredFacultyCount !== rec.facultyCount)
        out.push({
          id: "R5:faculty",
          severity: "High",
          target: "Declared Faculty Count",
          expected: String(rec.facultyCount),
          actual: String(app.declaredFacultyCount),
          message: `Declared faculty count (${app.declaredFacultyCount}) conflicts with institutional records (${rec.facultyCount}).`,
          recommendation: "Request the faculty list with appointment letters and reconcile counts manually.",
        });
      return out;
    },
  },
  {
    id: "R6",
    name: "Potential duplicate document",
    description: "Flags documents sharing a file hash, or the same issuer + document number, within or across applications.",
    run: (app, { allApplications }) => {
      const out: Omit<Finding, "ruleId" | "ruleName">[] = [];
      const others = allApplications.flatMap((a) => a.documents.map((d) => ({ a, d })));
      for (const d of app.documents) {
        const dupe = others.find(
          (o) =>
            o.d.id !== d.id &&
            ((d.sha256 && o.d.sha256 === d.sha256) ||
              (d.documentNumber && o.d.documentNumber === d.documentNumber && o.d.issuer === d.issuer)),
        );
        if (dupe)
          out.push({
            id: `R6:${d.id}`,
            severity: "Medium",
            target: docLabel(d.category),
            expected: "Unique document",
            actual: `Matches ${docLabel(dupe.d.category)} in ${dupe.a.id}${dupe.d.sha256 === d.sha256 ? " (identical file hash)" : " (same issuer & number)"}`,
            message: `${docLabel(d.category)} appears to duplicate another submitted document.`,
            recommendation: "Verify whether the correct file was uploaded. A duplicate alone is not evidence of forgery.",
          });
      }
      return out;
    },
  },
];

export function validateApplication(app: Application, ctx: ValidationContext): Finding[] {
  return RULES.flatMap((r) => r.run(app, ctx).map((f) => ({ ...f, ruleId: r.id, ruleName: r.name })));
}

export type AppOverallStatus = "No Discrepancies" | "Discrepancies Found" | "Under Review" | "Review Completed";

export function overallStatus(app: Application, findings: Finding[]): AppOverallStatus {
  if (findings.length === 0) return "No Discrepancies";
  const st = findings.map((f) => app.findingStatuses[f.id] ?? "Open");
  if (st.every((s) => s === "Resolved")) return "Review Completed";
  if (st.some((s) => s !== "Open")) return "Under Review";
  return "Discrepancies Found";
}
