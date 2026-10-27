import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Info, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, Loading, PageHeader, Panel, StatusBadge, fmtDate } from "@/components/vw/ui";
import { listApplications, listDocuments, uploadDocument, type Application, type Document } from "@/lib/api";
import { useSession } from "@/lib/session";
import { DOC_CATEGORIES, DOC_CATEGORY_LABELS, type DocCategory } from "@/lib/domain/types";
import { DocumentIntegrityNotice } from "@/components/vw/DocumentIntegrityNotice";

export const Route = createFileRoute("/upload")({
  validateSearch: (s: Record<string, unknown>): { app?: string | undefined } => ({ app: typeof s["app"] === "string" ? s["app"] as string : undefined }),
  head: () => ({ meta: [{ title: "Document Upload — VerifyWise AI" }, { name: "description", content: "Upload PDFs to private backend storage." }] }),
  component: UploadPage,
});
const MAX = 10 * 1024 * 1024;

async function fileError(file: File): Promise<string | null> {
  if (!file.name.toLowerCase().endsWith(".pdf")) return "Only .pdf files are accepted.";
  if (file.type && file.type !== "application/pdf") return "The selected file is not reported as application/pdf.";
  if (!file.size) return "The selected file is empty.";
  if (file.size > MAX) return "The selected file exceeds the 10 MB limit.";
  if (new TextDecoder().decode(await file.slice(0, 5).arrayBuffer()) !== "%PDF-") return "The file does not contain a PDF signature.";
  return null;
}

function UploadPage() {
  const user = useSession(); const { app } = Route.useSearch(); const navigate = useNavigate({ from: "/upload" });
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [docs, setDocs] = useState<Document[]>([]); const [category, setCategory] = useState<DocCategory>("fire_safety");
  const [file, setFile] = useState<File | null>(null); const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = applications?.find((item) => item.id === app);
  const canUpload = user?.role === "Applicant / Institution" || user?.role === "Official Reviewer";
  useEffect(() => {
    if (!user) { void navigate({ to: "/login" }); return; }
    if (user.role === "Rules Manager / Administrator") { setError("This role cannot access application documents."); setApplications([]); return; }
    listApplications().then(setApplications).catch((e) => setError((e as Error).message));
  }, [user, navigate]);
  useEffect(() => { if (app) listDocuments(app).then(setDocs).catch((e) => setError((e as Error).message)); else setDocs([]); }, [app]);
  if (!user || applications === null) return <Loading />;
  const upload = async () => {
    if (!app || !current) { setError("Select an application first."); return; }
    if (!file) { setError("Choose a PDF file to upload."); return; }
    setBusy(true); setError(null);
    try {
      const problem = await fileError(file); if (problem) throw new Error(problem);
      await uploadDocument(app, category, file);
      setDocs(await listDocuments(app)); setFile(null);
      const input = document.getElementById("pdf") as HTMLInputElement | null; if (input) input.value = "";
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <div>
    <PageHeader title="Document Upload" description="PDFs are sent to the authenticated backend and stored in its private document directory." />
    <div className="mb-6 flex gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm"><Info className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" /><p><strong>Extraction status is not issuer verification.</strong> Backend processing may extract document text. This prototype is not connected to AICTE or real issuing authorities.</p></div>
    <div className="grid gap-6 lg:grid-cols-3">
      <Panel title="Upload a PDF"><div className="space-y-4">
        <div className="space-y-1.5"><Label htmlFor="app">Application</Label><select id="app" className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" value={app ?? ""} onChange={(e) => { setError(null); void navigate({ search: { app: e.target.value || undefined } }); }}><option value="">Select application…</option>{applications.map((a) => <option key={a.id} value={a.id}>{a.id} — {a.institution_name || "Unnamed"}</option>)}</select></div>
        <div className="space-y-1.5"><Label htmlFor="cat">Document category</Label><select id="cat" className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" value={category} onChange={(e) => setCategory(e.target.value as DocCategory)}>{DOC_CATEGORIES.map((c) => <option key={c} value={c}>{DOC_CATEGORY_LABELS[c]}</option>)}</select></div>
        <div className="space-y-1.5"><Label htmlFor="pdf">PDF file (max 10 MB)</Label><Input id="pdf" type="file" accept="application/pdf,.pdf" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setError(null); }} /></div>
        {error && <p role="alert" className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}
        {canUpload && <Button onClick={upload} disabled={busy} className="w-full">{busy && <Loader2 className="h-4 w-4 animate-spin" />}{busy ? "Uploading…" : "Upload PDF"}</Button>}
      </div></Panel>
      <Panel title={current ? `Backend documents — ${current.id}` : "Backend documents"} className="lg:col-span-2">
        {!current ? <Empty title="Select an application to list its documents." /> : docs.length === 0 ? <Empty title="No backend documents yet." /> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-muted-foreground"><tr><th className="pb-2">Category</th><th>Filename</th><th>Uploaded</th><th>Status</th><th>Extraction</th></tr></thead><tbody>{docs.map((d) => <tr key={d.id} className="border-t"><td className="py-2">{DOC_CATEGORY_LABELS[d.category as DocCategory] ?? d.category}</td><td className="max-w-52 truncate">{d.filename ?? "—"}<DocumentIntegrityNotice duplicate={d.duplicate_hash_detected} /></td><td>{fmtDate(d.uploaded_at)}</td><td><StatusBadge status={d.processing_status} /></td><td>{d.extraction_status} · {d.extracted_text_char_count} chars</td></tr>)}</tbody></table></div>}
      </Panel>
    </div>
  </div>;
}
