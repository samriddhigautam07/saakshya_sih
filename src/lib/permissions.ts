import type { Role } from "@/lib/api";

/** UI affordance only; the API remains responsible for enforcing this permission. */
export function canCreateApplication(role: Role | null | undefined): boolean {
  return role === "Applicant / Institution";
}
