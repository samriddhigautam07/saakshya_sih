import type { ReactNode } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { LayoutDashboard, FileStack, FilePlus2, Upload, ShieldCheck, BadgeCheck, ClipboardCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { clearSession, useSession } from "@/lib/session";
import { canCreateApplication } from "@/lib/permissions";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/applications", label: "Applications", icon: FileStack },
  { to: "/applications/new", label: "New Application", icon: FilePlus2 },
  { to: "/upload", label: "Document Upload", icon: Upload },
  { to: "/validation", label: "Validation Engine", icon: ShieldCheck },
  { to: "/verification", label: "Verification Status", icon: BadgeCheck },
  { to: "/review", label: "Results & Review", icon: ClipboardCheck },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const user = useSession();
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen w-full bg-background">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
        <div className="border-b border-sidebar-border px-5 py-5">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground font-bold">V</div>
            <div>
              <p className="font-semibold leading-tight">VerifyWise AI</p>
              <p className="text-[11px] opacity-70">SIH26261 · Prototype</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          <Link to="/login" className="flex items-center gap-3 rounded-md px-3 py-2 text-sm opacity-80 transition hover:bg-sidebar-accent hover:opacity-100">{user ? user.email : "Backend sign in"}</Link>
          {NAV.filter((n) => n.to !== "/applications/new" || canCreateApplication(user?.role)).map((n) => (
            <Link
              key={n.to}
              to={n.to}
              activeOptions={{ exact: true }}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm opacity-80 transition hover:bg-sidebar-accent hover:opacity-100"
              activeProps={{ className: "!bg-sidebar-primary !text-sidebar-primary-foreground !opacity-100 font-medium" }}
            >
              <n.icon className="h-4 w-4" />
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-sidebar-border p-4">
          {user && <><p className="mb-2 text-[11px] opacity-70">Signed in as {user.role}</p><Button size="sm" variant="outline" className="mb-3 w-full" onClick={() => { clearSession(); navigate({ to: "/login" }); }}>Sign out</Button></>}
          <p className="text-[11px] leading-snug opacity-70">Backend-connected pages show authenticated API data. Remaining prototype tools may use synthetic local data. Not an official AICTE system and not connected to any real portal or issuing authority.</p>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-6">{children}</main>
    </div>
  );
}
