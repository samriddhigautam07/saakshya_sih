import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Panel, PageHeader } from "@/components/vw/ui";
import { login, setToken } from "@/lib/api";
import { setUser, useSession } from "@/lib/session";

export const Route = createFileRoute("/login")({ component: LoginPage });

export function LoginPage() {
  const navigate = useNavigate();
  const user = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (user) void navigate({ to: "/" }); }, [user, navigate]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const result = await login(email.trim().toLowerCase(), password);
      setToken(result.access_token); setUser(result.user);
      // The root dashboard selects the institution, reviewer, or rules-manager view
      // from the backend-authenticated role returned above.
      await navigate({ to: "/" });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  if (user) return null;
  return <div className="mx-auto max-w-xl">
    <PageHeader title="Login" description="Sign in to continue to the dashboard for your authenticated account." />
    <Panel title="Account credentials">
      <form className="space-y-4" onSubmit={submit}>
        <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="space-y-1.5"><Label htmlFor="password">Password</Label><Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        {error && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Login"}</Button>
        <p className="text-center text-sm text-muted-foreground">Institution account not created yet? <Link className="font-medium text-primary underline" to="/signup">Institution Sign Up</Link></p>
        <p className="text-xs text-muted-foreground">Authentication uses the VerifyWise backend. Access tokens remain in memory for this browser session.</p>
      </form>
    </Panel>
  </div>;
}
