import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App, { deserializeStructuredSections, serializeStructuredSections } from "./App";

describe("public entry experience", () => {
  it("shows the public landing page for logged-out visitors", () => {
    localStorage.clear();
    render(<App />);
    expect(screen.getByRole("heading", { name: /research-backed lessons/i })).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /create your first lesson/i })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Sign in" })).toHaveLength(2);
  });

  describe("structured lesson editor data", () => {
    it("round-trips repeatable sections without losing unrelated content", () => {
      const source = { outcomes: ["Identify charts"], time_plan: [{ section: "Intro", minutes: 5 }], references: [{ title: "Source", url: "https://example.com" }], summary: ["Takeaway"], introduction: "Keep me" };
      const draft = deserializeStructuredSections(source);
      draft.outcomes.push("Interpret patterns");
      const serialized = serializeStructuredSections(draft);
      expect(serialized.introduction).toBe("Keep me");
      expect(serialized.outcomes).toEqual(["Identify charts", "Interpret patterns"]);
      expect(serialized.references[0].url).toBe("https://example.com");
    });
  });
});
