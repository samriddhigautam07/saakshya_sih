import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, Loading, PageHeader, Panel, StatusBadge, fmtDateTime } from "@/components/vw/ui";
import { ApiError, activateRegulatoryRule, approveRegulatoryRule, configureRegulatoryCategory, getCategoryChecklist, getRegulatoryAuditHistory, listRegulatoryPassages, listRegulatoryRules, listRegulatorySources, proposeRegulatoryRule, registerRegulatorySource, reviseRegulatoryRule, retireRegulatoryRule, searchRegulatoryPassages, uploadRegulatorySource, verifyRegulatorySource, type AuditEvent, type RegulatoryPassage, type RegulatoryRule, type RegulatorySource, type RuleDraftPayload } from "@/lib/api";
import { useSession } from "@/lib/session";
import { APPLICATION_CATEGORIES, type ApplicationCategory } from "@/lib/domain/types";

export const Route = createFileRoute("/rules")({ component: RulesWorkspace });

const EMPTY_FORM = { title: "", authority: "", url: "", version: "", publication: "", effective: "", supersedes: "" };
const failure = (cause: unknown) => {
  if (cause instanceof ApiError && cause.status === 503) return "Provider Unavailable: the backend has no configured proposal provider. The source remains available; no rule was created.";
  if (cause instanceof ApiError && cause.status === 502) return "The configured proposal provider failed. No proposal was created; try again later or inspect the source passage manually.";
  return cause instanceof Error ? cause.message : "The request could not be completed.";
};

export function RulesWorkspace() {
  const user = useSession();
  const navigate = useNavigate();
  const [sources, setSources] = useState<RegulatorySource[]>([]);
  const [rules, setRules] = useState<RegulatoryRule[]>([]);
  const [passages, setPassages] = useState<RegulatoryPassage[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [categoryEnabled, setCategoryEnabled] = useState<Record<string, boolean>>({});
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [passageId, setPassageId] = useState("");
  const [category, setCategory] = useState<ApplicationCategory>(APPLICATION_CATEGORIES[0] ?? "New Institution");
  const [query, setQuery] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [revision, setRevision] = useState<RegulatoryRule | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [sourceReviewed, setSourceReviewed] = useState(false);

  const load = async () => {
    setError(null);
    try {
      const [nextSources, nextRules, nextAudit, checklists] = await Promise.all([
        listRegulatorySources(), listRegulatoryRules(), getRegulatoryAuditHistory(),
        Promise.all(APPLICATION_CATEGORIES.map((item) => getCategoryChecklist(item))),
      ]);
      setSources(nextSources); setRules(nextRules); setAudit(nextAudit);
      setCategoryEnabled(Object.fromEntries(checklists.map((item) => [item.application_category, item.configured])));
      setSelectedSourceId((current) => current || nextSources[0]?.id || "");
    } catch (cause) { setError(failure(cause)); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!user) { void navigate({ to: "/login" }); return; }
    if (user.role !== "Rules Manager / Administrator") { setLoading(false); return; }
    void load();
  }, [user, navigate]);

  useEffect(() => {
    if (user?.role !== "Rules Manager / Administrator" || !selectedSourceId) { setPassages([]); return; }
    let cancelled = false;
    listRegulatoryPassages(selectedSourceId).then((items) => { if (!cancelled) setPassages(items); }).catch((cause) => { if (!cancelled) setError(failure(cause)); });
    return () => { cancelled = true; };
  }, [selectedSourceId, user]);

  const selectedSource = sources.find((item) => item.id === selectedSourceId);
  const perform = async (key: string, successMessage: string, action: () => Promise<unknown>) => {
    setBusy(key); setError(null); setSuccess(null);
    try { await action(); setSuccess(successMessage); await load(); }
    catch (cause) { setError(failure(cause)); }
    finally { setBusy(null); }
  };

  const createSource = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload = {
      title: form.title.trim(), issuing_authority: form.authority.trim(), document_version: form.version.trim(),
      ...(form.url.trim() ? { source_url: form.url.trim() } : {}),
      ...(form.publication ? { publication_date: form.publication } : {}),
      ...(form.effective ? { effective_date: form.effective } : {}),
      ...(form.supersedes ? { supersedes_source_id: form.supersedes } : {}),
    };
    await perform("source", "Source metadata registered. Attach an authorized PDF to ingest its text and page passages.", async () => {
      const created = await registerRegulatorySource(payload);
      setSelectedSourceId(created.id); setForm(EMPTY_FORM);
    });
  };

  const attachSource = async (source: RegulatorySource, file: File | undefined) => {
    if (!file) return;
    await perform(`upload-${source.id}`, "Authorized source PDF ingested. Review the extracted passages before marking the source verified.", () => uploadRegulatorySource(source.id, file));
    const input = document.getElementById(`source-file-${source.id}`) as HTMLInputElement | null; if (input) input.value = "";
  };

  const findPassages = async () => {
    if (!selectedSourceId) return;
    setBusy("search"); setError(null);
    try { setPassages(query.trim().length >= 2 ? await searchRegulatoryPassages(selectedSourceId, query.trim()) : await listRegulatoryPassages(selectedSourceId)); }
    catch (cause) { setError(failure(cause)); }
    finally { setBusy(null); }
  };

  const saveRevision = async (payload: RuleDraftPayload) => {
    if (!revision) return;
    await perform(`revise-${revision.id}`, "A new immutable draft version was created; the existing rule version remains in history.", () => reviseRegulatoryRule(revision.id, payload));
    setRevision(null);
  };

  if (!user) return <Loading />;
  if (user.role !== "Rules Manager / Administrator") return <Panel title="Permission required"><p role="alert">The Regulatory Rules Workspace is available only to Rules Manager / Administrator accounts.</p><Button className="mt-3" onClick={() => void navigate({ to: "/" })}>Back to dashboard</Button></Panel>;

  return <div className="space-y-6">
    <PageHeader title="Regulatory Rules Workspace" description="Manage source records, source passages, rule versions, category configuration, and the audit trail through Rules Manager–authorized backend APIs." actions={<span className="rounded-full border border-warning/40 bg-warning/10 px-3 py-1 text-xs font-medium text-warning-foreground">Demo Environment</span>} />
    <p className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">A source URL is stored as metadata only; this service does not fetch it. Upload an authorized regulatory PDF. Marking a source verified records human review in this prototype and is not issuer verification or AICTE integration.</p>
    {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"><span>{error}</span><Button size="sm" variant="outline" onClick={() => void load()}>Retry</Button></div>}
    {success && <p role="status" className="rounded-md border border-success/30 bg-success/10 p-3 text-sm">{success}</p>}
    {loading ? <Loading label="Loading backend regulatory records…" /> : <>
      <Panel title="Register an authorized source">
        <form className="grid gap-3 md:grid-cols-2" onSubmit={(event) => void createSource(event)}>
          <div><Label htmlFor="source-title">Source title</Label><Input id="source-title" required minLength={3} maxLength={500} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></div>
          <div><Label htmlFor="source-authority">Issuing authority</Label><Input id="source-authority" required minLength={2} maxLength={300} value={form.authority} onChange={(event) => setForm({ ...form, authority: event.target.value })} /></div>
          <div><Label htmlFor="source-version">Document version</Label><Input id="source-version" required maxLength={120} value={form.version} onChange={(event) => setForm({ ...form, version: event.target.value })} /></div>
          <div><Label htmlFor="source-url">Official source URL (metadata only)</Label><Input id="source-url" type="url" placeholder="https://…" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} /></div>
          <div><Label htmlFor="publication-date">Publication date</Label><Input id="publication-date" type="date" value={form.publication} onChange={(event) => setForm({ ...form, publication: event.target.value })} /></div>
          <div><Label htmlFor="effective-date">Effective date</Label><Input id="effective-date" type="date" value={form.effective} onChange={(event) => setForm({ ...form, effective: event.target.value })} /></div>
          <div><Label htmlFor="supersedes-source">Supersedes source version (optional)</Label><select id="supersedes-source" className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={form.supersedes} onChange={(event) => setForm({ ...form, supersedes: event.target.value })}><option value="">New source lineage</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title} · {source.document_version}</option>)}</select></div>
          <div className="md:col-span-2"><Button type="submit" disabled={busy === "source"}>{busy === "source" ? "Registering…" : "Register source metadata"}</Button></div>
        </form>
      </Panel>

      <Panel title={`Regulatory sources (${sources.length})`}>
        {sources.length === 0 ? <Empty title="No regulatory sources are registered." /> : <ul className="space-y-3">{sources.map((source) => <li key={source.id} className={`rounded-md border p-3 ${selectedSourceId === source.id ? "border-primary" : ""}`}>
          <div className="flex flex-wrap items-center justify-between gap-2"><button className="text-left" onClick={() => { setSelectedSourceId(source.id); setSourceReviewed(false); }}><strong>{source.title}</strong><span className="ml-2 text-xs text-muted-foreground">{source.issuing_authority} · v{source.document_version}</span></button><StatusBadge status={source.status.replaceAll("_", " ")} /></div>
          <p className="mt-1 text-xs text-muted-foreground">{source.original_filename ?? source.source_url ?? "No URL or PDF attached"} · {source.extraction_status} · {source.passage_count} page passage(s)</p>
          {selectedSourceId === source.id && <div className="mt-3 flex flex-wrap items-center gap-3 border-t pt-3">
            {!source.original_filename && <><input id={`source-file-${source.id}`} aria-label={`Source PDF for ${source.title}`} type="file" accept="application/pdf,.pdf" disabled={busy === `upload-${source.id}`} onChange={(event) => void attachSource(source, event.target.files?.[0])} />{busy === `upload-${source.id}` && <span role="status">Ingesting source PDF…</span>}</>}
            {source.status === "ingested" && source.passage_count > 0 && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={sourceReviewed} onChange={(event) => setSourceReviewed(event.target.checked)} />I reviewed the uploaded source and extracted page text</label>}
            {source.status === "ingested" && source.passage_count > 0 && <Button size="sm" disabled={!sourceReviewed || busy === `verify-${source.id}`} onClick={() => void perform(`verify-${source.id}`, "Human source review recorded by the backend.", () => verifyRegulatorySource(source.id))}>Mark source reviewed</Button>}
            {source.source_url && <a className="text-xs text-primary underline" href={source.source_url} target="_blank" rel="noreferrer">Open recorded source URL</a>}
          </div>}
        </li>)}</ul>}
      </Panel>

      {selectedSource && <Panel title={`Source passages · ${selectedSource.title}`}>
        {selectedSource.passage_count === 0 ? <Empty title="No searchable page passages are available. Upload a readable source PDF first." /> : <>
          <div className="mb-3 flex gap-2"><Input aria-label="Search source passages" placeholder="Search extracted source text…" value={query} onChange={(event) => setQuery(event.target.value)} /><Button variant="outline" disabled={busy === "search"} onClick={() => void findPassages()}>{busy === "search" ? "Searching…" : "Search"}</Button></div>
          {passages.length === 0 ? <Empty title="No passages match this search." /> : <div className="max-h-96 space-y-2 overflow-y-auto">{passages.map((passage) => <article key={passage.id} className="rounded border p-3 text-sm"><p className="mb-1 text-xs font-semibold text-muted-foreground">Page {passage.page_number}</p><p className="whitespace-pre-wrap">{passage.text}</p></article>)}</div>}
        </>}
      </Panel>}

      <Panel title="Propose a rule from reviewed source evidence">
        <p className="mb-3 text-xs text-muted-foreground">The configured backend proposal provider is used only after you select a verified source passage. Provider failure creates no rule. Every proposal requires human review before activation.</p>
        <div className="grid gap-3 md:grid-cols-3"><div><Label htmlFor="proposal-source">Verified source</Label><select id="proposal-source" className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={selectedSourceId} onChange={(event) => { setSelectedSourceId(event.target.value); setPassageId(""); }}><option value="">Select source…</option>{sources.filter((source) => source.status === "verified").map((source) => <option key={source.id} value={source.id}>{source.title} · {source.document_version}</option>)}</select></div><div><Label htmlFor="proposal-passage">Source passage</Label><select id="proposal-passage" className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={passageId} onChange={(event) => setPassageId(event.target.value)}><option value="">Select passage…</option>{passages.map((passage) => <option key={passage.id} value={passage.id}>Page {passage.page_number} · {passage.text.slice(0, 90)}</option>)}</select></div><div><Label htmlFor="proposal-category">Application category</Label><select id="proposal-category" className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={category} onChange={(event) => setCategory(event.target.value as ApplicationCategory)}>{APPLICATION_CATEGORIES.map((item) => <option key={item}>{item}</option>)}</select></div></div>
        <Button className="mt-3" disabled={!selectedSource || selectedSource.status !== "verified" || !passageId || !!busy} onClick={() => void perform("proposal", "Rule proposal returned by backend; inspect its quotation and uncertainty before approval.", () => proposeRegulatoryRule(selectedSourceId, passageId, category))}>{busy === "proposal" ? "Requesting proposal…" : "Request structured proposal"}</Button>
      </Panel>

      <Panel title={`Rule versions (${rules.length})`}>
        {rules.length === 0 ? <Empty title="No rules or proposals are available." /> : <div className="space-y-3">{rules.map((rule) => <article key={rule.id} className="rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-2"><strong>{rule.rule_id} v{rule.version} · {rule.rule_title}</strong><StatusBadge status={rule.status.replaceAll("_", " ")} />{rule.is_demo && <StatusBadge status="Synthetic demo rule" />}</div>
          <p className="mt-2 text-sm">{rule.requirement}</p><blockquote className="mt-2 border-l-2 pl-3 text-sm italic">“{rule.supporting_quotation}”</blockquote>
          <p className="mt-2 text-xs text-muted-foreground">Source {rule.source_version} · page {rule.page_number} · {rule.application_category} · {rule.validation_type} · created by {rule.created_by}{rule.reviewed_by ? ` · reviewed by ${rule.reviewed_by}` : ""}</p>
          {rule.uncertainty_notes.length > 0 && <p className="mt-2 rounded bg-warning/10 p-2 text-xs">Manual review notes: {rule.uncertainty_notes.join("; ")}</p>}
          <div className="mt-3 flex flex-wrap gap-2">{["draft", "manual_review"].includes(rule.status) && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void perform(`approve-${rule.id}`, `${rule.rule_id} v${rule.version} approved by the Rules Manager.`, () => approveRegulatoryRule(rule.id))}>Approve reviewed version</Button>}{rule.status === "approved" && <Button size="sm" disabled={!!busy} onClick={() => void perform(`activate-${rule.id}`, `${rule.rule_id} v${rule.version} activated; prior versions remain in history.`, () => activateRegulatoryRule(rule.id))}>Activate</Button>}{["approved", "active", "retired"].includes(rule.status) && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => setRevision(rule)}>Create revision</Button>}{["approved", "active"].includes(rule.status) && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void perform(`retire-${rule.id}`, `${rule.rule_id} v${rule.version} retired.`, () => retireRegulatoryRule(rule.id))}>Retire</Button>}</div>
          {revision?.id === rule.id && <RevisionEditor rule={rule} busy={busy === `revise-${rule.id}`} onCancel={() => setRevision(null)} onSubmit={(payload) => void saveRevision(payload)} />}
        </article>)}</div>}
      </Panel>

      <Panel title="Application category configuration"><ul className="grid gap-2 sm:grid-cols-2">{APPLICATION_CATEGORIES.map((item) => <li key={item} className="flex items-center justify-between rounded border p-3 text-sm"><span>{item}<span className="ml-2 text-xs text-muted-foreground">{categoryEnabled[item] ? "Checklist enabled" : "Checklist disabled"}</span></span><Button size="sm" variant="outline" disabled={!!busy} onClick={() => void perform(`category-${item}`, `${item} checklist setting saved.`, () => configureRegulatoryCategory(item, !categoryEnabled[item]))}>{categoryEnabled[item] ? "Disable" : "Enable"}</Button></li>)}</ul></Panel>

      <Panel title={`Regulatory audit history (${audit.length})`}>
        {audit.length === 0 ? <Empty title="No regulatory audit events have been recorded." /> : <ol className="max-h-96 space-y-3 overflow-y-auto">{audit.map((event) => <li key={event.id} className="border-l-2 border-primary/30 pl-3 text-sm"><strong>{event.event_type.replaceAll("_", " ")}</strong> · {event.entity_type} {event.entity_id}<p className="text-xs text-muted-foreground">{event.actor} · {fmtDateTime(event.created_at)}</p>{Object.keys(event.details).length > 0 && <p className="mt-1 break-words text-xs text-muted-foreground">{JSON.stringify(event.details)}</p>}</li>)}</ol>}
      </Panel>
    </>}
  </div>;
}

function RevisionEditor({ rule, busy, onCancel, onSubmit }: { rule: RegulatoryRule; busy: boolean; onCancel: () => void; onSubmit: (payload: RuleDraftPayload) => void }) {
  const [title, setTitle] = useState(rule.rule_title);
  const [quote, setQuote] = useState(rule.supporting_quotation);
  const [requirement, setRequirement] = useState(rule.requirement);
  const [evidence, setEvidence] = useState(rule.required_evidence);
  const [clause, setClause] = useState(rule.clause_reference ?? "");
  const [annexure, setAnnexure] = useState(rule.annexure_reference ?? "");
  const [conditions, setConditions] = useState(rule.conditions.join("\n"));
  const [parameters, setParameters] = useState(JSON.stringify(rule.validation_parameters, null, 2));
  const [uncertainty, setUncertainty] = useState(rule.uncertainty_notes.join("\n"));
  const [error, setError] = useState<string | null>(null);
  return <form className="mt-4 space-y-3 border-t pt-3" onSubmit={(event) => {
    event.preventDefault(); setError(null);
    try {
      const validation_parameters = JSON.parse(parameters) as Record<string, unknown>;
      onSubmit({ rule_title: title, supporting_quotation: quote, clause_reference: clause || null, annexure_reference: annexure || null, page_number: rule.page_number, application_category: rule.application_category, requirement, conditions: conditions.split("\n").map((line) => line.trim()).filter(Boolean), required_evidence: evidence, validation_type: rule.validation_type, validation_parameters, applicable_from: rule.applicable_from, applicable_until: rule.applicable_until, uncertainty_notes: uncertainty.split("\n").map((line) => line.trim()).filter(Boolean) });
    } catch { setError("Validation parameters must be valid JSON."); }
  }}>
    <h3 className="font-semibold">Draft a new version from v{rule.version}</h3><p className="text-xs text-muted-foreground">Source, category, page, and validation type remain tied to this cited version. The previous version is preserved.</p>
    <div className="grid gap-2 sm:grid-cols-2"><div><Label>Rule title</Label><Input required minLength={3} value={title} onChange={(event) => setTitle(event.target.value)} /></div><div><Label>Required evidence</Label><Input required value={evidence} onChange={(event) => setEvidence(event.target.value)} /></div><div><Label>Clause reference</Label><Input value={clause} onChange={(event) => setClause(event.target.value)} /></div><div><Label>Annexure reference</Label><Input value={annexure} onChange={(event) => setAnnexure(event.target.value)} /></div></div>
    <div><Label>Exact supporting quotation</Label><textarea required minLength={10} className="min-h-20 w-full rounded-md border bg-background p-2 text-sm" value={quote} onChange={(event) => setQuote(event.target.value)} /></div>
    <div><Label>Requirement</Label><textarea required minLength={3} className="min-h-20 w-full rounded-md border bg-background p-2 text-sm" value={requirement} onChange={(event) => setRequirement(event.target.value)} /></div>
    <div className="grid gap-2 sm:grid-cols-2"><div><Label>Conditions (one per line)</Label><textarea className="min-h-20 w-full rounded-md border bg-background p-2 text-sm" value={conditions} onChange={(event) => setConditions(event.target.value)} /></div><div><Label>Uncertainty notes (one per line)</Label><textarea className="min-h-20 w-full rounded-md border bg-background p-2 text-sm" value={uncertainty} onChange={(event) => setUncertainty(event.target.value)} /></div></div>
    <div><Label>Validation parameters (JSON)</Label><textarea className="min-h-24 w-full rounded-md border bg-background p-2 font-mono text-xs" value={parameters} onChange={(event) => setParameters(event.target.value)} /></div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    <div className="flex gap-2"><Button type="submit" disabled={busy}>{busy ? "Saving new version…" : "Save as new draft version"}</Button><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button></div>
  </form>;
}
