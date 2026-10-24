import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Info, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { logAudit, uid, updateApplication, useStore } from "@/lib/store";
import { DOC_CATEGORIES, DOC_CATEGORY_LABELS, type AppDocument, type DocCategory } from "@/lib/domain/types";
import { Empty, Loading, PageHeader, Panel, StatusBadge, fmtDate } from "@/components/vw/ui";

export const Route = createFileRoute("/upload")({
  validateSearch: (s: Record<string, unknown>): { app?: string } => ({ app: typeof s.app === "string" ? s.app : undefined }),
  head: () => ({
    meta: [
      { title: "Document Upload — VerifyWise AI" },
      { name: "description", content: "Upload PDF documents for synthetic applications and record document fields." },
      { property: "og:title", content: "Document Upload — VerifyWise AI" },
      { property: "og:description", content: "Upload PDF documents and record document fields." },
    ],
  }),
  component: UploadPage,
});

const MAX = 10 * 1024 * 1024;

async function checkPdf(file: File): Promise<string | null> {
  if (!file.name.toLowerCase().endsWith(".pdf")) return `"${file.name}" is not a PDF. Only .pdf files are accepted.`;
  if (file.type && file.type !== "application/pdf") return `"${file.name}" has type ${file.type}; expected application/pdf.`;
  if (file.size === 0) return `"${file.name}" is empty.`;
  if (file.size > MAX) return `"${file.name}" is ${(file.size / 1048576).toFixed(1)} MB; the limit is 10 MB.`;
  const head = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
  if (head !== "%PDF-") return `"${file.name}" does not contain a valid PDF header.`;
  return null;
}

async function sha256(file: File) {
  const buf = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function UploadPage() {
  const s = useStore();
  const { app } = Route.useSearch();
  const nav = useNavigate({ from: "/upload" });
  const [cat, setCat] = useState<DocCategory>("fire_safety");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  if (!s) return <Loading />;
  const current = s.applications.find((a) => a.id === app);

  const upload = async () => {
    if (!current) return setError("Select an application first.");
    if (!file) return setError("Choose a PDF file to upload.");
    setBusy(true); setError(null);
    try {
      const problem = await checkPdf(file);
      if (problem) { setError(problem); return; }
      const hash = await sha256(file);
      const existing = current.documents.find((d) => d.category === cat);
      const docId = existing?.id ?? `DOC-${uid()}`;
      const base: AppDocument = existing ?? {
        id: docId, category: cat, filename: null, sha256: null, sizeBytes: null, uploadedAt: null, processingStatus: "Declared – file pending",
        fieldSource: "none", issuer: "", documentNumber: "", issueDate: null, expiryDate: null, institutionIdOnDoc: "", verification: null,
      };
      const next: AppDocument = { ...base, filename: file.name, sha256: hash, sizeBytes: file.size, uploadedAt: new Date().toISOString(), processingStatus: "Awaiting manual fields", fieldSource: "none", verification: null };
      updateApplication(current.id, (a) => ({ ...a, documents: existing ? a.documents.map((d) => (d.id === docId ? next : d)) : [...a.documents, next] }));
      logAudit(current.id, `Uploaded ${file.name} as ${DOC_CATEGORY_LABELS[cat]}`, { note: `SHA-256 ${hash.slice(0, 16)}…` });
      toast.success("PDF uploaded. Enter the document fields to complete processing.");
      setEditing(docId); setFile(null);
      (document.getElementById("pdf") as HTMLInputElement | null)?.value && ((document.getElementById("pdf") as HTMLInputElement).value = "");
    } catch (e) {
      setError(`Upload failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Document Upload" description="Attach PDF documents to an application. Files are hashed in your browser for duplicate detection." />
      <div className="mb-6 flex gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" />
        <p><strong>PDF text extraction is not available in this prototype.</strong> Uploaded files are checked for type, size and PDF header and fingerprinted (SHA-256), but their content is not analysed. Document fields (issuer, number, dates, institution ID) must be entered manually.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Upload a PDF">
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="app">Application</Label>
              <select id="app" className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" value={app ?? ""}
                onChange={(e) => { setEditing(null); nav({ search: { app: e.target.value || undefined } }); }}>
                <option value="">Select application…</option>
                {s.applications.map((a) => <option key={a.id} value={a.id}>{a.id} — {a.institutionName || "Unnamed"}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cat">Document category</Label>
              <select id="cat" className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" value={cat} onChange={(e) => setCat(e.target.value as DocCategory)}>
                {DOC_CATEGORIES.map((c) => <option key={c} value={c}>{DOC_CATEGORY_LABELS[c]}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pdf">PDF file (max 10 MB)</Label>
              <Input id="pdf" type="file" accept="application/pdf,.pdf" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setError(null); }} />
            </div>
            {error && <p role="alert" className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}
            <Button onClick={upload} disabled={busy} className="w-full">{busy && <Loader2 className="h-4 w-4 animate-spin" />}{busy ? "Processing…" : "Upload"}</Button>
          </div>
        </Panel>
        <Panel title={current ? `Documents — ${current.id}` : "Documents"} className="lg:col-span-2">
          {!current ? <Empty title="Select an application to see its documents." /> : current.documents.length === 0 ? <Empty title="No documents yet." /> : (
            <table className="w-full text-sm">
              <thead className="text-left text-muted-foreground"><tr><th className="pb-2">Category</th><th>Filename</th><th>Uploaded</th><th>Status</th><th /></tr></thead>
              <tbody>
                {current.documents.map((d) => (
                  <tr key={d.id} className="border-t">
                    <td className="py-2">{DOC_CATEGORY_LABELS[d.category]}</td>
                    <td className="max-w-52 truncate">{d.filename ?? <span className="text-muted-foreground">No file</span>}</td>
                    <td>{fmtDate(d.uploadedAt)}</td>
                    <td><StatusBadge status={d.processingStatus} /></td>
                    <td className="text-right"><Button size="sm" variant="ghost" onClick={() => setEditing(d.id)}>Edit fields</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {current && editing && <FieldEditor key={editing} appId={current.id} doc={current.documents.find((d) => d.id === editing)!} onDone={() => setEditing(null)} />}
        </Panel>
      </div>
    </div>
  );
}

function FieldEditor({ appId, doc, onDone }: { appId: string; doc: AppDocument; onDone: () => void }) {
  const [v, setV] = useState({ issuer: doc.issuer, documentNumber: doc.documentNumber, issueDate: doc.issueDate ?? "", expiryDate: doc.expiryDate ?? "", institutionIdOnDoc: doc.institutionIdOnDoc });
  const [err, setErr] = useState<string | null>(null);
  if (!doc) return null;
  const save = () => {
    if (v.issueDate && v.expiryDate && v.expiryDate < v.issueDate) return setErr("Expiry date cannot be before issue date.");
    updateApplication(appId, (a) => ({
      ...a,
      documents: a.documents.map((d) => d.id === doc.id ? {
        ...d, ...v, issueDate: v.issueDate || null, expiryDate: v.expiryDate || null, fieldSource: "manual", verification: null,
        processingStatus: d.filename ? "Ready for validation" : "Declared – file pending",
      } : d),
    }));
    logAudit(appId, `Entered document fields manually for ${DOC_CATEGORY_LABELS[doc.category]}`);
    toast.success("Document fields saved");
    onDone();
  };
  const f = (k: keyof typeof v, label: string, type = "text") => (
    <div className="space-y-1"><Label htmlFor={`f-${k}`}>{label}</Label><Input id={`f-${k}`} type={type} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></div>
  );
  return (
    <div className="mt-5 rounded-lg border bg-muted/40 p-4">
      <p className="mb-3 text-sm font-medium">Manual document fields — {DOC_CATEGORY_LABELS[doc.category]} <span className="font-normal text-muted-foreground">(not extracted from PDF)</span></p>
      <div className="grid gap-3 md:grid-cols-3">
        {f("issuer", "Issuer")}{f("documentNumber", "Document number")}{f("institutionIdOnDoc", "Institution ID on document")}
        {f("issueDate", "Issue date", "date")}{f("expiryDate", "Expiry date (if any)", "date")}
      </div>
      {err && <p className="mt-2 text-sm text-destructive">{err}</p>}
      <div className="mt-4 flex justify-end gap-2"><Button variant="outline" onClick={onDone}>Cancel</Button><Button onClick={save}>Save fields</Button></div>
    </div>
  );
}
