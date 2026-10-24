/**
 * MOCK issuer verification. No real issuing authority or AICTE system is contacted.
 * Responses are derived deterministically from the document's own fields.
 */
import type { AppDocument, Application, VerificationResult } from "@/lib/domain/types";

export function simulateIssuerCheck(doc: AppDocument, app: Application, now = new Date()): VerificationResult {
  const base = { checkedAt: now.toISOString(), mock: true as const };
  if (!doc.filename) return { ...base, status: "Verification Pending", message: "Mock: no file uploaded yet." };
  if (doc.fieldSource === "none" || !doc.issuer)
    return { ...base, status: "Verification Pending", message: "Mock: document fields not entered; cannot query issuer." };
  if (/unavailable|offline/i.test(doc.issuer))
    return { ...base, status: "Source Unavailable", message: "Mock: simulated issuer registry did not respond." };
  if (!doc.documentNumber)
    return { ...base, status: "Manual Review Required", message: "Mock: no document number to look up." };
  if (doc.institutionIdOnDoc && doc.institutionIdOnDoc !== app.institutionId)
    return { ...base, status: "Mismatch Detected", message: `Mock: issuer record lists ${doc.institutionIdOnDoc}, application lists ${app.institutionId}.` };
  if (doc.expiryDate && new Date(doc.expiryDate + "T23:59:59") < now)
    return { ...base, status: "Expired", message: `Mock: issuer record shows validity ended ${doc.expiryDate}.` };
  if (doc.fieldSource === "manual")
    return { ...base, status: "Manual Review Required", message: "Mock: fields were entered manually; confirm against the original document." };
  return { ...base, status: "Verified", message: "Mock: simulated issuer record matches the document number." };
}
