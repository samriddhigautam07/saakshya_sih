import type { Application } from "@/lib/api";

const OPEN_REVIEW_STATUSES = new Set(["Open", "Escalated"]);

export function reviewerDashboardData(applications: Application[]) {
  const pendingApplications = applications.filter((application) =>
    application.findings.some((finding) => OPEN_REVIEW_STATUSES.has(finding.status)),
  );
  const reviewedApplications = applications.filter((application) => application.reviewer_decisions.length > 0);
  return {
    pendingApplications,
    reviewedApplications,
    pendingFindings: pendingApplications.reduce(
      (count, application) => count + application.findings.filter((finding) => OPEN_REVIEW_STATUSES.has(finding.status)).length,
      0,
    ),
    recordedDecisions: applications.reduce((count, application) => count + application.reviewer_decisions.length, 0),
  };
}

export function institutionWorkflowLabel(application: Application) {
  const openFindings = application.findings.filter((finding) =>
    OPEN_REVIEW_STATUSES.has(finding.status) || finding.status === "Under Review",
  ).length;
  const missingDocuments = application.findings.filter((finding) =>
    /required document is missing/i.test(finding.message),
  ).length;
  if (missingDocuments > 0) return `${missingDocuments} required document finding${missingDocuments === 1 ? "" : "s"}`;
  if (openFindings > 0) return `${openFindings} finding${openFindings === 1 ? "" : "s"} need attention`;
  if (application.documents.length === 0) return "No documents uploaded";
  if (application.reviewer_decisions.length > 0) return "Reviewer activity recorded";
  return "No open findings recorded";
}
