import type { Application } from "@/lib/api";

export interface DashboardActivity {
  id: string;
  applicationId: string;
  actor: string;
  action: string;
  at: string;
}

export function summarizeDashboard(applications: Application[]) {
  const findings = applications.flatMap((application) => application.findings);
  const statusCounts = new Map<string, number>();
  for (const finding of findings) {
    statusCounts.set(finding.status, (statusCounts.get(finding.status) ?? 0) + 1);
  }

  const recentActivity: DashboardActivity[] = applications
    .flatMap((application) => [
      ...application.audit_logs.map((entry, index) => ({
        id: `audit-${application.id}-${String(entry["id"] ?? index)}`,
        applicationId: application.id,
        actor: typeof entry["actor"] === "string" ? entry["actor"] : "Backend",
        action:
          typeof entry["action"] === "string" ? entry["action"] : "Application activity recorded",
        at: typeof entry["created_at"] === "string" ? entry["created_at"] : "",
      })),
      ...application.reviewer_decisions.map((entry, index) => ({
        id: `decision-${application.id}-${String(entry["id"] ?? index)}`,
        applicationId: application.id,
        actor: typeof entry["actor"] === "string" ? entry["actor"] : "Official Reviewer",
        action: `Reviewer decision: ${String(entry["decision_type"] ?? entry["status"] ?? "recorded").replaceAll("_", " ")}`,
        at: typeof entry["created_at"] === "string" ? entry["created_at"] : "",
      })),
    ])
    .filter((event) => event.at)
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
    .slice(0, 6);

  const openFindings = findings.filter((finding) =>
    ["Open", "Under Review", "Escalated"].includes(finding.status),
  ).length;
  const highSeverity = findings.filter(
    (finding) => finding.severity === "High" && finding.status !== "Resolved",
  ).length;
  const reviewedApplications = applications.filter(
    (application) => application.reviewer_decisions.length > 0,
  ).length;

  return {
    totalApplications: applications.length,
    openFindings,
    highSeverity,
    reviewedApplications,
    workflowStatuses: [...statusCounts.entries()].sort(([a], [b]) => a.localeCompare(b)),
    recentApplications: [...applications]
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      .slice(0, 6),
    recentActivity,
  };
}
