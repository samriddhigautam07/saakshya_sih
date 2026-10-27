import type { DocumentExtraction } from "@/lib/api";

export function extractionFailureMessage(
  extraction: Pick<DocumentExtraction, "status" | "error_message">,
): string {
  const detail = extraction.error_message ?? "";
  if (extraction.status === "no_text") {
    return "No extracted PDF text is available for structured extraction. Existing document records are preserved. Retry PDF text/OCR only if the text extraction status indicates it is safe to reprocess.";
  }
  if (
    extraction.status === "provider_unavailable" ||
    /no llm provider is configured|provider is not configured/i.test(detail)
  ) {
    return "Structured extraction is not configured on the backend. PDF text extraction remains available; no structured fields were generated.";
  }
  if (/HTTP\s*429|quota|rate limit/i.test(detail)) {
    return "The AI provider quota or rate limit is preventing structured extraction. PDF text and the uploaded file remain available. Check provider quota before manually retrying.";
  }
  if (/HTTP\s*503|temporarily unavailable/i.test(detail)) {
    return "The AI provider is temporarily unavailable. PDF text remains available. Retry manually later; no automatic retry was started.";
  }
  if (/timed out|timeout/i.test(detail)) {
    return "The structured extraction request timed out. PDF text and the uploaded file remain available. You can retry manually; automatic retries are disabled.";
  }
  if (/HTTP\s*401|authentication/i.test(detail)) {
    return "The backend could not authenticate with the configured AI provider. Contact the system administrator; the API key is never shown here.";
  }
  if (/HTTP\s*403|permission|billing/i.test(detail)) {
    return "The AI provider project does not currently have permission or billing access for this request. PDF text remains available.";
  }
  if (/HTTP\s*404|model was not found|endpoint/i.test(detail)) {
    return "The configured AI endpoint or model could not be found. Ask the system administrator to check the backend provider settings.";
  }
  if (extraction.status === "invalid_output") {
    return "The AI response did not match the required evidence-linked extraction format. No fields were accepted.";
  }
  return "Structured extraction did not complete. The uploaded document and any stored PDF text remain unchanged.";
}

export function pdfExtractionGuidance(status: string): string | null {
  switch (status) {
    case "scanned_ocr_unavailable":
    case "ocr_unavailable":
      return "This PDF appears to contain scanned pages, but OCR is unavailable in the backend environment. The uploaded PDF is preserved; ask an administrator to check Tesseract.";
    case "ocr_partial_failure":
      return "OCR could not read some scanned pages. Any text already extracted is preserved; review the document manually before relying on its fields.";
    case "encrypted":
      return "The PDF is encrypted and its text could not be read. Upload an authorized, readable copy if available.";
    case "corrupt":
    case "failed":
      return "The uploaded PDF could not be processed. The private file record remains; verify the PDF opens correctly before uploading a replacement.";
    case "empty":
      return "No readable text was found in this PDF. If it contains scanned pages, check whether OCR is available.";
    case "page_limit_exceeded":
      return "The PDF exceeds the configured page-processing limit. Ask an administrator about the allowed processing limit.";
    case "text_truncated":
      return "Text extraction reached the configured character limit. The stored text is partial and may need manual review.";
    case "ocr_timeout":
    case "processing_timeout":
      return "OCR exceeded its processing time limit. The PDF remains stored; review it manually or ask an administrator to check OCR settings.";
    case "ocr_page_limit_exceeded":
      return "The scanned PDF exceeds the configured OCR page limit. The original PDF is preserved; review the remaining pages manually.";
    case "ocr_page_too_large":
      return "A scanned page is too large for the configured OCR pixel limit. The original PDF is preserved for manual review.";
    default:
      return null;
  }
}
