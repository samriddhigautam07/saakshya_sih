import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Empty, Loading, PageHeader, Panel, StatusBadge, fmtDate } from "@/components/vw/ui";
import { ApiError, getApplication, runValidation, type Application } from "@/lib/api";
import { useSession } from "@/lib/session";
import { DOC_CATEGORY_LABELS } from "@/lib/domain/types";

export const Route = createFileRoute("/applications/$id")({
  head: ({ params }) => ({ meta: [{ title: `${params.id} — VerifyWise AI` }, { name: "description", content: `Backend details and validation for ${params.id}.` }] }),
  component: Detail,
});

function Detail() {
  const { id } = Route.useParams();
  const user = useSession();
  const navigate = useNavigate();
  const [application, setApplication] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const load = () => getApplication(id).then(setApplication).catch((e: ApiError) => { setError(e.message); setApplication(null); }).finally(() => setLoading(false));
  useEffect(() => { if (!user) { void navigate({ to: "/login" }); return; } void load(); }, [user, id]);
  if (!user || loading) return <Loading />;
  if (error) return <Empty title={error}><Link to="/applications" className="text-accent-foreground underline">Back to applications</Link></Empty>;
  if (!application) return <Empty title={`Application ${id} not found.`}><Link to="/applications" className="text-accent-foreground underline">Back to applications</Link></Empty>;
  const a = application;
  const validate = async () => {
    setRunning(true); setRunMessage(null);
    try { const run = await runValidation(a.id); setRunMessage(`Run ${run.id}: ${run.status.replaceAll("_", " ")}; ${run.results.length} result(s).`); await load(); }
    catch (e) { setRunMessage((e as Error).message); }
    finally { setRunning(false); }
  };
  const kv = (k: string, v: React.ReactNode) => <div><dt className="text-xs text-muted-foreground">{k}</dt><dd className="font-medium">{v || "—"}</dd></div>;
  return <div>
    <PageHeader title={a.id} description={a.institution_name || "Unnamed institution"} actions={<>
      {(user.role === "Applicant / Institution" || user.role === "Official Reviewer") && <Button variant="outline" asChild><Link to="/upload" search={{ app: a.id }}>Upload documents</Link></Button>}
      {(user.role === "Applicant / Institution" || user.role === "Official Reviewer") && <Button disabled={running} onClick={validate}>{running ? "Running…" : "Run validation"}</Button>}
    </>} />
    <Panel title="Application details">
      <dl className="grid grid-cols-2 gap-4 text-sm md:grid-cols-3">
        {kv("Institution ID", a.institution_id)}{kv("Category", a.category)}{kv("Reference number", a.reference_number)}
        {kv("Submitted", fmtDate(a.submitted_at))}{kv("Declared faculty", a.declared_faculty_count ?? "")}
        {kv("Backend validation status", a.findings.length ? "Issue Found / review required" : "Not yet validated")}
      </dl>
    </Panel>
    <Panel title={`Backend documents (${a.documents.length})`} className="mt-6">
      {a.documents.length === 0 ? <Empty title="No backend documents uploaded yet." /> : <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead className="text-left text-muted-foreground"><tr><th className="pb-2">Category</th><th>File</th><th>Uploaded</th><th>Processing</th><th>Text extraction</th></tr></thead>
        <tbody>{a.documents.map((d) => <tr key={d.id} className="border-t"><td className="py-2">{DOC_CATEGORY_LABELS[d.category as keyof typeof DOC_CATEGORY_LABELS] ?? d.category}</td><td>{d.filename ?? "—"}</td><td>{fmtDate(d.uploaded_at)}</td><td><StatusBadge status={d.processing_status} /></td><td>{d.extraction_status} ({d.extracted_text_char_count} chars)</td></tr>)}</tbody>
      </table></div>}
    </Panel>
    <Panel title={`Backend findings (${a.findings.length})`} className="mt-6">
      {runMessage && <p role="status" className="mb-3 rounded-md bg-muted p-3 text-sm">{runMessage}</p>}
      {a.findings.length === 0 ? <p className="text-sm text-muted-foreground">No persisted validation findings. This does not mean the application has passed; run validation when approved rules are configured.</p> : <ul className="space-y-3 text-sm">{a.findings.map((f) => <li key={f.id} className="rounded-md border p-3"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={f.severity} /><span className="font-medium">{f.rule_id}: {f.rule_name}</span><span className="text-xs text-muted-foreground">{f.status}</span></div><p className="mt-2">{f.message}</p><p className="mt-1 text-xs text-muted-foreground">Result: {f.expected ?? "—"} → {f.actual ?? "—"}. Evidence remains attached to backend run history.</p></li>)}</ul>}
    </Panel>
  </div>;
}
