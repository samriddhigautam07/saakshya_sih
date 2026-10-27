import { afterEach, describe, expect, it, vi } from "vitest";
import {
  extractCorrectedDocumentFields,
  listDocumentCorrections,
  setToken,
  uploadDocumentCorrection,
} from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("corrected document API workflow", () => {
  it("uploads a corrected PDF using the authenticated private correction endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "correction-1",
          application_id: "APP-1",
          document_id: "DOC-1",
          version: 2,
          filename: "replacement.pdf",
          sha256: "abc",
          size_bytes: 100,
          extraction_status: "text_extracted",
          extracted_text_char_count: 75,
          uploaded_by: "applicant@example.test",
          uploaded_at: "2026-10-27T00:00:00Z",
          structured_extraction_status: null,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    setToken("applicant-token");
    const file = new File(["%PDF-1.7"], "replacement.pdf", { type: "application/pdf" });

    const uploaded = await uploadDocumentCorrection("APP-1", "DOC-1", file);

    expect(uploaded.version).toBe(2);
    expect(fetchMock.mock.calls[0]?.[0]).toContain(
      "/api/applications/APP-1/documents/DOC-1/corrections",
    );
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.method).toBe("POST");
    expect(new Headers(request.headers).get("Authorization")).toBe("Bearer applicant-token");
    expect((request.body as FormData).get("file")).toBe(file);
  });

  it("loads corrected versions and calls the existing structured extraction endpoint", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("[]", { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "extract-1",
            document_id: "correction-1",
            provider: "openai_compatible",
            model: "gemini-3.8-flash",
            status: "uncertain",
            result: null,
            error_message: null,
            created_at: "2026-10-27T00:00:00Z",
          }),
          { status: 201 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    expect(await listDocumentCorrections("APP-1", "DOC-1")).toEqual([]);
    await extractCorrectedDocumentFields("APP-1", "DOC-1", "correction-1");

    expect(fetchMock.mock.calls[1]?.[0]).toContain(
      "/corrections/correction-1/structured-extraction",
    );
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).method).toBe("POST");
  });
});
