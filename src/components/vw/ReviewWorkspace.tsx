import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Empty, Loading, PageHeader, Panel, StatusBadge, fmtDate, fmtDateTime } from "@/components/vw/ui";
import type { Application, AuditEvent, ReviewDecision, ReviewReport, User } from "@/lib/api";

type Decision = ReviewDecision["decision"];
type FindingRecord = Record<string, unknown>;
type Props = {
  user: User;
  applications: Application[];
  selectedId?: string;
  loading: boolean;
  error: string | null;
  report: ReviewReport | null;
  audit: AuditEvent[];
  histories: Record<string, ReviewDecision[]>;
  pendingFinding: string | null;
  onSelect: (id: string) => void;
  onDecision: (findingId: string, decision: Decision, reason: string) => Promise<void>;
};

const str = (value: unknown, fallback = "—") => typeof value === "string" || typeof value === "number" ? String(value) : fallback;
const evidenceText = (value: unknown) => {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => entry as Record<string, unknown>);
};

export function ReviewWorkspace(props: Props) {
  const { user, applications, selectedId, loading, error, report, audit, histories, pendingFinding, onSelect, onDecision } = props;
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [decisionTypes, setDecisionTypes] = useState<Record<string, Decision>>({});
  const selected = applications.find((item) => item.id === selectedId);
  const reviewer = user.role === "Official Reviewer";
  return <div>
    <PageHeader title="Results & Review" description="Backend validation evidence and official reviewer decisions. Reports support review and are not official AICTE decisions." actions={selected && <div className="print:hidden"><Button variant="outline" onClick={() => window.print()}>Print report</Button></div>} />
    <select aria-label="Application" className="mb-6 h-9 w-full max-w-md rounded-md border border-input bg-background px-3 text-sm print:hidden" value={selectedId ?? ""} onChange={(event) => onSelect(event.target.value)}>
      <option value="">Select an application…</option>{applications.map((item) => <option key={item.id} value={item.id}>{item.id} — {item.institution_name || "Unnamed institution"}</option>)}
    </select>
    {error && <p role="alert" className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
    {loading ? <Loading label="Loading backend review data…" /> : !selectedId ? <Empty title="Choose an application to load its backend report." /> : !report ? <Empty title="The backend report could not be loaded." /> : <div className="space-y-6 print:space-y-4">
      <Panel title="Review report" className="print:shadow-none">
        <p className="mb-4 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm font-medium">{report.disclaimer} This is advisory review support only.</p>
        <dl className="grid gap-4 text-sm md:grid-cols-4"><div><dt className="text-xs text-muted-foreground">Application</dt><dd className="font-semibold">{str(report.application["id"], selected?.id)}</dd></div><div className="md:col-span-2"><dt className="text-xs text-muted-foreground">Institution</dt><dd className="font-semibold">{str(report.application["institution_name"], selected?.institution_name)}</dd></div><div><dt className="text-xs text-muted-foreground">Category</dt><dd>{str(report.application["category"])}</dd></div></dl>
        <p className="mt-3 text-xs text-muted-foreground">{report.synthetic_data ? "Synthetic/demo application data" : "Application data from backend records"} · verification records: {report.mock_verification_present ? "includes mock verification" : "no mock verification flagged"}</p>
        {report.latest_validation_run && <p className="mt-2 text-sm">Latest validation run: {str(report.latest_validation_run["status"])} · {str(report.latest_validation_run["created_at"])}{report.latest_validation_run["summary_json"] ? ` · summary ${JSON.stringify(report.latest_validation_run["summary_json"])}` : ""}</p>}
      </Panel>

      <Panel title="Issuer verification status">
        {report.verification_status.length === 0 ? <p className="rounded-md border border-primary/20 bg-primary/5 p-3 text-sm"><StatusBadge status="Pending Verification" /> No issuer verification result was returned. Document extraction and rule checks do not verify a real issuer.</p> : <ul className="space-y-2">{report.verification_status.map((item, index) => <li key={`${str(item["document_id"])}-${index}`} className="rounded border p-3 text-sm"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={str(item["status"], "Pending Verification")} /><span className="text-xs text-muted-foreground">Provider: {str(item["provider"])}{item["is_mock"] ? " · synthetic/mock response" : ""}</span></div><p className="mt-2">{str(item["message"])}</p><p className="mt-1 text-xs text-muted-foreground">Document {str(item["document_id"])} · checked {str(item["checked_at"])}</p></li>)}</ul>}
      </Panel>

      <Panel title="Applicable rule and source references"><p className="mb-3 text-xs text-muted-foreground">Only references supplied by the backend report appear here.</p>{report.applicable_rule_references.length === 0 ? <Empty title="No applicable reviewed rule references were returned." /> : <ul className="space-y-3">{report.applicable_rule_references.map((reference, index) => <li key={`${str(reference["rule_id"])}-${str(reference["version"])}-${index}`} className="rounded border p-3 text-sm"><strong>{str(reference["rule_id"])} v{str(reference["version"])} · {str(reference["title"])}</strong><p className="mt-1 text-xs text-muted-foreground">{str(reference["source_title"])} · source version {str(reference["source_version"])} · page {str(reference["page_number"])}{reference["clause_reference"] ? ` · clause ${str(reference["clause_reference"])}` : ""}{reference["annexure_reference"] ? ` · annexure ${str(reference["annexure_reference"])}` : ""}</p><blockquote className="mt-2 border-l-2 pl-3 italic">“{str(reference["supporting_quotation"]) }”</blockquote></li>)}</ul>}</Panel>

      <Panel title={`Findings (${report.findings.length})`}>{report.findings.length === 0 ? <p className="text-sm text-muted-foreground">No findings were returned. Check the latest validation run status before interpreting this as a pass.</p> : <div className="space-y-4">{report.findings.map((finding: FindingRecord) => {
        const id = str(finding["id"], "unknown");
        const history = histories[id] ?? [];
        const evidence = evidenceText(finding["evidence"]);
        const resolution = finding["resolution_type"];
        const current = decisionTypes[id] ?? "confirmed_issue";
        return <article key={id} className="rounded-lg border p-4"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={str(finding["severity"])} /><StatusBadge status={str(finding["report_disposition"], str(finding["status"]))} /><strong>{str(finding["rule_id"])}{finding["rule_version"] ? ` v${str(finding["rule_version"])}` : ""} · {str(finding["title"])}</strong></div><p className="mt-2 text-sm">{str(finding["message"], str(finding["report_disposition"]))}</p><p className="mt-2 text-xs text-muted-foreground">Expected {str(finding["expected"])} · observed {str(finding["observed"])}</p>
          {resolution === "resolved_by_new_evidence" && <p className="mt-2 text-sm font-medium text-success">Resolved by new evidence; prior run and evidence remain in history.</p>}{resolution === "dismissed_by_reviewer" && <p className="mt-2 text-sm font-medium">Formally dismissed by an Official Reviewer.</p>}
          {Array.isArray(finding["document_ids"]) && <p className="mt-2 text-xs">Supporting documents: {(finding["document_ids"] as unknown[]).map((value) => str(value)).join(", ") || "—"}</p>}
          {evidence.length > 0 && <ul className="mt-3 space-y-2">{evidence.map((item, index) => <li key={index} className="rounded bg-muted p-3 text-sm"><p>{item["evidence"] ? `“${str(item["evidence"])}”` : "Evidence reference"}</p><p className="mt-1 text-xs text-muted-foreground">{item["document_id"] ? `Document ${str(item["document_id"])}` : "Document reference unavailable"}{item["page_number"] ? ` · page ${str(item["page_number"])}` : " · page not recorded"}{item["value"] ? ` · value ${str(item["value"])}` : ""}</p></li>)}</ul>}
          <div className="mt-4 border-t pt-3"><h3 className="text-sm font-semibold">Official decision history</h3>{history.length === 0 ? <p className="mt-1 text-xs text-muted-foreground">No official decisions recorded.</p> : <ol className="mt-2 space-y-2">{history.map((item) => <li key={item.id} className="border-l-2 pl-3 text-sm"><StatusBadge status={item.decision.replaceAll("_", " ")} /><span className="ml-2">{item.reason}</span><p className="mt-1 text-xs text-muted-foreground">{item.actor} · {fmtDateTime(item.created_at)} · {item.previous_status} → {item.status}</p></li>)}</ol>}</div>
          {reviewer && resolution !== "resolved_by_new_evidence" && <form className="mt-4 flex flex-col gap-2 border-t pt-3 print:hidden" onSubmit={(event) => { event.preventDefault(); void onDecision(id, current, reasons[id] ?? ""); }}><label className="text-sm font-medium" htmlFor={`decision-${id}`}>Record official reviewer decision</label><div className="flex flex-wrap gap-2"><select id={`decision-${id}`} className="h-9 rounded-md border bg-background px-2 text-sm" value={current} onChange={(event) => setDecisionTypes((old) => ({ ...old, [id]: event.target.value as Decision }))}><option value="confirmed_issue">Confirmed issue</option><option value="dismissed_finding">Dismiss finding</option><option value="clarification_required">Clarification required</option></select><Button type="submit" disabled={pendingFinding === id || (reasons[id] ?? "").trim().length < 3}>{pendingFinding === id ? "Saving…" : "Save decision"}</Button></div><Textarea aria-label="Decision reason" placeholder="Decision reason (at least 3 characters)" value={reasons[id] ?? ""} onChange={(event) => setReasons((old) => ({ ...old, [id]: event.target.value }))} rows={2} /></form>}
        </article>;
      })}</div>}{!reviewer && <p className="mt-4 rounded-md bg-muted p-3 text-sm">Official review decisions can only be recorded by an authenticated Official Reviewer. Your account can view this report but cannot change official decisions.</p>}</Panel>

      <Panel title="Audit history">{audit.length === 0 ? <p className="text-sm text-muted-foreground">No backend audit events were returned.</p> : <ol className="space-y-2">{audit.map((event) => <li key={event.id} className="border-l-2 border-sidebar-primary pl-3 text-sm"><span className="text-xs text-muted-foreground">{fmtDateTime(event.created_at)} · </span><strong>{event.actor}</strong> — {event.event_type.replaceAll("_", " ")} · {event.entity_type} {event.entity_id}{Object.keys(event.details).length > 0 && <p className="mt-1 text-xs text-muted-foreground">{JSON.stringify(event.details)}</p>}</li>)}</ol>}</Panel>
    </div>}
  </div>;
}
