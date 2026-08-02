import { describe, expect, it } from "vitest";
import {
  displayCompany,
  discoveryFitOutOf5,
  isPlausibleCompany,
  scoreBadge,
} from "./display";
import type { Job } from "@/src/types/job";

function job(partial: Partial<Job>): Job {
  return {
    id: "1",
    url: "",
    source: "LinkedIn",
    company: null,
    title: "SRE",
    location: null,
    jd_text: null,
    salary: null,
    fit_score: 0,
    fit_reason: "",
    status: "New",
    discovered_at: null,
    ...partial,
  };
}

describe("isPlausibleCompany / displayCompany", () => {
  it("rejects digit and salary junk", () => {
    expect(isPlausibleCompany("1659474")).toBe(false);
    expect(isPlausibleCompany("3 ₹6L")).toBe(false);
    expect(isPlausibleCompany(".A Complex")).toBe(false);
    expect(displayCompany(job({ company: "1659474" }))).toBeNull();
    expect(displayCompany(job({ company: "Cisco" }))).toBe("Cisco");
  });
});

describe("scoreBadge", () => {
  it("maps discovery fit to /5", () => {
    expect(discoveryFitOutOf5(60)).toBe(3);
    const badge = scoreBadge(
      job({ eval_score: 4.6, eval_template_only: true, fit_score: 60 })
    );
    expect(badge.kind).toBe("discovery");
    expect(badge.label).toBe("3/5");
  });

  it("keeps full eval /5 when not template-only", () => {
    const badge = scoreBadge(job({ eval_score: 4.6, eval_template_only: false }));
    expect(badge.kind).toBe("eval");
    expect(badge.label).toBe("4.6/5");
  });
});
