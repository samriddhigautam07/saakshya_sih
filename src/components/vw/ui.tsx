import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "success" | "warning" | "danger" | "info" | "neutral" | "accent";
const TONES: Record<Tone, string> = {
  success: "bg-success/12 text-success border-success/30",
  warning: "bg-warning/15 text-warning-foreground border-warning/40",
  danger: "bg-destructive/10 text-destructive border-destructive/30",
  info: "bg-primary/8 text-primary border-primary/25",
  accent: "bg-accent text-accent-foreground border-accent-foreground/20",
  neutral: "bg-muted text-muted-foreground border-border",
};

const STATUS_TONE: Record<string, Tone> = {
  Verified: "success",
  "No Discrepancies": "success",
  "Review Completed": "success",
  Resolved: "success",
  "Ready for validation": "success",
  "Mismatch Detected": "danger",
  Expired: "danger",
  "Discrepancies Found": "danger",
  High: "danger",
  Escalated: "danger",
  "Upload error": "danger",
  "Manual Review Required": "warning",
  "Provider Unavailable": "warning",
  "Unable to Verify": "warning",
  "Pending Verification": "info",
  "Under Review": "warning",
  Medium: "warning",
  "Awaiting manual fields": "warning",
  "Source Unavailable": "neutral",
  "Verification Pending": "info",
  "Declared – file pending": "info",
  Open: "info",
  Low: "accent",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const inferredTone: Tone = /mismatch|inconsisten|issue found|expired|error/i.test(status)
    ? "danger"
    : /pending|provider unavailable|unable to verify|manual review|required/i.test(status)
      ? "warning"
      : "neutral";
  return (
    <span className={cn("inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium", TONES[STATUS_TONE[status] ?? inferredTone], className)}>
      {status}
    </span>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b pb-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-primary">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, children, className, actions }: { title?: string; children: ReactNode; className?: string; actions?: ReactNode }) {
  return (
    <section className={cn("rounded-lg border bg-card p-5 shadow-sm", className)}>
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-foreground">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading({ label = "Loading data…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground justify-center">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function MockLabel() {
  return <span className="rounded bg-warning/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-warning-foreground">Mock response</span>;
}

export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—");
export const fmtDateTime = (s: string) => new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
