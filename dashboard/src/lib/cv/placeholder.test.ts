import { describe, expect, it } from "vitest";

import { isPlaceholderCv } from "./placeholder";

describe("isPlaceholderCv", () => {
  it("treats empty / whitespace as placeholder", () => {
    expect(isPlaceholderCv("")).toBe(true);
    expect(isPlaceholderCv("   \n  ")).toBe(true);
  });

  it("flags the default onboarding template (>=3 markers) as placeholder", () => {
    const template = [
      "# Your Name",
      "email@example.com | linkedin.com/in/you",
      "Your Title | Company",
      "- One measurable win",
    ].join("\n");
    expect(isPlaceholderCv(template)).toBe(true);
  });

  it("treats a real résumé (any field, any region) as NOT placeholder", () => {
    const real = [
      "# Jane Okafor",
      "jane.okafor@gmail.com | Lagos, Nigeria",
      "## Experience",
      "Senior Nurse at Lagos General — led a ward of 20 staff, cut wait times 25%.",
      "## Education",
      "BSc Nursing, University of Lagos",
    ].join("\n");
    expect(isPlaceholderCv(real)).toBe(false);
  });
});
