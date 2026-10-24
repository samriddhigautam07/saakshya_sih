import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, INSTITUTION_RECORDS, SEED_APPLICATIONS } from "@/lib/domain/seed";
import { validateApplication } from "@/lib/validation/engine";
import { simulateIssuerCheck } from "@/lib/verification/mock-issuer";

const ctx = { records: INSTITUTION_RECORDS, allApplications: SEED_APPLICATIONS, config: DEFAULT_CONFIG, now: new Date("2026-10-24T00:00:00Z") };
const run = (i: number) => validateApplication(SEED_APPLICATIONS[i]!, ctx);

describe("validation rules on synthetic scenarios", () => {
  it("complete application has no findings", () => expect(run(0)).toEqual([]));
  it("flags missing fire safety certificate", () => expect(run(1).map((f) => f.id)).toContain("R2:fire_safety"));
  it("flags expired certificate", () => expect(run(2).some((f) => f.ruleId === "R3" && f.actual === "Expired on 2025-03-31")).toBe(true));
  it("flags institution ID mismatch with compared values", () => {
    const f = run(3).find((x) => x.ruleId === "R4")!;
    expect([f.expected, f.actual]).toEqual(["SYN-INST-1004", "SYN-INST-1040"]);
  });
  it("flags faculty count conflict 120 vs 96", () => {
    const f = run(4).find((x) => x.id === "R5:faculty")!;
    expect([f.expected, f.actual]).toEqual(["96", "120"]);
  });
  it("flags duplicate file hash", () => expect(run(5).some((f) => f.ruleId === "R6")).toBe(true));
  it("flags missing mandatory field", () => {
    const f = validateApplication({ ...SEED_APPLICATIONS[0]!, referenceNumber: "" }, ctx);
    expect(f.map((x) => x.id)).toContain("R1:referenceNumber");
  });
  it("mock issuer marks expired and is labelled mock", () => {
    const a = SEED_APPLICATIONS[2]!;
    const r = simulateIssuerCheck(a.documents.find((d) => d.category === "fire_safety")!, a, ctx.now);
    expect(r).toMatchObject({ status: "Expired", mock: true });
  });
});
