import { createFileRoute, Link } from "@tanstack/react-router";
import { FileStack, Clock, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { findingsFor, resetDemo, useStore } from "@/lib/store";
import { overallStatus } from "@/lib/validation/engine";
import { Loading, PageHeader, Panel, StatusBadge, fmtDate } from "@/components/vw/ui";
import { toast } from "sonner";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dashboard — VerifyWise AI" },
      { name: "description", content: "Overview of synthetic applications, pending reviews and detected discrepancies." },
      { property: "og:title", content: "Dashboard — VerifyWise AI" },
      { property: "og:description", content: "Overview of synthetic applications, pending reviews and detected discrepancies." },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const s = useStore();
  if (!s) return <Loading />;
  const rows = s.applications.map((a) => {
    const f = findingsFor(s, a);
    return { a, f, status: overallStatus(a, f) };
  });
  const stats = [
    { label: "Total Applications", value: rows.length, icon: FileStack, tone: "text-primary" },
    { label: "Pending Reviews", value: rows.filter((r) => r.status === "Discrepancies Found" || r.status === "Under Review").length, icon: Clock, tone: "text-accent-foreground" },
    { label: "With Discrepancies", value: rows.filter((r) => r.f.length > 0).length, icon: AlertTriangle, tone: "text-destructive" },
    { label: "Completed Reviews", value: rows.filter((r) => r.status === "Review Completed" || r.status === "No Discrepancies").length, icon: CheckCircle2, tone: "text-success" },
  ];
  const ruleCounts = new Map<string, number>();
  rows.forEach((r) => r.f.forEach((f) => ruleCounts.set(f.ruleName, (ruleCounts.get(f.ruleName) ?? 0) + 1)));

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="AICTE-style application validation overview. All institutions and records shown are synthetic demonstration data."
        actions={
          <Button variant="outline" onClick={() => { if (confirm("Reset all demo data and review history?")) { resetDemo(); toast.success("Demo data reset"); } }}>
            Reset demo data
          </Button>
        }
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((x) => (
          <div key={x.label} className="rounded-lg border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">{x.label}</p>
              <x.icon className={`h-5 w-5 ${x.tone}`} />
            </div>
            <p className="mt-2 text-3xl font-semibold">{x.value}</p>
          </div>
        ))}
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Panel title="Recent applications" className="lg:col-span-2" actions={<Link to="/applications" className="text-sm text-accent-foreground hover:underline">View all</Link>}>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground"><tr><th className="pb-2">ID</th><th>Institution</th><th>Submitted</th><th>Findings</th><th>Status</th></tr></thead>
            <tbody>
              {rows.slice(0, 6).map(({ a, f, status }) => (
                <tr key={a.id} className="border-t">
                  <td className="whitespace-nowrap py-2 pr-3"><Link to="/applications/$id" params={{ id: a.id }} className="font-medium text-primary hover:underline">{a.id}</Link></td>
                  <td>{a.institutionName || "—"}</td>
                  <td className="whitespace-nowrap pr-3">{fmtDate(a.submittedAt)}</td>
                  <td className="pr-3 text-center">{f.length}</td>
                  <td><StatusBadge status={status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Findings by rule">
          {ruleCounts.size === 0 ? <p className="text-sm text-muted-foreground">No findings detected.</p> : (
            <ul className="space-y-3 text-sm">
              {[...ruleCounts].map(([k, v]) => (
                <li key={k}>
                  <div className="flex justify-between"><span>{k}</span><span className="font-medium">{v}</span></div>
                  <div className="mt-1 h-1.5 rounded bg-muted"><div className="h-1.5 rounded bg-sidebar-primary" style={{ width: `${Math.min(100, v * 25)}%` }} /></div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-6 text-xs text-muted-foreground">Validation is deterministic and rule-based. No machine-learning model is used in this prototype.</p>
        </Panel>
      </div>
    </div>
  );
}
