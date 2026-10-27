import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Role } from "@/lib/api";

const { navigate, login, registerInstitution, listApplications, setToken, setUser } = vi.hoisted(() => ({
  navigate: vi.fn(),
  login: vi.fn(),
  registerInstitution: vi.fn(),
  listApplications: vi.fn(),
  setToken: vi.fn(),
  setUser: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => () => ({}),
  useNavigate: () => navigate,
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
}));
vi.mock("@/lib/session", () => ({ useSession: () => null, setUser, clearSession: vi.fn() }));
vi.mock("@/lib/api", () => ({ login, registerInstitution, listApplications, setToken }));

import { LoginPage } from "@/routes/login";
import { InstitutionSignup } from "@/routes/signup";
import { Welcome } from "@/routes/index";
import { Applications } from "@/routes/applications.index";

describe("authentication entry flow", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows the public welcome screen with both entry options", () => {
    render(<Welcome />);
    expect(screen.getByRole("link", { name: "Login" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Institution Sign Up" })).toHaveAttribute("href", "/signup");
  });

  it("redirects unauthenticated visitors away from the applications route without requesting data", async () => {
    render(<Applications />);
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: "/login" }));
    expect(listApplications).not.toHaveBeenCalled();
  });

  it("shows backend login errors without creating a local session", async () => {
    login.mockRejectedValue(new Error("Invalid email or password."));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "member@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "incorrect-password" } });
    fireEvent.submit(screen.getByRole("button", { name: "Login" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(setToken).not.toHaveBeenCalled();
  });

  it.each<Role>(["Applicant / Institution", "Official Reviewer", "Rules Manager / Administrator"])(
    "redirects an authenticated %s account to its role-aware dashboard",
    async (role) => {
      login.mockResolvedValue({ access_token: "test-token", user: { id: "user-1", email: "user@example.test", role } });
      render(<LoginPage />);
      fireEvent.change(screen.getByLabelText("Email"), { target: { value: "USER@example.test" } });
      fireEvent.change(screen.getByLabelText("Password"), { target: { value: "safe-password" } });
      fireEvent.submit(screen.getByRole("button", { name: "Login" }).closest("form")!);
      await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: "/" }));
      expect(login).toHaveBeenCalledWith("user@example.test", "safe-password");
      expect(setToken).toHaveBeenCalledWith("test-token");
      expect(setUser).toHaveBeenCalledWith(expect.objectContaining({ role }));
    },
  );

  it("creates only an institution account and asks the user to sign in", async () => {
    registerInstitution.mockResolvedValue({ id: "user-1", email: "institution@example.test", role: "Applicant / Institution" });
    render(<InstitutionSignup />);
    fireEvent.change(screen.getByLabelText("Institution email"), { target: { value: "institution@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-safe-password-123" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "a-safe-password-123" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create institution account" }).closest("form")!);
    expect(await screen.findByRole("status")).toHaveTextContent("has been created");
    expect(registerInstitution).toHaveBeenCalledWith("institution@example.test", "a-safe-password-123");
    expect(setToken).not.toHaveBeenCalled();
  });

  it("rejects mismatched signup passwords before calling the API", async () => {
    render(<InstitutionSignup />);
    fireEvent.change(screen.getByLabelText("Institution email"), { target: { value: "institution@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-safe-password-123" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "different-safe-password" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create institution account" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("passwords do not match");
    expect(registerInstitution).not.toHaveBeenCalled();
  });
});
