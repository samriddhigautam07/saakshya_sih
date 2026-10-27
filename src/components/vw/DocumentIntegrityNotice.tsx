export function DocumentIntegrityNotice({ duplicate }: { duplicate: boolean }) {
  if (!duplicate) return null;
  return (
    <p role="status" className="mt-2 rounded border border-warning/40 bg-warning/10 p-2 text-xs text-warning-foreground">
      Exact duplicate PDF content detected by SHA-256 within this application. Review the duplicate upload; this signal is not a fraud determination.
    </p>
  );
}
