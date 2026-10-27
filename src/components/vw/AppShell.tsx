import type { ReactNode } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard,
  FileStack,
  FilePlus2,
  Upload,
  ShieldCheck,
  BadgeCheck,
  ClipboardCheck,
} from "lucide-react";
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
  if (!user) return <div className="min-h-screen bg-background">
    <header className="border-b bg-card">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary font-bold text-primary-foreground">V</div>
        <div><p className="font-semibold leading-tight">VerifyWise AI</p><p className="text-xs text-muted-foreground">SIH26261 · Compliance assistance prototype</p></div>
      </div>
    </header>
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
  </div>;
  return (
    <div className="flex min-h-screen w-full flex-col bg-background lg:flex-row">
      <aside className="flex shrink-0 flex-col bg-sidebar text-sidebar-foreground lg:sticky lg:top-0 lg:h-screen lg:w-60">
        <div className="border-b border-sidebar-border px-4 py-3 lg:px-5 lg:py-5">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground font-bold">
              V
            </div>
            <div>
              <p className="font-semibold leading-tight">VerifyWise AI</p>
              <p className="text-[11px] opacity-70">SIH26261 · Prototype</p>
            </div>
          </div>
        </div>
        <nav
          aria-label="Main navigation"
          className="flex gap-1 overflow-x-auto p-2 lg:block lg:flex-1 lg:space-y-1 lg:overflow-y-auto lg:p-3"
        >
          <Link
            to="/login"
            className="hidden rounded-md px-3 py-2 text-sm opacity-80 transition hover:bg-sidebar-accent hover:opacity-100 lg:block"
          >
            {user ? user.email : "Backend sign in"}
          </Link>
          {NAV.filter((n) => n.to !== "/applications/new" || canCreateApplication(user?.role)).map(
            (n) => (
              <Link
                key={n.to}
                to={n.to}
                activeOptions={{ exact: true }}
                className="flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-xs opacity-80 outline-none transition hover:bg-sidebar-accent hover:opacity-100 focus-visible:ring-2 focus-visible:ring-sidebar-ring lg:gap-3 lg:text-sm"
                activeProps={{
                  className:
                    "!bg-sidebar-primary !text-sidebar-primary-foreground !opacity-100 font-medium",
                }}
              >
                <n.icon className="h-4 w-4" />
                {n.label}
              </Link>
            ),
          )}
        </nav>
        <div className="hidden border-t border-sidebar-border p-4 lg:block">
          {user && (
            <>
              <p className="mb-2 text-[11px] opacity-70">Signed in as {user.role}</p>
              <Button
                size="sm"
                variant="outline"
                className="mb-3 w-full"
                onClick={() => {
                  clearSession();
                  navigate({ to: "/login" });
                }}
              >
                Sign out
              </Button>
            </>
          )}
          <p className="text-[11px] leading-snug opacity-70">
            Backend-connected pages use authenticated API data. Validation Engine and Verification
            Status contain local synthetic or mock examples. Not an official AICTE system; no issuer
            portal is connected.
          </p>
        </div>
      </aside>
      <div className="flex items-center justify-between gap-3 border-b bg-sidebar px-4 py-2 text-xs text-sidebar-foreground lg:hidden">
        <Link to="/login" className="min-w-0 truncate opacity-80">
          {user ? `${user.email} · ${user.role}` : "Backend sign in"}
        </Link>
        {user && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              clearSession();
              navigate({ to: "/login" });
            }}
          >
            Sign out
          </Button>
        )}
      </div>
      <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-8 lg:py-6">{children}</main>
    </div>
  );
}
