import { useSyncExternalStore } from "react";
import { getToken, setToken, subscribeSession, type User } from "@/lib/api";

let currentUser: User | null = null;
const listeners = new Set<() => void>();
export function setUser(user: User | null) { currentUser = user; listeners.forEach((fn) => fn()); }
export function clearSession() { setToken(null); setUser(null); }
export function useSession() {
  return useSyncExternalStore((fn) => { listeners.add(fn); const off = subscribeSession(fn); return () => { listeners.delete(fn); off(); }; }, () => getToken() ? currentUser : null, () => null);
}
export function hasSession() { return Boolean(getToken() && currentUser); }
