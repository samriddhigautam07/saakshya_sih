import { afterEach, describe, expect, it, vi } from "vitest";
import { api, getCategoryChecklist, getApplicationReviewReport, extractDocumentFields, newestDocumentExtraction, reprocessDocumentText, submitReviewDecision, setToken, ApiError } from "@/lib/api";

afterEach(() => { vi.unstubAllGlobals(); setToken(null); });

describe("Phase 10 API integrations", () => {
  it("sends the authenticated structured extraction request to the existing endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "x", document_id: "d1", provider: "mock", model: null, status: "complete", result: null, error_message: null, created_at: "2026-01-01T00:00:00Z" }), { status: 201, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock); setToken("test-token");
    await extractDocumentFields("APP/1", "DOC 1");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/applications/APP%2F1/documents/DOC%201/structured-extraction");
    expect(new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).get("Authorization")).toBe("Bearer test-token");
  });

  it("loads category checklist and JSON report from backend endpoints", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ application_category: "New Institution", configured: false, items: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ report_type: "prototype_review_support", disclaimer: "Advisory", application: {}, synthetic_data: false, latest_validation_run: null, applicable_rule_references: [], findings: [], verification_status: [], mock_verification_present: false, reviewer_decisions: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    expect((await getCategoryChecklist("New Institution")).items).toEqual([]);
    expect((await getApplicationReviewReport("APP-1")).report_type).toBe("prototype_review_support");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(expect.arrayContaining([expect.stringContaining("/api/regulatory/checklists/New%20Institution"), expect.stringContaining("/api/applications/APP-1/report")]));
  });

  it("retries PDF text extraction through the protected document API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "doc-1", application_id: "APP-1", extracted_text_char_count: 120, extraction_status: "text_extracted_with_ocr" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock); setToken("applicant-token");
    const result = await reprocessDocumentText("APP-1", "doc-1");
    expect(result.extracted_text_char_count).toBe(120);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/applications/APP-1/documents/doc-1/reprocess-text");
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).method).toBe("POST");
  });

  it("selects the newest persisted extraction even when the API array is newest-first", () => {
    const old = { id: "old", document_id: "d1", provider: "unconfigured", model: null, status: "provider_unavailable", result: null, error_message: "old", created_at: "2026-10-26T14:00:00Z" };
    const latest = { ...old, id: "latest", provider: "openai_compatible", model: "gemini-3.8-flash", status: "provider_error", error_message: "HTTP 503", created_at: "2026-10-26T16:00:00Z" };
    expect(newestDocumentExtraction([latest, old])?.id).toBe("latest");
    expect(newestDocumentExtraction([])).toBeNull();
  });

  it("posts reviewer decisions with the backend schema and surfaces API errors", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ id: "r1" }), { status: 201 })).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Official Reviewer role required." }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock); setToken("reviewer-token");
    await submitReviewDecision("APP-1", "F-1", "dismissed_finding", "Evidence is not applicable.");
    expect(JSON.parse((fetchMock.mock.calls[0]?.[1] as RequestInit).body as string)).toEqual({ decision: "dismissed_finding", reason: "Evidence is not applicable." });
    await expect(api("/api/applications/APP-1/findings/F-1/reviews", { method: "POST", body: JSON.stringify({ decision: "confirmed_issue", reason: "Confirmed." }) })).rejects.toMatchObject({ status: 403, message: "Official Reviewer role required." });
  });
});
