import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Panel, PageHeader } from "@/components/vw/ui";
import { login, setToken } from "@/lib/api";
import { setUser } from "@/lib/session";

export const Route = createFileRoute("/login")({ component: LoginPage });

function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const result = await login(email, password);
      setToken(result.access_token); setUser(result.user);
      await navigate({ to: "/applications" });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="mx-auto max-w-xl">
    <PageHeader title="Backend sign in" description="Sign in with an account provisioned by a VerifyWise administrator." />
    <Panel title="Account credentials">
      <form className="space-y-4" onSubmit={submit}>
        <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="space-y-1.5"><Label htmlFor="password">Password</Label><Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        {error && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <p className="text-xs text-muted-foreground">Access tokens are kept in memory for this browser session. No public registration is available.</p>
      </form>
    </Panel>
  </div>;
}
