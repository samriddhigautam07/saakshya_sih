import { createFileRoute, Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { findingsFor, useStore } from "@/lib/store";
import { overallStatus } from "@/lib/validation/engine";
import { INSTITUTION_RECORDS } from "@/lib/domain/seed";
import { DOC_CATEGORY_LABELS } from "@/lib/domain/types";
import { Empty, Loading, MockLabel, PageHeader, Panel, StatusBadge, fmtDate } from "@/components/vw/ui";

export const Route = createFileRoute("/applications/$id")({
  head: ({ params }) => ({
    meta: [
      { title: `${params.id} — VerifyWise AI` },
      { name: "description", content: `Details, documents and validation summary for application ${params.id}.` },
      { property: "og:title", content: `${params.id} — VerifyWise AI` },
      { property: "og:description", content: `Details and validation summary for application ${params.id}.` },
    ],
  }),
  component: Detail,
});

function Detail() {
  const { id } = Route.useParams();
  const s = useStore();
  if (!s) return <Loading />;
  const a = s.applications.find((x) => x.id === id);
  if (!a) return <Empty title={`Application ${id} not found.`}><Link to="/applications" className="text-accent-foreground underline">Back to applications</Link></Empty>;
  const f = findingsFor(s, a);
  const rec = INSTITUTION_RECORDS.find((r) => r.institutionId === a.institutionId);
  const kv = (k: string, v: React.ReactNode) => (<div><dt className="text-xs text-muted-foreground">{k}</dt><dd className="font-medium">{v || "—"}</dd></div>);

  return (
    <div>
      <PageHeader title={a.id} description={a.institutionName || "Unnamed institution"}
        actions={<>
          <Button variant="outline" asChild><Link to="/upload" search={{ app: a.id }}>Upload documents</Link></Button>
          <Button asChild><Link to="/review" search={{ app: a.id }}>Open validation report</Link></Button>
        </>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Application details" className="lg:col-span-2">
          <dl className="grid grid-cols-2 gap-4 text-sm md:grid-cols-3">
            {kv("Institution ID", a.institutionId)}
            {kv("Category", a.category)}
            {kv("Reference number", a.referenceNumber)}
            {kv("Submitted", fmtDate(a.submittedAt))}
            {kv("Declared faculty", a.declaredFacultyCount ?? "")}
            {kv("Validation status", <StatusBadge status={overallStatus(a, f)} />)}
          </dl>
        </Panel>
        <Panel title="Synthetic institutional record">
          {rec ? (
            <dl className="space-y-3 text-sm">{kv("Name on record", rec.name)}{kv("Faculty on record", rec.facultyCount)}{kv("State", rec.state)}</dl>
          ) : <p className="text-sm text-muted-foreground">No synthetic record found for this institution ID.</p>}
        </Panel>
      </div>
      <Panel title={`Documents (${a.documents.length})`} className="mt-6">
        {a.documents.length === 0 ? <Empty title="No documents submitted yet." /> : (
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground"><tr><th className="pb-2">Category</th><th>File</th><th>Issuer</th><th>Doc no.</th><th>Expiry</th><th>Processing</th><th>Verification</th></tr></thead>
            <tbody>
              {a.documents.map((d) => (
                <tr key={d.id} className="border-t align-top">
                  <td className="py-2">{DOC_CATEGORY_LABELS[d.category]}</td>
                  <td className="max-w-48 truncate">{d.filename ?? "—"}</td>
                  <td>{d.issuer || "—"}</td>
                  <td>{d.documentNumber || "—"}</td>
                  <td>{fmtDate(d.expiryDate)}</td>
                  <td><StatusBadge status={d.processingStatus} /></td>
                  <td>{d.verification ? <div className="space-y-1"><StatusBadge status={d.verification.status} /> <MockLabel /></div> : <span className="text-muted-foreground">Not checked</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <Panel title={`Validation summary — ${f.length} finding(s)`} className="mt-6">
        {f.length === 0 ? <p className="text-sm text-success">No discrepancies detected by the current rule set.</p> : (
          <ul className="space-y-2 text-sm">
            {f.map((x) => (<li key={x.id} className="flex items-center gap-2"><StatusBadge status={x.severity} /><span className="font-medium">{x.ruleName}:</span> {x.message}</li>))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
