import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Empty, Loading, PageHeader, Panel, StatusBadge, fmtDate, fmtDateTime } from "@/components/vw/ui";
import { ApiError, extractCorrectedDocumentFields, extractDocumentFields, getApplication, getCategoryChecklist, listDocumentCorrections, listDocumentExtractions, listValidationRuns, newestDocumentExtraction, reprocessDocumentText, runValidation, uploadDocumentCorrection, type Application, type Checklist, type DocumentCorrection, type DocumentExtraction, type ValidationRun } from "@/lib/api";
import { useSession } from "@/lib/session";
import { DOC_CATEGORY_LABELS } from "@/lib/domain/types";
import { extractionFailureMessage, pdfExtractionGuidance } from "@/lib/extraction-message";
import { DocumentIntegrityNotice } from "@/components/vw/DocumentIntegrityNotice";

export const Route = createFileRoute("/applications/$id")({
  head: ({ params }) => ({ meta: [{ title: `${params.id} — SAAKSHYA` }, { name: "description", content: `Backend details and validation for ${params.id}.` }] }),
  component: Detail,
});

function ExtractionFields({ extraction }: { extraction: DocumentExtraction }) {
  if (!extraction.result) return null;
  return <>
    <dl className="mt-3 grid gap-3 md:grid-cols-2">{Object.entries(extraction.result).filter(([key]) => key !== "uncertainty").map(([key, item]) => {
      const field = item as { value: unknown; evidence: string | null; page_number: number | null; confidence: number | null };
      return <div key={key} className="rounded border bg-background p-2"><dt className="text-xs capitalize text-muted-foreground">{key.replaceAll("_", " ")}</dt><dd className="font-medium">{field.value == null ? "Not extracted" : String(field.value)}</dd>{field.evidence && <dd className="mt-1 text-xs">Evidence: “{field.evidence}”</dd>}{field.page_number && <dd className="mt-1 text-xs text-muted-foreground">Page {field.page_number}{field.confidence != null ? ` · confidence ${Math.round(field.confidence * 100)}%` : ""}</dd>}</div>;
    })}</dl>
    {extraction.result.uncertainty.length > 0 && <div className="mt-3"><strong>Uncertainty / manual review:</strong><ul className="list-disc pl-5">{extraction.result.uncertainty.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
  </>;
}

function Detail() {
  const { id } = Route.useParams();
  const user = useSession();
  const navigate = useNavigate();
  const [application, setApplication] = useState<Application | null>(null);
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [runs, setRuns] = useState<ValidationRun[]>([]);
  const [extractions, setExtractions] = useState<Record<string, DocumentExtraction | null>>({});
  const [corrections, setCorrections] = useState<Record<string, DocumentCorrection[]>>({});
  const [correctionExtractions, setCorrectionExtractions] = useState<Record<string, DocumentExtraction>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checklistError, setChecklistError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [extracting, setExtracting] = useState<string | null>(null);
  const [reprocessing, setReprocessing] = useState<string | null>(null);
  const [uploadingCorrection, setUploadingCorrection] = useState<string | null>(null);
  const [extractingCorrection, setExtractingCorrection] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const load = async () => {
    setError(null);
    try {
      const a = await getApplication(id);
      setApplication(a);
      const [runResults, checkResults, extractionResults, correctionResults] = await Promise.all([
        Promise.allSettled([listValidationRuns(id)]),
        Promise.allSettled([a.category ? getCategoryChecklist(a.category) : Promise.resolve(null)]),
        Promise.allSettled(a.documents.map((d) => listDocumentExtractions(id, d.id))),
        Promise.allSettled(a.documents.map((d) => listDocumentCorrections(id, d.id))),
      ]);
      const runResult = runResults[0];
      const checkResult = checkResults[0];
      if (runResult?.status === "fulfilled") setRuns(runResult.value);
      if (checkResult?.status === "fulfilled") { setChecklist(checkResult.value); setChecklistError(null); }
      else setChecklistError(checkResult?.reason instanceof Error ? checkResult.reason.message : "Checklist could not be loaded.");
      const next: Record<string, DocumentExtraction | null> = {};
      a.documents.forEach((d, index) => {
        const res = extractionResults[index];
        next[d.id] = res?.status === "fulfilled" ? newestDocumentExtraction(res.value) : null;
      });
      setExtractions(next);
      const nextCorrections: Record<string, DocumentCorrection[]> = {};
      a.documents.forEach((d, index) => {
        const res = correctionResults[index];
        nextCorrections[d.id] = res?.status === "fulfilled" ? res.value : [];
      });
      setCorrections(nextCorrections);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
      setApplication(null);
    } finally { setLoading(false); }
  };
  useEffect(() => { if (!user) { void navigate({ to: "/login" }); return; } void load(); }, [user, id]);
  if (!user || loading) return <Loading />;
  if (error) return <Empty title={error}><Link to="/applications" className="text-accent-foreground underline">Back to applications</Link></Empty>;
  if (!application) return <Empty title={`Application ${id} not found.`}><Link to="/applications" className="text-accent-foreground underline">Back to applications</Link></Empty>;
  const a = application;
  const validate = async () => {
    setRunning(true); setActionMessage(null);
    try { const run = await runValidation(a.id); setActionMessage(`Run ${run.id}: ${run.status.replaceAll("_", " ")}; ${run.results.length} result(s).`); await load(); }
    catch (e) { setActionMessage((e as Error).message); }
    finally { setRunning(false); }
  };
  const extract = async (documentId: string) => {
    setExtracting(documentId); setActionMessage(null);
    try { const result = await extractDocumentFields(a.id, documentId); setExtractions((old) => ({ ...old, [documentId]: result })); }
    catch (e) { setActionMessage((e as Error).message); }
    finally { setExtracting(null); }
  };
  const reprocessText = async (documentId: string) => {
    setReprocessing(documentId); setActionMessage(null);
    try {
      const document = await reprocessDocumentText(a.id, documentId);
      setApplication((current) => current ? { ...current, documents: current.documents.map((item) => item.id === documentId ? document : item) } : current);
      setActionMessage(document.extracted_text_char_count > 0
        ? `PDF text is ready (${document.extracted_text_char_count} characters; ${document.extraction_status}). You can now run structured extraction.`
        : `PDF text is still empty (${document.extraction_status}). If this is a scanned PDF, install Tesseract and retry.`);
    } catch (e) { setActionMessage((e as Error).message); }
    finally { setReprocessing(null); }
  };
  const uploadCorrection = async (documentId: string, file: File | undefined) => {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setActionMessage("Corrected PDF exceeds the 10 MB upload limit."); return; }
    setUploadingCorrection(documentId); setActionMessage(null);
    try {
      const correction = await uploadDocumentCorrection(a.id, documentId, file);
      setCorrections((old) => ({ ...old, [documentId]: [correction, ...(old[documentId] ?? [])] }));
      setActionMessage(`Corrected document version ${correction.version} was stored. PDF text status: ${correction.extraction_status} (${correction.extracted_text_char_count} characters). Previous versions and validation evidence are retained.`);
    } catch (cause) { setActionMessage((cause as Error).message || "Corrected PDF upload failed."); }
    finally { setUploadingCorrection(null); }
  };
  const extractCorrection = async (documentId: string, correctionId: string) => {
    setExtractingCorrection(correctionId); setActionMessage(null);
    try {
      const result = await extractCorrectedDocumentFields(a.id, documentId, correctionId);
      setCorrectionExtractions((old) => ({ ...old, [correctionId]: result }));
      setCorrections((old) => ({ ...old, [documentId]: (old[documentId] ?? []).map((item) => item.id === correctionId ? { ...item, structured_extraction_status: result.status } : item) }));
      setActionMessage(result.status === "completed" || result.status === "uncertain" ? "Structured extraction result was saved for this corrected version. Run validation to compare the new evidence; prior runs remain in history." : extractionFailureMessage(result));
    } catch (cause) { setActionMessage((cause as Error).message || "Structured extraction could not be started."); }
    finally { setExtractingCorrection(null); }
  };
  const kv = (k: string, v: React.ReactNode) => <div><dt className="text-xs text-muted-foreground">{k}</dt><dd className="font-medium">{v || "—"}</dd></div>;
  return <div>
    <PageHeader title={a.id} description={a.institution_name || "Unnamed institution"} actions={<>
      {(user.role === "Applicant / Institution" || user.role === "Official Reviewer") && <Button variant="outline" asChild><Link to="/upload" search={{ app: a.id }}>Upload documents</Link></Button>}
      <Button variant="outline" asChild><Link to="/review" search={{ app: a.id }}>View report</Link></Button>
      {(user.role === "Applicant / Institution" || user.role === "Official Reviewer") && <Button disabled={running} onClick={validate}>{running ? "Running…" : "Run validation"}</Button>}
    </>} />
    <Panel title="Application details"><dl className="grid grid-cols-2 gap-4 text-sm md:grid-cols-3">
      {kv("Institution ID", a.institution_id)}{kv("Category", a.category)}{kv("Reference number", a.reference_number)}
      {kv("Submitted", fmtDate(a.submitted_at))}{kv("Declared faculty", a.declared_faculty_count ?? "")}
      {kv("Backend findings", a.findings.length ? "Issues or review required" : "No persisted findings; this is not a pass")}
    </dl></Panel>

    <Panel title="Applicable regulatory checklist" className="mt-6">
      {checklistError ? <p role="alert" className="text-sm text-destructive">Checklist unavailable: {checklistError}</p> : !checklist ? <Loading label="Loading category checklist…" /> : checklist.items.length === 0 ? <p className="text-sm text-muted-foreground">No applicable rules are currently returned for {checklist.application_category}. No requirements have been inferred.</p> : <div className="space-y-3">{checklist.items.map((item) => <article key={`${item.rule_id}-${item.version}`} className="rounded-md border p-3 text-sm"><div className="flex flex-wrap items-center gap-2"><strong>{item.rule_id} v{item.version}: {item.title}</strong><StatusBadge status={item.classification === "verified_regulatory" ? "Verified regulatory" : "Synthetic demo rule"} /></div><p className="mt-2">{item.requirement}</p><p className="mt-1 text-muted-foreground">Evidence: {item.required_evidence}</p><blockquote className="mt-2 border-l-2 pl-3 italic">“{item.supporting_quotation}”</blockquote><p className="mt-2 text-xs text-muted-foreground">{item.source_title} · version {item.source_version} · page {item.page_number}{item.classification === "demo" ? " · Synthetic demo content, not verified regulation" : " · Verified source status as recorded by the backend"}</p></article>)}</div>}
      {checklist && !checklist.configured && checklist.items.length === 0 && <p className="mt-2 text-xs text-muted-foreground">No checklist configuration is available for this category.</p>}
    </Panel>

    <Panel title={`Backend documents (${a.documents.length})`} className="mt-6">
      {a.documents.length === 0 ? <Empty title="No backend documents uploaded yet."><Link to="/upload" search={{ app: a.id }} className="text-primary underline">Upload a private PDF</Link></Empty> : <div className="space-y-4">{a.documents.map((d) => {
        const extraction = extractions[d.id];
        const canCorrect = user.role === "Applicant / Institution";
        const pdfGuidance = pdfExtractionGuidance(d.extraction_status);
        return <article key={d.id} className="rounded-md border p-3 text-sm">
          <div className="flex flex-wrap items-center gap-3"><div className="min-w-48 flex-1"><p className="font-medium">{DOC_CATEGORY_LABELS[d.category as keyof typeof DOC_CATEGORY_LABELS] ?? d.category} · {d.filename ?? "Unnamed file"}</p><p className="mt-1 text-xs text-muted-foreground">Uploaded {fmtDate(d.uploaded_at)} · processing <StatusBadge status={d.processing_status} /> · PDF text/OCR: <StatusBadge status={d.extraction_status.replaceAll("_", " ")} /> · {d.extracted_text_char_count.toLocaleString()} extracted characters</p></div>{d.extracted_text_char_count === 0 && <Button variant="outline" disabled={reprocessing === d.id} onClick={() => void reprocessText(d.id)}>{reprocessing === d.id ? "Retrying PDF text…" : "Retry PDF text / OCR"}</Button>}<Button variant="outline" disabled={extracting === d.id || d.extracted_text_char_count === 0} onClick={() => void extract(d.id)}>{extracting === d.id ? "Extracting…" : extraction ? "Retry structured extraction" : "Extract structured fields"}</Button></div>
          <DocumentIntegrityNotice duplicate={d.duplicate_hash_detected} />
          {d.extracted_text_char_count === 0 && <p className="mt-2 rounded bg-warning/10 p-2 text-xs text-warning-foreground">No PDF text is stored. Retry text/OCR extraction where appropriate. Scanned pages require Tesseract in the backend environment.</p>}
          {pdfGuidance && <p role="status" className="mt-2 rounded border border-warning/40 bg-warning/10 p-2 text-xs">{pdfGuidance}</p>}
          {extraction && <div className="mt-3 rounded-md bg-muted/50 p-3"><div className="flex flex-wrap gap-2 text-xs"><StatusBadge status={extraction.status.replaceAll("_", " ")} /><span>Provider: {extraction.provider}{extraction.model ? ` · ${extraction.model}` : ""}</span><span>· {fmtDateTime(extraction.created_at)}</span></div>{extraction.error_message && <p role="status" className="mt-2 rounded border border-warning/40 bg-warning/10 p-3 text-sm">{extractionFailureMessage(extraction)}<span className="mt-1 block text-xs text-muted-foreground">The uploaded PDF and saved PDF text are preserved. Retrying structured extraction is a manual action and may use provider quota.</span></p>}<ExtractionFields extraction={extraction} /></div>}
          {canCorrect && <div className="mt-4 border-t pt-3"><label className="block text-sm font-medium" htmlFor={`correction-${d.id}`}>Upload a corrected PDF version</label><p className="mt-1 text-xs text-muted-foreground">This adds a new private document version; it does not overwrite the original or its evidence.</p><div className="mt-2 flex flex-wrap items-center gap-3"><input id={`correction-${d.id}`} type="file" accept="application/pdf,.pdf" disabled={uploadingCorrection === d.id} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void uploadCorrection(d.id, file); }} className="max-w-full text-xs file:mr-3 file:rounded-md file:border file:bg-background file:px-3 file:py-2 file:text-xs" />{uploadingCorrection === d.id && <span role="status" className="text-xs text-muted-foreground">Uploading and extracting PDF text…</span>}</div></div>}
          {(corrections[d.id] ?? []).length > 0 && <div className="mt-3 rounded-md bg-muted/40 p-3"><h3 className="text-sm font-semibold">Corrected versions</h3><ol className="mt-2 space-y-3">{(corrections[d.id] ?? []).map((correction) => {
            const correctionExtraction = correctionExtractions[correction.id];
            return <li key={correction.id} className="rounded border bg-background p-3"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-medium">Version {correction.version} · {correction.filename}</p><p className="text-xs text-muted-foreground">{fmtDateTime(correction.uploaded_at)} · PDF text {correction.extraction_status.replaceAll("_", " ")} · {correction.extracted_text_char_count.toLocaleString()} characters</p></div>{correction.extracted_text_char_count > 0 && <Button size="sm" variant="outline" disabled={extractingCorrection === correction.id} onClick={() => void extractCorrection(d.id, correction.id)}>{extractingCorrection === correction.id ? "Extracting…" : correction.structured_extraction_status ? "Retry extraction for version" : "Extract corrected version"}</Button>}</div>
              {correctionExtraction && <div className="mt-3">{correctionExtraction.error_message && <p role="status" className="rounded bg-warning/10 p-2 text-xs">{extractionFailureMessage(correctionExtraction)}</p>}<ExtractionFields extraction={correctionExtraction} /></div>}
            </li>;
          })}</ol><p className="mt-3 text-xs text-muted-foreground">Run validation again to compare the new evidence. Historical runs and findings remain available.</p></div>}
        </article>;
      })}</div>}
    </Panel>

    <Panel title={`Validation history (${runs.length} run${runs.length === 1 ? "" : "s"})`} className="mt-6">
      {actionMessage && <p role="status" className="mb-3 rounded-md bg-muted p-3 text-sm">{actionMessage}</p>}
      <p className="mb-3 rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">Validation is deterministic and does not call Gemini. It evaluates active verified rules and evidence available from exact labelled PDF text or prior structured extraction. AI extraction is separate and optional.</p>
      {runs.length === 0 ? <p className="text-sm text-muted-foreground">No backend validation runs yet. A lack of findings is not a pass.</p> : <div className="space-y-3">{runs.map((run) => <details key={run.id} className="rounded-md border p-3" open={runs[0]?.id === run.id}><summary className="cursor-pointer"><span className="font-medium">{run.id}</span> · {fmtDateTime(run.created_at)} · <StatusBadge status={run.status.replaceAll("_", " ")} /> · {run.results.length} result(s)</summary><dl className="my-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">{Object.entries(run.summary_json).map(([key, value]) => <div key={key}><dt className="capitalize text-muted-foreground">{key.replaceAll("_", " ")}</dt><dd className="font-medium">{value}</dd></div>)}</dl>{run.results.length === 0 ? <p className="text-sm text-muted-foreground">This run returned no rule results. Check category configuration and approved verified sources.</p> : <ul className="space-y-3">{run.results.map((result) => { const relatedFinding = result.finding_id ? a.findings.find((finding) => finding.id === result.finding_id) : undefined; return <li key={result.id} className="rounded border p-3"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={result.severity} /><StatusBadge status={result.result_status.replaceAll("_", " ")} /><strong>{result.rule_id}{result.rule_version ? ` v${result.rule_version}` : ""} · {result.rule_name}</strong><span className="rounded border px-2 py-0.5 text-xs text-muted-foreground">{result.source_kind === "cross_document" ? "Deterministic cross-document check" : result.source_kind === "regulatory" ? "Verified rule check" : "Authorized reference check"}</span></div><p className="mt-2">{result.message}</p><p className="mt-1 text-xs text-muted-foreground">Expected {result.expected ?? "—"} · observed {result.actual ?? "—"}{result.revalidation_state ? ` · ${result.revalidation_state.replaceAll("_", " ")}` : ""}</p>{relatedFinding?.recommendation && <p className="mt-2 rounded bg-muted/60 p-2 text-xs"><strong>Suggested next action:</strong> {relatedFinding.recommendation} This is workflow guidance, not an additional regulatory requirement.</p>}{result.revalidation_state === "resolved_by_new_evidence" && <p className="mt-1 text-xs font-medium text-success">Resolved by new evidence; historical finding retained.</p>}{relatedFinding?.resolution_type === "dismissed_by_reviewer" && <p className="mt-1 text-xs font-medium">Dismissed by reviewer as a formal decision.</p>}{result.document_ids_json.length > 0 && <p className="mt-1 text-xs">Supporting documents: {result.document_ids_json.join(", ")}</p>}{result.evidence_json.length > 0 && <ul className="mt-2 space-y-1 text-xs">{result.evidence_json.map((e, i) => <li key={i} className="border-l-2 pl-2">{typeof e["evidence"] === "string" ? `“${e["evidence"]}”` : "Evidence reference"}{typeof e["page_number"] === "number" ? ` · page ${e["page_number"]}` : " · page not recorded"}{typeof e["document_id"] === "string" ? ` · document ${e["document_id"]}` : ""}{e["extraction_source"] === "deterministic_label_parse" ? " · parsed from an exact labelled PDF line" : e["extraction_source"] === "structured_provider" ? " · structured extraction provider" : ""}</li>)}</ul>}</li>; })}</ul>}</details>)}</div>}
    </Panel>
    <Panel title={`Current backend findings (${a.findings.length})`} className="mt-6">{a.findings.length === 0 ? <p className="text-sm text-muted-foreground">No persisted findings. Review the validation run history above for result details.</p> : <ul className="space-y-3">{a.findings.map((f) => <li key={f.id} className="rounded-md border p-3 text-sm"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={f.severity} /><strong>{f.rule_id}: {f.rule_name}</strong><StatusBadge status={f.status} /></div><p className="mt-2">{f.message}</p>{f.resolution_type === "resolved_by_new_evidence" && <p className="mt-1 font-medium text-success">Resolved by new evidence.</p>}{f.resolution_type === "dismissed_by_reviewer" && <p className="mt-1 font-medium">Formally dismissed by a reviewer.</p>}</li>)}</ul>}</Panel>
  </div>;
}
