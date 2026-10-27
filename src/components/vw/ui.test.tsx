import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "@/components/vw/ui";

describe("workflow status colors", () => {
  it("renders inconsistencies as errors and pending/provider states as warnings", () => {
    const { rerender } = render(<StatusBadge status="Detected inconsistency" />);
    expect(screen.getByText("Detected inconsistency").className).toContain("bg-destructive");
    rerender(<StatusBadge status="Provider Unavailable" />);
    expect(screen.getByText("Provider Unavailable").className).toContain("bg-warning");
    rerender(<StatusBadge status="Pending Verification" />);
    expect(screen.getByText("Pending Verification").className).toContain("bg-primary");
  });
});
