/** Shared display helpers for Discover cards / rows / drawer. */

import type { Job } from "@/src/types/job";

/** Scorer noise — never show these as a human summary on cards. */
const NOISE_FIT_REASON =
  /^(title match|jd not fetched|preferred location|disqualifier found|keyword match|location match)/i;

export function isNoiseFitReason(reason?: string | null): boolean {
  const r = (reason || "").trim();
  if (!r) return true;
  // Entire string is only scorer fragments joined by "; "
  const parts = r.split(";").map((p) => p.trim()).filter(Boolean);
  return parts.length > 0 && parts.every((p) => NOISE_FIT_REASON.test(p));
}

export function displayTitle(job: Pick<Job, "title">): string {
  return (job.title || "").trim() || "Role pending";
}

/** Reject parse junk that sometimes lands in company (job ids, salary fragments). */
export function isPlausibleCompany(name?: string | null): boolean {
  const c = (name || "").trim();
  if (!c || /^(unknown|untitled|company pending|n\/a|na|tbd|\?)$/i.test(c)) return false;
  if (/^\d+$/.test(c)) return false;
  if (/^\./.test(c)) return false;
  if (/₹|\d+\s*L(?:PA)?\b/i.test(c)) return false;
  if (/^[\d\W_]+$/.test(c)) return false;
  return true;
}

export function displayCompany(job: Pick<Job, "company">): string | null {
  const c = (job.company || "").trim();
  if (!isPlausibleCompany(c)) return null;
  return c;
}

export function displayLocation(job: Pick<Job, "location">): string | null {
  const loc = (job.location || "").trim();
  return loc || null;
}

/** Discovery fit is stored 0–100; Discover always displays on the 0–5 scale. */
export function discoveryFitOutOf5(fit100: number): number {
  if (!Number.isFinite(fit100) || fit100 <= 0) return 0;
  return Math.min(5, Math.max(0, Math.round(fit100 / 20)));
}

export function formatScoreOutOf5(score: number, decimals = 1): string {
  const n = Math.min(5, Math.max(0, Number(score) || 0));
  if (decimals <= 0) return `${Math.round(n)}/5`;
  return `${n.toFixed(decimals)}/5`;
}

export function scoreBadge(
  job: Job
): { label: string; kind: "eval" | "discovery" | "basic" | "none" } {
  // Keyword-only ("Basic score") must not look like a full A–G judgment —
  // still show /5 so Discover has one scale.
  if (job.eval_template_only) {
    if (job.fit_score > 0) {
      return {
        label: formatScoreOutOf5(discoveryFitOutOf5(job.fit_score), 0),
        kind: "discovery",
      };
    }
    if (job.eval_score != null && job.eval_score > 0) {
      return { label: formatScoreOutOf5(job.eval_score), kind: "basic" };
    }
    return { label: "—", kind: "none" };
  }
  if (job.eval_score != null && job.eval_score > 0) {
    return { label: formatScoreOutOf5(job.eval_score), kind: "eval" };
  }
  if (job.fit_score > 0) {
    return {
      label: formatScoreOutOf5(discoveryFitOutOf5(job.fit_score), 0),
      kind: "discovery",
    };
  }
  return { label: "—", kind: "none" };
}

export function isUnverified(job: Job): boolean {
  return (job.verification || "").toLowerCase() === "unverified";
}
