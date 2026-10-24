import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { findingsFor, useStore } from "@/lib/store";
import { overallStatus } from "@/lib/validation/engine";
import { Empty, Loading, PageHeader, StatusBadge, fmtDate } from "@/components/vw/ui";

export const Route = createFileRoute("/applications/")({
  head: () => ({
    meta: [
      { title: "Applications — VerifyWise AI" },
      { name: "description", content: "Browse synthetic applications and their validation status." },
      { property: "og:title", content: "Applications — VerifyWise AI" },
      { property: "og:description", content: "Browse synthetic applications and their validation status." },
    ],
  }),
  component: Applications,
});

function Applications() {
  const s = useStore();
  const [q, setQ] = useState("");
  if (!s) return <Loading />;
  const rows = s.applications
    .filter((a) => `${a.id} ${a.institutionName} ${a.institutionId}`.toLowerCase().includes(q.toLowerCase()))
    .map((a) => ({ a, status: overallStatus(a, findingsFor(s, a)) }));
  return (
    <div>
      <PageHeader title="Applications" description="Open any application to inspect details, documents and its validation report."
        actions={<Button asChild><Link to="/applications/new">New application</Link></Button>} />
      <Input placeholder="Search by ID, institution name or institution ID…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-md" />
      {rows.length === 0 ? <Empty title="No applications match your search." /> : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-muted-foreground">
              <tr><th className="px-4 py-3">Application ID</th><th>Institution</th><th>Type</th><th>Submitted</th><th>Validation Status</th><th /></tr>
            </thead>
            <tbody>
              {rows.map(({ a, status }) => (
                <tr key={a.id} className="border-t hover:bg-muted/40">
                  <td className="px-4 py-3 font-medium text-primary">{a.id}</td>
                  <td><div>{a.institutionName || "—"}</div><div className="text-xs text-muted-foreground">{a.institutionId}</div></td>
                  <td>{a.category || "—"}</td>
                  <td>{fmtDate(a.submittedAt)}</td>
                  <td><StatusBadge status={status} /></td>
                  <td className="pr-4 text-right"><Button size="sm" variant="outline" asChild><Link to="/applications/$id" params={{ id: a.id }}>Open</Link></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
