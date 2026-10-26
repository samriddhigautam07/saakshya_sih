import { describe, expect, it } from "vitest";
import { getRouter } from "@/router";
import { canCreateApplication } from "@/lib/permissions";

describe("application creation navigation", () => {
  it("matches /applications/new to the static creation route", () => {
    const matches = getRouter().matchRoutes("/applications/new");
    expect(matches.at(-1)?.routeId).toBe("/applications/new");
  });

  it("exposes application creation only to applicant accounts", () => {
    expect(canCreateApplication("Applicant / Institution")).toBe(true);
    expect(canCreateApplication("Official Reviewer")).toBe(false);
    expect(canCreateApplication("Rules Manager / Administrator")).toBe(false);
    expect(canCreateApplication(null)).toBe(false);
  });
});
