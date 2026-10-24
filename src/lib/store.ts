/** Persistent browser storage (localStorage) for applications, review decisions and audit history. */
import { useSyncExternalStore } from "react";
import { DEFAULT_CONFIG, INSTITUTION_RECORDS, SEED_APPLICATIONS } from "@/lib/domain/seed";
import type { Application, FindingStatus, ValidationConfig } from "@/lib/domain/types";
import { validateApplication, type ValidationContext } from "@/lib/validation/engine";

const KEY = "verifywise-ai.v1";
export interface StoreState {
  applications: Application[];
  config: ValidationConfig;
}

let state: StoreState | null = null;
const listeners = new Set<() => void>();

function fresh(): StoreState {
  return { applications: structuredClone(SEED_APPLICATIONS), config: structuredClone(DEFAULT_CONFIG) };
}
function get(): StoreState {
  if (!state) {
    try {
      const raw = localStorage.getItem(KEY);
      state = raw ? (JSON.parse(raw) as StoreState) : fresh();
    } catch {
      state = fresh();
    }
  }
  return state;
}
function set(next: StoreState) {
  state = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    throw new Error("Could not save to browser storage (storage may be full or disabled).");
  }
  listeners.forEach((l) => l());
}
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** Returns null during server render / before hydration → callers show a loading state. */
export function useStore(): StoreState | null {
  return useSyncExternalStore(subscribe, get, () => null);
}

export function ctxFor(s: StoreState): ValidationContext {
  return { records: INSTITUTION_RECORDS, allApplications: s.applications, config: s.config, now: new Date() };
}
export function findingsFor(s: StoreState, app: Application) {
  return validateApplication(app, ctxFor(s));
}

const uid = () => Math.random().toString(36).slice(2, 10);

export function updateApplication(id: string, fn: (a: Application) => Application) {
  const s = get();
  set({ ...s, applications: s.applications.map((a) => (a.id === id ? fn(a) : a)) });
}

export function addApplication(a: Omit<Application, "id" | "audit" | "findingStatuses">): string {
  const s = get();
  const n = s.applications.length + 1;
  let id = `APP-2026-${String(n).padStart(3, "0")}`;
  while (s.applications.some((x) => x.id === id)) id += "A";
  const app: Application = {
    ...a,
    id,
    findingStatuses: {},
    audit: [{ id: uid(), at: new Date().toISOString(), actor: "Reviewer (demo)", action: "Application created" }],
  };
  set({ ...s, applications: [app, ...s.applications] });
  return id;
}

export function logAudit(appId: string, action: string, extra: Partial<Application["audit"][number]> = {}) {
  updateApplication(appId, (a) => ({
    ...a,
    audit: [...a.audit, { id: uid(), at: new Date().toISOString(), actor: "Reviewer (demo)", action, ...extra }],
  }));
}

export function setFindingStatus(appId: string, findingId: string, to: FindingStatus, note: string) {
  updateApplication(appId, (a) => {
    const from = a.findingStatuses[findingId] ?? "Open";
    return {
      ...a,
      findingStatuses: { ...a.findingStatuses, [findingId]: to },
      audit: [
        ...a.audit,
        { id: uid(), at: new Date().toISOString(), actor: "Reviewer (demo)", action: "Finding status changed", findingId, from, to, ...(note ? { note } : {}) },
      ],
    };
  });
}

export function updateConfig(config: ValidationConfig) {
  set({ ...get(), config });
}

export function resetDemo() {
  set(fresh());
}

export { uid };
