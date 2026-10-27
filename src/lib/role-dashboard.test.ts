import { describe, expect, it } from "vitest";
import type { Application, Finding } from "@/lib/api";
import { institutionWorkflowLabel, reviewerDashboardData } from "@/lib/role-dashboard";

const finding = (status: string, message = "Check evidence"): Finding => ({
  id: `finding-${status}`, application_id: "APP-1", document_id: null, finding_key: status,
  rule_id: "RULE-1", rule_name: "Evidence review", severity: "Medium", target: "document",
  expected: null, actual: null, rule_version: 1, status, document_ids_json: [], evidence_json: [],
  resolution_type: null, message, recommendation: "Review evidence", created_at: "2026-01-01", updated_at: "2026-01-01",
});

const application = (overrides: Partial<Application> = {}): Application => ({
  id: "APP-1", institution_id: "INST-1", institution_name: "Example Institute", category: "New Institution",
  reference_number: "REF-1", submitted_at: "2026-01-01", declared_faculty_count: null, owner_user_id: "user-1",
  created_at: "2026-01-01", updated_at: "2026-01-01", documents: [], findings: [], reviewer_decisions: [], audit_logs: [], ...overrides,
});

describe("role dashboard data", () => {
  it("counts reviewer queue from unresolved backend findings and recorded decisions", () => {
    const queued = application({ findings: [finding("Open"), finding("Under Review")] });
    const completed = application({ id: "APP-2", findings: [finding("Resolved")], reviewer_decisions: [{ id: "decision-1" }] });
    expect(reviewerDashboardData([queued, completed])).toMatchObject({
      pendingApplications: [queued], reviewedApplications: [completed], pendingFindings: 1, recordedDecisions: 1,
    });
  });

  it("labels institution workflow using only returned documents, findings, and decisions", () => {
    expect(institutionWorkflowLabel(application())).toBe("No documents uploaded");
    expect(institutionWorkflowLabel(application({ findings: [finding("Open", "A required document is missing.")] }))).toBe("1 required document finding");
    expect(institutionWorkflowLabel(application({ documents: [{ id: "D1" } as Application["documents"][number]] }))).toBe("No open findings recorded");
  });
});
