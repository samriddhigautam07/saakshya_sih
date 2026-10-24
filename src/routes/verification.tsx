import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { logAudit, updateApplication, useStore } from "@/lib/store";
import { simulateIssuerCheck } from "@/lib/verification/mock-issuer";
import { DOC_CATEGORY_LABELS, type VerificationStatus } from "@/lib/domain/types";
import { Empty, Loading, MockLabel, PageHeader, Panel, StatusBadge, fmtDateTime } from "@/components/vw/ui";

export const Route = createFileRoute("/verification")({
  head: () => ({
    meta: [
      { title: "Verification Status — VerifyWise AI" },
      { name: "description", content: "Simulated issuer verification status for submitted documents (mock responses)." },
      { property: "og:title", content: "Verification Status — VerifyWise AI" },
      { property: "og:description", content: "Simulated issuer verification status for submitted documents." },
    ],
  }),
  component: VerificationPage,
});

const ALL: VerificationStatus[] = ["Verified", "Mismatch Detected", "Expired", "Verification Pending", "Source Unavailable", "Manual Review Required"];

function VerificationPage() {
  const s = useStore();
  const [busy, setBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState<VerificationStatus | "">("");
  if (!s) return <Loading />;

  const check = async (appId: string, docIds: string[]) => {
    setBusy(docIds.length > 1 ? "all" : (docIds[0] ?? null));
    await new Promise((r) => setTimeout(r, 600));
    updateApplication(appId, (a) => ({ ...a, documents: a.documents.map((d) => (docIds.includes(d.id) ? { ...d, verification: simulateIssuerCheck(d, a) } : d)) }));
    logAudit(appId, `Mock issuer verification run on ${docIds.length} document(s)`);
    setBusy(null);
  };
  const checkAll = async () => {
    setBusy("all");
    for (const a of s.applications) {
      updateApplication(a.id, (x) => ({ ...x, documents: x.documents.map((d) => ({ ...d, verification: simulateIssuerCheck(d, x) })) }));
    }
    await new Promise((r) => setTimeout(r, 600));
    setBusy(null);
    toast.success("Mock verification completed for all documents");
  };

  const rows = s.applications.flatMap((a) => a.documents.map((d) => ({ a, d })));
  const counts = Object.fromEntries(ALL.map((st) => [st, rows.filter((r) => r.d.verification?.status === st).length]));
  const shown = rows.filter((r) => !filter || r.d.verification?.status === filter);

  return (
    <div>
      <PageHeader title="Verification Status" description="Issuer verification is SIMULATED. No real issuing authority, DigiLocker or AICTE service is contacted."
        actions={<Button onClick={checkAll} disabled={!!busy}>{busy === "all" && <Loader2 className="h-4 w-4 animate-spin" />}Run mock verification on all</Button>} />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {ALL.map((st) => (
          <button key={st} onClick={() => setFilter(filter === st ? "" : st)} className={`rounded-lg border bg-card p-3 text-left shadow-sm transition hover:border-ring ${filter === st ? "ring-2 ring-ring" : ""}`}>
            <StatusBadge status={st} /><p className="mt-2 text-2xl font-semibold">{counts[st]}</p>
          </button>
        ))}
      </div>
      <Panel title={filter ? `Documents — ${filter}` : "All documents"} actions={<MockLabel />}>
        {shown.length === 0 ? <Empty title="No documents in this state.">Run mock verification or clear the filter.</Empty> : (
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground"><tr><th className="pb-2">Application</th><th>Document</th><th>Status</th><th>Mock response</th><th /></tr></thead>
            <tbody>
              {shown.map(({ a, d }) => (
                <tr key={d.id} className="border-t align-top">
                  <td className="py-2 font-medium">{a.id}</td>
                  <td>{DOC_CATEGORY_LABELS[d.category]}<div className="text-xs text-muted-foreground">{d.issuer || "Issuer not entered"}</div></td>
                  <td>{d.verification ? <StatusBadge status={d.verification.status} /> : <span className="text-muted-foreground">Not checked</span>}</td>
                  <td className="max-w-80 text-xs">{d.verification ? <>{d.verification.message}<div className="text-muted-foreground">{fmtDateTime(d.verification.checkedAt)}</div></> : "—"}</td>
                  <td className="text-right"><Button size="sm" variant="outline" disabled={!!busy} onClick={() => check(a.id, [d.id])}>{busy === d.id ? <Loader2 className="h-4 w-4 animate-spin" /> : "Check"}</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
