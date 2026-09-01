import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "./page";

describe("Home", () => {
  it("shows the infrastructure baseline", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { name: "HawkFundOS is running." })).toBeInTheDocument();
    expect(screen.getByText("Phase 0 infrastructure baseline")).toBeInTheDocument();
  });
});
