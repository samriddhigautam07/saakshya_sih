import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Empty, Loading, PageHeader, StatusBadge, fmtDate } from "@/components/vw/ui";
import { ApiError, listApplications, type Application } from "@/lib/api";
import { useSession } from "@/lib/session";

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
  const user = useSession();
  const navigate = useNavigate();
  const [items, setItems] = useState<Application[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    if (!user) { void navigate({ to: "/login" }); return; }
    listApplications().then(setItems).catch((e: ApiError) => { setError(e.message); setItems([]); });
  }, [user, navigate]);
  if (!user || items === null) return <Loading />;
  const rows = items.filter((a) => `${a.id} ${a.institution_name} ${a.institution_id}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <PageHeader title="Applications" description="Authenticated application records returned by the VerifyWise backend."
        actions={<Button asChild><Link to="/applications/new">New application</Link></Button>} />
      {error && <p role="alert" className="mb-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      <Input placeholder="Search by ID, institution name or institution ID…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-md" />
      {rows.length === 0 ? <Empty title={error ? "Applications could not be loaded." : q ? "No applications match your search." : "No backend applications yet."} /> : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-muted-foreground">
              <tr><th className="px-4 py-3">Application ID</th><th>Institution</th><th>Type</th><th>Submitted</th><th>Validation Status</th><th /></tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} className="border-t hover:bg-muted/40">
                  <td className="px-4 py-3 font-medium text-primary">{a.id}</td>
                  <td><div>{a.institution_name || "—"}</div><div className="text-xs text-muted-foreground">{a.institution_id}</div></td>
                  <td>{a.category || "—"}</td>
                  <td>{fmtDate(a.submitted_at)}</td>
                  <td><StatusBadge status={a.findings.length ? "Issue Found" : "Not yet validated"} /></td>
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
