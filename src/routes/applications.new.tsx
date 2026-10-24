import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { addApplication, uid, useStore } from "@/lib/store";
import { APPLICATION_CATEGORIES, DOC_CATEGORIES, DOC_CATEGORY_LABELS, type ApplicationCategory, type DocCategory } from "@/lib/domain/types";
import { Loading, PageHeader, Panel } from "@/components/vw/ui";

export const Route = createFileRoute("/applications/new")({
  head: () => ({
    meta: [
      { title: "New Application — VerifyWise AI" },
      { name: "description", content: "Create a new synthetic application for validation." },
      { property: "og:title", content: "New Application — VerifyWise AI" },
      { property: "og:description", content: "Create a new synthetic application for validation." },
    ],
  }),
  component: NewApplication,
});

function NewApplication() {
  const s = useStore();
  const nav = useNavigate();
  const [f, setF] = useState({ institutionId: "", institutionName: "", category: "" as ApplicationCategory | "", referenceNumber: "", faculty: "" });
  const [docs, setDocs] = useState<DocCategory[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  if (!s) return <Loading />;
  const checklist = f.category ? s.config.checklist[f.category] : [];

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const err: Record<string, string> = {};
    if (f.faculty && (!/^\d+$/.test(f.faculty))) err["faculty"] = "Enter a whole number.";
    if (f.referenceNumber && s.applications.some((a) => a.referenceNumber === f.referenceNumber)) err["referenceNumber"] = "This reference number already exists.";
    setErrors(err);
    if (Object.keys(err).length) return;
    try {
      const id = addApplication({
        institutionId: f.institutionId.trim(),
        institutionName: f.institutionName.trim(),
        category: f.category,
        referenceNumber: f.referenceNumber.trim(),
        submittedAt: new Date().toISOString().slice(0, 10),
        declaredFacultyCount: f.faculty ? Number(f.faculty) : null,
        documents: docs.map((c) => ({
          id: `DOC-${uid()}`, category: c, filename: null, sha256: null, sizeBytes: null, uploadedAt: null,
          processingStatus: "Declared – file pending", fieldSource: "none", issuer: "", documentNumber: "",
          issueDate: null, expiryDate: null, institutionIdOnDoc: "", verification: null,
        })),
      });
      toast.success(`Application ${id} created. Missing fields will be flagged by validation.`);
      nav({ to: "/applications/$id", params: { id } });
    } catch (x) {
      toast.error((x as Error).message);
    }
  };

  const field = (k: keyof typeof f, label: string, ph: string) => (
    <div className="space-y-1.5">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} value={f[k]} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
      {errors[k] && <p className="text-xs text-destructive">{errors[k]}</p>}
    </div>
  );

  return (
    <div>
      <PageHeader title="New Application" description="Fields left blank are allowed so you can demonstrate the 'missing mandatory field' rule. Try institution IDs SYN-INST-1001 to SYN-INST-1006." />
      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-2">
        <Panel title="Application details">
          <div className="space-y-4">
            {field("institutionId", "Institution ID", "e.g. SYN-INST-1002")}
            {field("institutionName", "Institution Name", "e.g. Sample College of Engineering, Jaipur")}
            <div className="space-y-1.5">
              <Label htmlFor="category">Application Category</Label>
              <select id="category" className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" value={f.category}
                onChange={(e) => setF({ ...f, category: e.target.value as ApplicationCategory })}>
                <option value="">Select category…</option>
                {APPLICATION_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            {field("referenceNumber", "Application Reference Number", "e.g. SYN-REF-26-2001")}
            {field("faculty", "Declared Faculty Count", "e.g. 62")}
          </div>
        </Panel>
        <Panel title="Submitted documents">
          <p className="mb-3 text-sm text-muted-foreground">Tick the documents the institution declares as submitted. Files are attached on the Document Upload page.</p>
          <div className="space-y-2">
            {DOC_CATEGORIES.map((c) => (
              <label key={c} className="flex items-center gap-3 rounded-md border p-3 text-sm">
                <input type="checkbox" checked={docs.includes(c)} onChange={(e) => setDocs(e.target.checked ? [...docs, c] : docs.filter((d) => d !== c))} />
                <span className="flex-1">{DOC_CATEGORY_LABELS[c]}</span>
                {checklist.includes(c) && <span className="text-xs font-medium text-accent-foreground">Required</span>}
              </label>
            ))}
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => nav({ to: "/applications" })}>Cancel</Button>
            <Button type="submit">Create application</Button>
          </div>
        </Panel>
      </form>
    </div>
  );
}
