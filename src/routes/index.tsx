import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  Clock3,
  FileStack,
  FileUp,
  LogIn,
  Plus,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Empty,
  Loading,
  PageHeader,
  Panel,
  StatusBadge,
  fmtDate,
  fmtDateTime,
} from "@/components/vw/ui";
import { listApplications, type Application } from "@/lib/api";
import { useSession } from "@/lib/session";
import { canCreateApplication } from "@/lib/permissions";
import { summarizeDashboard } from "@/lib/dashboard-summary";
import { institutionWorkflowLabel, reviewerDashboardData } from "@/lib/role-dashboard";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dashboard — SAAKSHYA" },
      {
        name: "description",
        content: "Live application and review activity from the SAAKSHYA backend.",
      },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const user = useSession();
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setApplications(await listApplications());
    } catch (cause) {
      setApplications(null);
      setError((cause as Error).message || "Backend application data could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user) return;
    void load();
  }, [user]);

  if (!user) return <Welcome />;
  const canCreate = canCreateApplication(user.role);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Application workflow and review activity from authenticated backend records. Findings are advisory and require human review."
        actions={
          canCreate ? (
            <Button asChild>
              <Link to="/applications/new">
                <Plus className="h-4 w-4" />
                New application
              </Link>
            </Button>
          ) : undefined
        }
      />

      {loading ? (
        <Loading label="Loading backend applications…" />
      ) : error ? (
        <Empty title="Dashboard data is unavailable.">
          <p role="alert" className="mb-3 text-destructive">
            {error}
          </p>
          <Button variant="outline" onClick={() => void load()}>
            Retry loading dashboard
          </Button>
        </Empty>
      ) : !applications?.length ? (
        <Panel className="border-dashed">
          <Empty title={user.role === "Official Reviewer" ? "No authorized applications are available." : "No backend applications yet."}>
            <p>{user.role === "Applicant / Institution" ? "Create an application to begin the document and validation workflow. No demo records are included in these metrics." : user.role === "Official Reviewer" ? "Applications will appear here when they are available to your authenticated reviewer account." : "No application records were returned. Rules Manager access remains separate from official application review."}</p>
            {canCreate && (
              <Button className="mt-4" asChild>
                <Link to="/applications/new">
                  <Plus className="h-4 w-4" />
                  Create an application
                </Link>
              </Button>
            )}
          </Empty>
        </Panel>
      ) : (
        (() => {
          const summary = summarizeDashboard(applications);
          const reviewerData = reviewerDashboardData(applications);
          const isReviewer = user.role === "Official Reviewer";
          const isApplicant = user.role === "Applicant / Institution";
          const cards = isReviewer ? [
            { label: "Applications awaiting review", value: reviewerData.pendingApplications.length, detail: "At least one open or escalated finding", icon: Clock3, tone: "text-warning-foreground" },
            { label: "Findings awaiting review", value: reviewerData.pendingFindings, detail: "Open or escalated backend findings", icon: AlertTriangle, tone: "text-destructive" },
            { label: "Applications with decisions", value: reviewerData.reviewedApplications.length, detail: "Persisted reviewer decisions", icon: CheckCircle2, tone: "text-success" },
            { label: "Recorded decisions", value: reviewerData.recordedDecisions, detail: "Backend decision history entries", icon: Activity, tone: "text-primary" },
          ] : isApplicant ? [
            { label: "Your applications", value: summary.totalApplications, detail: "Owned backend records", icon: FileStack, tone: "text-primary" },
            { label: "Open findings", value: summary.openFindings, detail: "Need attention or review", icon: AlertTriangle, tone: "text-warning-foreground" },
            { label: "Missing document findings", value: applications.flatMap((item) => item.findings).filter((finding) => /required document is missing/i.test(finding.message)).length, detail: "Detected by backend validation", icon: FileUp, tone: "text-destructive" },
            { label: "Documents", value: applications.reduce((count, item) => count + item.documents.length, 0), detail: "Uploaded to private backend storage", icon: FileStack, tone: "text-success" },
          ] : [
            {
              label: "Applications",
              value: summary.totalApplications,
              detail: "Backend records",
              icon: FileStack,
              tone: "text-primary",
            },
            {
              label: "Open review workload",
              value: summary.openFindings,
              detail: "Open or under review",
              icon: Clock3,
              tone: "text-warning-foreground",
            },
            {
              label: "High severity findings",
              value: summary.highSeverity,
              detail: "Signals for human review",
              icon: AlertTriangle,
              tone: "text-destructive",
            },
            {
              label: "Applications with decisions",
              value: summary.reviewedApplications,
              detail: "At least one reviewer decision",
              icon: CheckCircle2,
              tone: "text-success",
            },
          ];
          const dashboardApplications = isReviewer ? reviewerData.pendingApplications.slice(0, 6) : summary.recentApplications;
          return (
            <>
              {user.role === "Rules Manager / Administrator" && <Panel title="Rules Manager account">
                <p className="text-sm text-muted-foreground">You are signed in with the Rules Manager / Administrator role. Manage authorized regulatory sources, rule versions, approvals, and audit history in the backend-connected workspace. The Validation Engine page remains a labelled local demo.</p>
                <Button className="mt-3" asChild><Link to="/rules"><ShieldCheck className="h-4 w-4" />Open Rules Workspace</Link></Button>
              </Panel>}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {cards.map((card) => (
                  <article key={card.label} className="rounded-lg border bg-card p-5 shadow-sm">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm text-muted-foreground">{card.label}</p>
                        <p className="mt-2 text-3xl font-semibold tracking-tight">{card.value}</p>
                      </div>
                      <card.icon className={`h-5 w-5 ${card.tone}`} aria-hidden="true" />
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">{card.detail}</p>
                  </article>
                ))}
              </div>

              <div className="grid gap-5 xl:grid-cols-3">
                <Panel
                  title={isReviewer ? "Applications awaiting official review" : isApplicant ? "Your recent applications" : "Recent applications"}
                  className="xl:col-span-2"
                  actions={
                    <Link
                      to="/applications"
                      className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                    >
                      All applications <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  }
                >
                  {dashboardApplications.length === 0 ? (
                    <Empty title={isReviewer ? "No applications currently have open findings awaiting review." : "No application activity to show."} />
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[620px] text-sm">
                        <thead className="text-left text-xs text-muted-foreground">
                          <tr>
                            <th className="pb-3">Institution / ID</th>
                            <th>Category</th>
                            <th>Updated</th>
                            <th>{isReviewer ? "Pending findings" : isApplicant ? "Documents / findings" : "Findings"}</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {dashboardApplications.map((application) => (
                            <tr key={application.id} className="border-t align-middle">
                              <td className="py-3 pr-3">
                                <Link
                                  to="/applications/$id"
                                  params={{ id: application.id }}
                                  className="font-medium text-primary hover:underline"
                                >
                                  {application.institution_name || application.id}
                                </Link>
                                <p className="mt-0.5 text-xs text-muted-foreground">
                                  {application.id} ·{" "}
                                  {application.institution_id || "Institution ID not supplied"}
                                </p>
                              </td>
                              <td className="pr-3">
                                {application.category || "Category not selected"}
                              </td>
                              <td className="whitespace-nowrap pr-3">
                                {fmtDate(application.updated_at)}
                              </td>
                              <td>
                                {isApplicant ? <><StatusBadge status={institutionWorkflowLabel(application)} /><p className="mt-1 text-xs text-muted-foreground">{application.documents.length} document(s) · {application.findings.length} persisted finding(s)</p>{application.documents.length > 0 && <p className="mt-1 max-w-64 text-xs text-muted-foreground">PDF text/OCR: {application.documents.map((document) => `${document.category}: ${document.extraction_status} (${document.extracted_text_char_count} chars)`).join("; ")}</p>}</> : <StatusBadge status={`${isReviewer ? application.findings.filter((finding) => finding.status === "Open" || finding.status === "Escalated").length : application.findings.length} finding(s)`} />}
                              </td>
                              <td className="text-right">
                                <div className="flex justify-end gap-2">
                                  <Button size="sm" variant="outline" asChild>
                                    <Link to="/applications/$id" params={{ id: application.id }}>
                                      {isReviewer ? "Evidence" : "Open"}
                                    </Link>
                                  </Button>
                                  {isReviewer && <Button size="sm" asChild><Link to="/review" search={{ app: application.id }}>Review</Link></Button>}
                                  {isApplicant && <Button size="sm" variant="ghost" asChild><Link to="/review" search={{ app: application.id }}>Report</Link></Button>}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Panel>

                <Panel title="Workflow status">
                  {summary.workflowStatuses.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No findings have been returned from backend records. This is not a validation
                      pass.
                    </p>
                  ) : (
                    <ul className="space-y-3">
                      {summary.workflowStatuses.map(([status, count]) => (
                        <li
                          key={status}
                          className="flex items-center justify-between gap-3 border-b pb-2 last:border-0"
                        >
                          <span className="flex items-center gap-2 text-sm">
                            <StatusBadge status={status} />
                          </span>
                          <span className="text-sm font-semibold tabular-nums">{count}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                    Counts come from persisted backend findings. A finding or mismatch is an
                    advisory signal, not a fraud conclusion or automatic rejection.
                  </p>
                </Panel>
              </div>

              {isApplicant && <p className="-mt-2 text-xs text-muted-foreground">Workflow labels summarize current backend records; no open findings is not an approval. Open an application to see extraction/OCR status, corrected versions, validation history, reviewer remarks, evidence, and its report.</p>}

              {isReviewer && <Panel title="Recently reviewed applications">
                {reviewerData.reviewedApplications.length === 0 ? <p className="text-sm text-muted-foreground">No reviewer decisions are recorded for these authorized applications.</p> : <ul className="space-y-2">{reviewerData.reviewedApplications.slice(0, 6).map((application) => <li key={application.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 last:border-0"><span><strong>{application.institution_name || application.id}</strong><span className="ml-2 text-xs text-muted-foreground">{application.id} · {application.reviewer_decisions.length} decision(s)</span></span><div className="flex gap-2"><Button size="sm" variant="outline" asChild><Link to="/applications/$id" params={{ id: application.id }}>Evidence & runs</Link></Button><Button size="sm" variant="outline" asChild><Link to="/review" search={{ app: application.id }}>Report & history</Link></Button></div></li>)}</ul>}
              </Panel>}

              <div className="grid gap-5 lg:grid-cols-2">
                <Panel
                  title="Recent backend activity"
                  actions={
                    <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  }
                >
                  {summary.recentActivity.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No reviewer or audit activity is recorded yet.
                    </p>
                  ) : (
                    <ol className="space-y-3">
                      {summary.recentActivity.map((event) => (
                        <li key={event.id} className="border-l-2 border-primary/30 pl-3">
                          <p className="text-sm font-medium">{event.action}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {event.actor} · {fmtDateTime(event.at)} · {event.applicationId}
                          </p>
                        </li>
                      ))}
                    </ol>
                  )}
                </Panel>
                <Panel title="Continue a workflow">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Button variant="outline" className="justify-start" asChild>
                      <Link to="/applications">
                        <FileStack className="h-4 w-4" />
                        Open applications
                      </Link>
                    </Button>
                    {(isApplicant || isReviewer) && <Button variant="outline" className="justify-start" asChild>
                      <Link to="/upload">
                        <FileUp className="h-4 w-4" />
                        Upload documents
                      </Link>
                    </Button>}
                    {(isApplicant || isReviewer) && <Button variant="outline" className="justify-start" asChild>
                      <Link to="/review">
                        <ShieldCheck className="h-4 w-4" />
                        Review findings
                      </Link>
                    </Button>}
                    {canCreate && (
                      <Button variant="outline" className="justify-start" asChild>
                        <Link to="/applications/new">
                          <Plus className="h-4 w-4" />
                          New application
                        </Link>
                      </Button>
                    )}
                    {user.role === "Rules Manager / Administrator" && <Button variant="outline" className="justify-start" asChild><Link to="/rules"><ShieldCheck className="h-4 w-4" />Manage regulatory rules</Link></Button>}
                  </div>
                  <p className="mt-4 text-xs text-muted-foreground">
                    Category checklists, extraction, validation, reports, and review decisions use
                    the backend workflow on each application.
                  </p>
                </Panel>
              </div>
            </>
          );
        })()
      )}
    </div>
  );
}

export function Welcome() {
  return <div className="mx-auto grid min-h-[65vh] max-w-5xl items-center gap-10 py-10 lg:grid-cols-2">
    <section>
      <p className="text-sm font-semibold uppercase tracking-[0.16em] text-accent-foreground">Institutional compliance assistance</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">Welcome to SAAKSHYA</h1>
      <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">AI-powered document authentication and compliance workflow for institutions and authorized reviewers to organize application documents, inspect deterministic validation findings, and record human review.</p>
      <p className="mt-4 text-xs text-muted-foreground">This is an advisory prototype. It is not an official AICTE system and does not make approval decisions.</p>
    </section>
    <section className="rounded-xl border bg-card p-6 shadow-sm sm:p-8">
      <h2 className="text-xl font-semibold">Get started</h2>
      <p className="mt-2 text-sm text-muted-foreground">Sign in with your account or create an institution account to begin.</p>
      <div className="mt-6 grid gap-3">
        <Button className="w-full" asChild><Link to="/login"><LogIn className="h-4 w-4" />Login</Link></Button>
        <Button variant="outline" className="w-full" asChild><Link to="/signup"><Building2 className="h-4 w-4" />Institution Sign Up</Link></Button>
      </div>
      <p className="mt-5 text-xs text-muted-foreground">Public registration creates Applicant / Institution accounts only. Reviewer and administrator accounts are provisioned through controlled administration.</p>
    </section>
  </div>;
}
