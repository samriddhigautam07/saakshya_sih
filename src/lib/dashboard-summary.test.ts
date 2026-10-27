import { describe, expect, it } from "vitest";
import { summarizeDashboard } from "@/lib/dashboard-summary";
import type { Application } from "@/lib/api";

const application = (overrides: Partial<Application> = {}): Application => ({
  id: "APP-1",
  institution_id: "INST-1",
  institution_name: "Example Institute",
  category: "New Institution",
  reference_number: "REF-1",
  submitted_at: "2026-10-01",
  declared_faculty_count: null,
  owner_user_id: "user-1",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
  documents: [],
  findings: [],
  reviewer_decisions: [],
  audit_logs: [],
  ...overrides,
});

describe("live dashboard summary", () => {
  it("derives metrics and activity only from backend application records", () => {
    const result = summarizeDashboard([
      application({
        findings: [
          {
            id: "f1",
            application_id: "APP-1",
            document_id: null,
            finding_key: "a",
            rule_id: "R1",
            rule_name: "Check one",
            severity: "High",
            target: "name",
            expected: "A",
            actual: "B",
            rule_version: 1,
            status: "Open",
            document_ids_json: [],
            evidence_json: [],
            resolution_type: null,
            message: "Review this",
            recommendation: "Check source",
            created_at: "2026-10-02T00:00:00Z",
            updated_at: "2026-10-02T00:00:00Z",
          },
          {
            id: "f2",
            application_id: "APP-1",
            document_id: null,
            finding_key: "b",
            rule_id: "R2",
            rule_name: "Check two",
            severity: "Medium",
            target: "expiry",
            expected: "Valid",
            actual: "Expired",
            rule_version: 1,
            status: "Resolved",
            document_ids_json: [],
            evidence_json: [],
            resolution_type: "resolved_by_new_evidence",
            message: "Updated evidence",
            recommendation: "None",
            created_at: "2026-10-02T00:00:00Z",
            updated_at: "2026-10-02T00:00:00Z",
          },
        ],
        reviewer_decisions: [
          {
            id: "decision-1",
            decision_type: "confirmed_issue",
            actor: "reviewer@example.test",
            created_at: "2026-10-03T00:00:00Z",
          },
        ],
        audit_logs: [
          {
            id: "audit-1",
            actor: "applicant@example.test",
            action: "Uploaded document",
            created_at: "2026-10-02T12:00:00Z",
          },
        ],
      }),
    ]);

    expect(result.totalApplications).toBe(1);
    expect(result.openFindings).toBe(1);
    expect(result.highSeverity).toBe(1);
    expect(result.reviewedApplications).toBe(1);
    expect(result.workflowStatuses).toEqual([
      ["Open", 1],
      ["Resolved", 1],
    ]);
    expect(result.recentActivity.map((entry) => entry.actor)).toEqual([
      "reviewer@example.test",
      "applicant@example.test",
    ]);
  });

  it("keeps an empty backend result empty", () => {
    expect(summarizeDashboard([])).toMatchObject({
      totalApplications: 0,
      openFindings: 0,
      highSeverity: 0,
      reviewedApplications: 0,
      workflowStatuses: [],
      recentApplications: [],
      recentActivity: [],
    });
  });
});
