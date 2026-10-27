import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { findingsFor, logAudit, updateConfig, useStore } from "@/lib/store";
import { RULES } from "@/lib/validation/engine";
import { DEFAULT_CONFIG } from "@/lib/domain/seed";
import { APPLICATION_CATEGORIES, DOC_CATEGORIES, DOC_CATEGORY_LABELS } from "@/lib/domain/types";
import { Loading, PageHeader, Panel, StatusBadge } from "@/components/vw/ui";

export const Route = createFileRoute("/validation")({
  head: () => ({
    meta: [
      { title: "Validation Engine — SAAKSHYA" },
      { name: "description", content: "Deterministic validation rules and configurable document checklist." },
      { property: "og:title", content: "Validation Engine — SAAKSHYA" },
      { property: "og:description", content: "Deterministic validation rules and configurable document checklist." },
    ],
  }),
  component: ValidationPage,
});

function ValidationPage() {
  const s = useStore();
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<{ id: string; n: number; high: number }[] | null>(null);
  if (!s) return <Loading />;

  const runAll = async () => {
    setRunning(true);
    await new Promise((r) => setTimeout(r, 400));
    const res = s.applications.map((a) => {
      const f = findingsFor(s, a);
      logAudit(a.id, `Validation run: ${f.length} finding(s)`);
      return { id: a.id, n: f.length, high: f.filter((x) => x.severity === "High").length };
    });
    setLastRun(res);
    setRunning(false);
    toast.success(`Validated ${res.length} applications`);
  };

  const toggle = (cat: (typeof APPLICATION_CATEGORIES)[number], doc: (typeof DOC_CATEGORIES)[number]) => {
    const list = s.config.checklist[cat];
    updateConfig({ ...s.config, checklist: { ...s.config.checklist, [cat]: list.includes(doc) ? list.filter((d) => d !== doc) : [...list, doc] } });
  };

  return (
    <div>
      <PageHeader title="Validation Engine" description="Local synthetic demo only. These browser rules and checklist settings are separate from the authenticated backend; backend validation runs are available on each application detail page."
        actions={<Button onClick={runAll} disabled={running}>{running && <Loader2 className="h-4 w-4 animate-spin" />}Run local demo on synthetic applications</Button>} />
      {lastRun && (
        <Panel title="Last run results" className="mb-6">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            {lastRun.map((r) => (
              <Link key={r.id} to="/review" search={{ app: r.id }} className="flex items-center justify-between rounded-md border p-3 text-sm hover:bg-muted">
                <span className="font-medium">{r.id}</span>
                <StatusBadge status={r.n === 0 ? "No Discrepancies" : r.high ? "High" : "Medium"} className="ml-2" />
                <span className="text-muted-foreground">{r.n} finding(s)</span>
              </Link>
            ))}
          </div>
        </Panel>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Active rules">
          <ol className="space-y-3 text-sm">
            {RULES.map((r) => (<li key={r.id} className="rounded-md border p-3"><span className="mr-2 rounded bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">{r.id}</span><span className="font-medium">{r.name}</span><p className="mt-1 text-muted-foreground">{r.description}</p></li>))}
          </ol>
          <p className="mt-4 text-xs text-muted-foreground">Mandatory fields: Institution ID, Institution Name, Category, Reference Number, Declared Faculty Count. Mismatches and duplicates are flagged for review only — they are never labelled as forgery.</p>
        </Panel>
        <Panel title="Required-document checklist (configurable)"
          actions={<Button size="sm" variant="ghost" onClick={() => { updateConfig(DEFAULT_CONFIG); toast.success("Checklist restored to defaults"); }}>Restore defaults</Button>}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr><th className="pb-2 text-left">Document</th>{APPLICATION_CATEGORIES.map((c) => <th key={c} className="px-1 pb-2 font-medium">{c}</th>)}</tr></thead>
              <tbody>
                {DOC_CATEGORIES.map((d) => (
                  <tr key={d} className="border-t">
                    <td className="py-2">{DOC_CATEGORY_LABELS[d]}</td>
                    {APPLICATION_CATEGORIES.map((c) => (
                      <td key={c} className="text-center"><input type="checkbox" aria-label={`${DOC_CATEGORY_LABELS[d]} required for ${c}`} checked={s.config.checklist[c].includes(d)} onChange={() => toggle(c, d)} /></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center gap-3 text-sm">
            <label htmlFor="warn">Expiry warning window (days)</label>
            <Input id="warn" type="number" min={0} className="w-24" value={s.config.expiryWarningDays}
              onChange={(e) => updateConfig({ ...s.config, expiryWarningDays: Math.max(0, Number(e.target.value) || 0) })} />
          </div>
          <p className="mt-3 text-xs text-muted-foreground">Changes are saved immediately and apply to all validation reports.</p>
        </Panel>
      </div>
    </div>
  );
}
