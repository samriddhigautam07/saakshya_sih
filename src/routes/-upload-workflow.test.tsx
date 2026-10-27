import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  applications: vi.fn(), documents: vi.fn(), upload: vi.fn(),
  user: { role: "Applicant / Institution" },
}));
vi.mock("@tanstack/react-router", () => ({ createFileRoute: () => (config: { component: unknown }) => ({ ...config, useSearch: () => ({ app: "APP-1" }) }), useNavigate: () => mocks.navigate }));
vi.mock("@/lib/session", () => ({ useSession: () => mocks.user }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, listApplications: mocks.applications, listDocuments: mocks.documents, uploadDocument: mocks.upload };
});

import { UploadPage } from "@/routes/upload";

const application = { id: "APP-1", institution_name: "Example Institute", institution_id: "I-1" };
const uploadedDocument = { id: "D-1", application_id: "APP-1", category: "fire_safety", filename: "certificate.pdf", sha256: null, size_bytes: 10, uploaded_at: "2026-01-01", processing_status: "Ready for validation", extraction_status: "text_extracted", extracted_at: "2026-01-01", duplicate_hash_detected: false, extracted_text_char_count: 123, content_available: true, field_source: "none", issuer: "", document_number: "", issue_date: null, expiry_date: null, institution_id_on_doc: "" };

describe("institution document upload flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.applications.mockResolvedValue([application]);
    mocks.documents.mockResolvedValue([]);
  });

  it("reports upload completion and stored PDF extraction status", async () => {
    mocks.upload.mockResolvedValue(uploadedDocument);
    render(<UploadPage />);
    await screen.findByText(/Backend documents — APP-1/);
    const file = new File([new Uint8Array([37, 80, 68, 70, 45])], "certificate.pdf", { type: "application/pdf" });
    Object.defineProperty(file, "slice", { value: () => ({ arrayBuffer: async () => new Uint8Array([37, 80, 68, 70, 45]).buffer }) });
    fireEvent.change(screen.getByLabelText("PDF file (max 10 MB)"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload PDF" }));
    expect(await screen.findByRole("status")).toHaveTextContent("text_extracted · 123 characters");
    expect(mocks.upload).toHaveBeenCalledWith("APP-1", "fire_safety", file);
  });

  it("shows a retry action when application loading fails and recovers on retry", async () => {
    mocks.applications.mockRejectedValueOnce(new Error("Backend temporarily unavailable"));
    render(<UploadPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend temporarily unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry loading" }));
    await waitFor(() => expect(screen.getByText(/Backend documents — APP-1/)).toBeInTheDocument());
    expect(mocks.applications).toHaveBeenCalledTimes(2);
  });
});
