import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  role: "Applicant / Institution" as string,
  applicantUser: { role: "Applicant / Institution" },
  managerUser: { role: "Rules Manager / Administrator" },
  navigate: vi.fn(),
  sources: vi.fn(), rules: vi.fn(), audit: vi.fn(), checklist: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({ createFileRoute: () => () => ({}), useNavigate: () => mocks.navigate }));
vi.mock("@/lib/session", () => ({ useSession: () => mocks.role === "Rules Manager / Administrator" ? mocks.managerUser : mocks.applicantUser }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, listRegulatorySources: mocks.sources, listRegulatoryRules: mocks.rules, getRegulatoryAuditHistory: mocks.audit, getCategoryChecklist: mocks.checklist };
});

import { RulesWorkspace } from "@/routes/rules";

describe("Rules Manager workspace authorization", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.role = "Applicant / Institution";
    mocks.sources.mockResolvedValue([]); mocks.rules.mockResolvedValue([]); mocks.audit.mockResolvedValue([]); mocks.checklist.mockResolvedValue({ configured: false, items: [] });
  });

  it("does not request regulatory management data for an applicant", async () => {
    render(<RulesWorkspace />);
    expect(await screen.findByText(/available only to Rules Manager/)).toBeInTheDocument();
    expect(mocks.sources).not.toHaveBeenCalled();
    expect(mocks.rules).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Register source metadata" })).not.toBeInTheDocument();
  });

  it("loads actual workspace collections only for the Rules Manager role", async () => {
    mocks.role = "Rules Manager / Administrator";
    render(<RulesWorkspace />);
    expect(await screen.findByText("No regulatory sources are registered.")).toBeInTheDocument();
    await waitFor(() => expect(mocks.sources).toHaveBeenCalledTimes(1));
    expect(mocks.rules).toHaveBeenCalledTimes(1);
    expect(mocks.audit).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/does not fetch it/)).toBeInTheDocument();
  });
});
