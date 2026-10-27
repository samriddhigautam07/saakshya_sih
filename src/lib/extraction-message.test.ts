import { describe, expect, it } from "vitest";
import { extractionFailureMessage, pdfExtractionGuidance } from "@/lib/extraction-message";

describe("structured extraction failure guidance", () => {
  it.each([
    ["no_text", "No extracted document text is available."],
    [
      "provider_error",
      "The Gemini provider rate or quota limit was reached (HTTP 429). Retry after the limit resets.",
    ],
    ["provider_error", "The Gemini service is temporarily unavailable (HTTP 503). Retry later."],
    ["provider_error", "The configured extraction provider request timed out."],
    ["provider_unavailable", "No LLM provider is configured."],
    ["invalid_output", "The provider response did not match the extraction schema."],
  ])("explains %s without showing raw provider details", (status, errorMessage) => {
    const result = extractionFailureMessage({ status, error_message: errorMessage });
    expect(result).toMatch(/PDF text|provider|AI response/i);
    expect(result).not.toContain("Retry after the limit resets.");
    expect(result).not.toContain("No LLM provider is configured.");
    expect(result).not.toContain("The provider response did not match the extraction schema.");
  });

  it("does not disclose unexpected provider messages", () => {
    const result = extractionFailureMessage({
      status: "provider_error",
      error_message: "Bearer secret-value internal stack trace",
    });
    expect(result).toBe(
      "Structured extraction did not complete. The uploaded document and any stored PDF text remain unchanged.",
    );
    expect(result).not.toContain("secret-value");
    expect(result).not.toContain("stack trace");
  });

  it("explains OCR and corrupt-PDF states without suggesting structured extraction will fix them", () => {
    expect(pdfExtractionGuidance("scanned_ocr_unavailable")).toMatch(/Tesseract/i);
    expect(pdfExtractionGuidance("corrupt")).toMatch(/could not be processed/i);
    expect(pdfExtractionGuidance("text_extracted_with_ocr")).toBeNull();
  });
});
