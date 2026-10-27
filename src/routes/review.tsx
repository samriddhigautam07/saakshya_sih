import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Loading } from "@/components/vw/ui";
import { ReviewWorkspace } from "@/components/vw/ReviewWorkspace";
import { getApplicationAuditHistory, getApplicationReviewReport, getFindingReviewHistory, listApplications, submitReviewDecision, type Application, type AuditEvent, type ReviewDecision, type ReviewReport } from "@/lib/api";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/review")({
  validateSearch: (s: Record<string, unknown>): { app?: string | undefined } => ({ app: typeof s["app"] === "string" ? s["app"] : undefined }),
  head: () => ({ meta: [{ title: "Results & Review — VerifyWise AI" }, { name: "description", content: "Backend validation report, evidence, reviewer decisions and audit history." }] }),
  component: ReviewPage,
});

function ReviewPage() {
  const user = useSession();
  const { app } = Route.useSearch();
  const nav = useNavigate({ from: "/review" });
  const [applications, setApplications] = useState<Application[]>([]);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [histories, setHistories] = useState<Record<string, ReviewDecision[]>>({});
  const [applicationsLoading, setApplicationsLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFinding, setPendingFinding] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    if (!user) { void nav({ to: "/login" }); return; }
    if (user.role === "Rules Manager / Administrator") { setApplicationsLoading(false); return; }
    let cancelled = false;
    setApplicationsLoading(true); setError(null);
    listApplications().then((items) => { if (!cancelled) setApplications(items); }).catch((e: Error) => { if (!cancelled) setError(e.message); }).finally(() => { if (!cancelled) setApplicationsLoading(false); });
    return () => { cancelled = true; };
  }, [user, nav]);

  useEffect(() => {
    if (!app || !user || user.role === "Rules Manager / Administrator") { setReport(null); setAudit([]); setHistories({}); return; }
    let cancelled = false;
    setReportLoading(true); setError(null); setReport(null);
    Promise.all([getApplicationReviewReport(app), getApplicationAuditHistory(app)]).then(async ([nextReport, nextAudit]) => {
      const findings = nextReport.findings;
      const historyPairs = await Promise.all(findings.map(async (finding) => {
        const findingId = typeof finding["id"] === "string" ? finding["id"] : "";
        if (!findingId) return [findingId, []] as const;
        return [findingId, await getFindingReviewHistory(app, findingId)] as const;
      }));
      if (!cancelled) { setReport(nextReport); setAudit(nextAudit); setHistories(Object.fromEntries(historyPairs)); }
    }).catch((e: Error) => { if (!cancelled) setError(e.message); }).finally(() => { if (!cancelled) setReportLoading(false); });
    return () => { cancelled = true; };
  }, [app, user, refresh]);

  const decide = async (findingId: string, decision: ReviewDecision["decision"], reason: string) => {
    if (!user || user.role !== "Official Reviewer") { setError("Only an authenticated Official Reviewer can record an official decision."); return; }
    if (reason.trim().length < 3) { setError("Enter a decision reason of at least 3 characters."); return; }
    setPendingFinding(findingId); setError(null);
    try { await submitReviewDecision(app ?? "", findingId, decision, reason.trim()); setRefresh((value) => value + 1); }
    catch (e) { setError((e as Error).message); }
    finally { setPendingFinding(null); }
  };

  if (!user) return <Loading />;
  if (user.role === "Rules Manager / Administrator") return <ReviewWorkspace user={user} applications={[]} loading={false} error="Application review reports are available to the owning Applicant / Institution and Official Reviewers. This role can manage regulatory sources and rules, but does not have application review access." report={null} audit={[]} histories={{}} pendingFinding={null} onSelect={() => undefined} onDecision={decide} />;
  return <ReviewWorkspace user={user} applications={applications} {...(app ? { selectedId: app } : {})} loading={applicationsLoading || reportLoading} error={error} report={report} audit={audit} histories={histories} pendingFinding={pendingFinding} onSelect={(id) => void nav({ search: { app: id || undefined } })} onDecision={decide} />;
}
