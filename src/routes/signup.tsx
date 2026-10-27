import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader, Panel } from "@/components/vw/ui";
import { registerInstitution } from "@/lib/api";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/signup")({ component: InstitutionSignup });

export function InstitutionSignup() {
  const user = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [createdEmail, setCreatedEmail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (user) void navigate({ to: "/" }); }, [user, navigate]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < 12) { setError("Use a password with at least 12 characters."); return; }
    if (password !== confirmation) { setError("The passwords do not match."); return; }
    setBusy(true);
    try {
      const created = await registerInstitution(email.trim().toLowerCase(), password);
      if (created.role !== "Applicant / Institution") throw new Error("Registration did not return an institution account. Contact the system administrator.");
      setCreatedEmail(created.email);
    } catch (cause) {
      setError((cause as Error).message || "Institution sign up failed. Please review your details and try again.");
    } finally { setBusy(false); }
  }

  if (user) return null;
  return <div className="mx-auto max-w-xl">
    <PageHeader title="Institution Sign Up" description="Create an Applicant / Institution account using the secure SAAKSHYA backend." />
    <Panel title={createdEmail ? "Account created" : "Institution account details"}>
      {createdEmail ? <div className="space-y-4"><p role="status" className="rounded-md border border-success/30 bg-success/10 p-3 text-sm">The Applicant / Institution account for <strong>{createdEmail}</strong> has been created. Sign in to continue.</p><Button asChild className="w-full"><Link to="/login">Go to Login</Link></Button></div> : <form className="space-y-4" onSubmit={(event) => void submit(event)}>
        <div className="space-y-1.5"><Label htmlFor="signup-email">Institution email</Label><Input id="signup-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></div>
        <div className="space-y-1.5"><Label htmlFor="signup-password">Password</Label><Input id="signup-password" type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} /><p className="text-xs text-muted-foreground">Use at least 12 characters.</p></div>
        <div className="space-y-1.5"><Label htmlFor="signup-confirmation">Confirm password</Label><Input id="signup-confirmation" type="password" autoComplete="new-password" required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></div>
        {error && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating account…" : "Create institution account"}</Button>
        <p className="text-center text-sm text-muted-foreground">Already registered? <Link className="font-medium text-primary underline" to="/login">Login</Link></p>
        <p className="text-xs text-muted-foreground">Public registration can create Applicant / Institution accounts only. Reviewer and Rules Manager roles cannot be selected here.</p>
      </form>}
    </Panel>
  </div>;
}
