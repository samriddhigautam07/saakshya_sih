import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DocumentIntegrityNotice } from "@/components/vw/DocumentIntegrityNotice";

describe("DocumentIntegrityNotice", () => {
  it("explains backend-confirmed exact duplicate hashes without alleging fraud", () => {
    render(<DocumentIntegrityNotice duplicate />);
    expect(screen.getByRole("status")).toHaveTextContent("Exact duplicate PDF content detected by SHA-256");
    expect(screen.getByRole("status")).toHaveTextContent("not a fraud determination");
  });

  it("does not display a duplicate warning for a unique document", () => {
    const { container } = render(<DocumentIntegrityNotice duplicate={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
