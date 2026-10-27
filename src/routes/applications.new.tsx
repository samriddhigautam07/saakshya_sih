import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { APPLICATION_CATEGORIES, type ApplicationCategory } from "@/lib/domain/types";
import { PageHeader, Panel } from "@/components/vw/ui";
import { createApplication, type Application } from "@/lib/api";
import { clearSession, useSession } from "@/lib/session";
import { canCreateApplication } from "@/lib/permissions";

export const Route = createFileRoute("/applications/new")({
  head: () => ({
    meta: [
      { title: "New Application — SAAKSHYA" },
      { name: "description", content: "Create an application record in the authenticated SAAKSHYA backend." },
      { property: "og:title", content: "New Application — SAAKSHYA" },
      { property: "og:description", content: "Create an application record in the authenticated SAAKSHYA backend." },
    ],
  }),
  component: NewApplication,
});

function NewApplication() {
  const user = useSession();
  const nav = useNavigate();
  const [f, setF] = useState({ institutionId: "", institutionName: "", category: "" as ApplicationCategory | "", referenceNumber: "", faculty: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  useEffect(() => { if (!user) void nav({ to: "/login" }); }, [user, nav]);
  if (!user) return null;
  if (!canCreateApplication(user.role)) return <div className="mx-auto max-w-xl">
    <PageHeader title="Application creation unavailable" description={`Your ${user.role} role does not have permission to create applications.`} />
    <Panel title="Permission required">
      <p className="text-sm text-muted-foreground">Application creation requires an Applicant / Institution account. Sign out and sign in with an Applicant / Institution account to continue. The backend enforces this permission for direct API requests as well.</p>
      <Button className="mt-4" onClick={() => { clearSession(); void nav({ to: "/login" }); }}>Sign out and switch account</Button>
    </Panel>
  </div>;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err: Record<string, string> = {};
    if (f.faculty && (!/^\d+$/.test(f.faculty))) err["faculty"] = "Enter a whole number.";
    setErrors(err);
    if (Object.keys(err).length) return;
    setSubmitError(null);
    setBusy(true);
    try {
      const created: Application = await createApplication({ institution_id: f.institutionId.trim(), institution_name: f.institutionName.trim(), category: f.category, reference_number: f.referenceNumber.trim(), submitted_at: new Date().toISOString().slice(0, 10), declared_faculty_count: f.faculty ? Number(f.faculty) : null });
      toast.success(`Application ${created.id} created.`);
      await nav({ to: "/applications/$id", params: { id: created.id } });
    } catch (x) {
      const message = (x as Error).message || "Application could not be created. Please try again.";
      setSubmitError(message);
      toast.error(message);
    } finally { setBusy(false);
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
      <PageHeader title="New Application" description="Create an application record in the authenticated backend. Document files are uploaded separately." />
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
        <Panel title="Next step">
          <p className="text-sm text-muted-foreground">This request creates only the backend application. Upload PDFs from its detail page after creation; no local demo document records are added.</p>
          {submitError && <p role="alert" className="mt-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{submitError}</p>}
          <div className="mt-6 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => nav({ to: "/applications" })}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create application"}</Button>
          </div>
        </Panel>
      </form>
    </div>
  );
}
