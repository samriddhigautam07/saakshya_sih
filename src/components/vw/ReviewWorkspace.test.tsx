import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviewWorkspace } from "@/components/vw/ReviewWorkspace";
import type { Application, AuditEvent, ReviewDecision, ReviewReport, User } from "@/lib/api";

const user = (role: User["role"]): User => ({ id: "u1", email: "reviewer@example.test", role, is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });
const application = { id: "APP-1", institution_id: "I-1", institution_name: "Example Institute", category: "New Institution", reference_number: "REF-1", submitted_at: "2026-01-01", declared_faculty_count: 10, owner_user_id: "u1", created_at: "2026-01-01", updated_at: "2026-01-01", documents: [], findings: [], reviewer_decisions: [], audit_logs: [] } as Application;
const report: ReviewReport = {
  report_type: "prototype_review_support", disclaimer: "This report is review support only and is not an official AICTE decision.", application: { id: "APP-1", institution_name: "Example Institute", category: "New Institution" }, synthetic_data: false,
  latest_validation_run: { status: "completed", created_at: "2026-01-01T00:00:00Z", summary_json: { issue_found: 1 } }, applicable_rule_references: [{ rule_id: "R-1", version: 2, title: "Proof of identity", source_title: "Synthetic source", source_version: "v1", page_number: 4, supporting_quotation: "Identity proof must be submitted." }],
  findings: [{ id: "F-1", rule_id: "R-1", rule_version: 2, title: "Proof of identity", status: "Open", report_disposition: "Issue Found", severity: "High", message: "Evidence needs review.", expected: "Valid proof", observed: "Unknown", document_ids: ["D-1"], evidence: [{ document_id: "D-1", page_number: 4, evidence: "Identity proof must be submitted.", value: "Unknown" }] }],
  verification_status: [], mock_verification_present: false, reviewer_decisions: [],
};
const audit: AuditEvent[] = [{ id: "a1", application_id: "APP-1", actor: "reviewer@example.test", event_type: "validation_run", entity_type: "run", entity_id: "run1", details: {}, created_at: "2026-01-01T00:00:00Z" }];
const decision: ReviewDecision = { id: "rd1", application_id: "APP-1", finding_id: "F-1", decision: "confirmed_issue", previous_status: "Open", status: "Under Review", actor: "reviewer@example.test", reason: "Confirmed after evidence review.", created_at: "2026-01-02T00:00:00Z" };
const base = (overrides: Partial<Parameters<typeof ReviewWorkspace>[0]> = {}) => ({ user: user("Official Reviewer"), applications: [application], selectedId: "APP-1", loading: false, error: null, report, audit, histories: {}, pendingFinding: null, onSelect: vi.fn(), onDecision: vi.fn().mockResolvedValue(undefined), ...overrides });

describe("backend review workspace", () => {
  it("shows loading and API errors accessibly", () => {
    const { rerender } = render(<ReviewWorkspace {...base({ loading: true, report: null })} />);
    expect(screen.getByText("Loading backend review data…")).toBeInTheDocument();
    rerender(<ReviewWorkspace {...base({ error: "Backend unavailable", report: null })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Backend unavailable");
  });

  it("renders evidence, page references, disclaimer, rule source and audit history", () => {
    render(<ReviewWorkspace {...base()} />);
    expect(screen.getByText(/not an official AICTE decision/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Identity proof must be submitted\./)).toHaveLength(2);
    expect(screen.getByText(/Document D-1 · page 4/)).toBeInTheDocument();
    expect(screen.getByText(/Synthetic source/)).toBeInTheDocument();
    expect(screen.getByText(/reviewer@example\.test/)).toBeInTheDocument();
  });

  it("clearly distinguishes pending or mock issuer results from real verification", () => {
    const withStatuses = { ...report, verification_status: [
      { document_id: "D-1", status: "Verification Pending", checked_at: "2026-01-01T00:00:00Z", message: "No issuer response yet.", provider: "mock", is_mock: true },
      { document_id: "D-2", status: "Source Unavailable", checked_at: "2026-01-01T00:00:00Z", message: "Provider unavailable.", provider: "mock", is_mock: true },
    ], mock_verification_present: true };
    render(<ReviewWorkspace {...base({ report: withStatuses })} />);
    expect(screen.getByText("Verification Pending")).toBeInTheDocument();
    expect(screen.getByText("Source Unavailable")).toBeInTheDocument();
    expect(screen.getAllByText(/synthetic\/mock response/)).toHaveLength(2);
  });

  it("hides official decision controls for applicants and lets reviewers submit a reasoned decision", () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(<ReviewWorkspace {...base({ user: user("Applicant / Institution"), onDecision })} />);
    expect(screen.queryByRole("button", { name: "Save decision" })).not.toBeInTheDocument();
    expect(screen.getByText(/Official review decisions can only be recorded/i)).toBeInTheDocument();
    rerender(<ReviewWorkspace {...base({ onDecision })} />);
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Confirmed by document evidence." } });
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    expect(onDecision).toHaveBeenCalledWith("F-1", "confirmed_issue", "Confirmed by document evidence.");
  });

  it("distinguishes resolution by new evidence from reviewer dismissal", () => {
    const resolvedReport = { ...report, findings: [
      { ...report.findings[0], id: "F-1", resolution_type: "resolved_by_new_evidence", report_disposition: "Passed" },
      { ...report.findings[0], id: "F-2", resolution_type: "dismissed_by_reviewer", report_disposition: "Dismissed by Official Reviewer" },
    ] };
    render(<ReviewWorkspace {...base({ report: resolvedReport })} />);
    expect(screen.getByText(/Resolved by new evidence/)).toBeInTheDocument();
    expect(screen.getByText(/Formally dismissed by an Official Reviewer/)).toBeInTheDocument();
  });
});
