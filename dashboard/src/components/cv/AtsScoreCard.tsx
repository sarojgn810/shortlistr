"use client";

import { ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "@/src/components/ui/Button";
import type { AtsScore } from "@/src/lib/api/client";

interface AtsScoreCardProps {
  ats: AtsScore;
  onImprove?: () => void;
  onContinue?: () => void;
  continueLabel?: string;
  compact?: boolean;
}

function tierCopy(pct: number): { headline: string; detail: string } {
  if (pct >= 90) {
    return {
      headline: "Excellent ATS structure",
      detail: "Sections, keywords, and bullets are in a format parsers handle well.",
    };
  }
  if (pct >= 75) {
    return {
      headline: "Strong ATS structure",
      detail: "Most applicant tracking systems will parse this resume reliably.",
    };
  }
  if (pct >= 60) {
    return {
      headline: "Good foundation",
      detail: "Readable by ATS — fix the items below to strengthen parsing and keyword match.",
    };
  }
  return {
    headline: "Needs structural work",
    detail: "Missing sections or formatting ATS parsers expect. Address the gaps below.",
  };
}

export function AtsScoreCard({
  ats,
  onImprove,
  onContinue,
  continueLabel = "Continue",
  compact = false,
}: AtsScoreCardProps) {
  const pct = ats.content_score ?? ats.job_match_percent ?? ats.score;
  const fixes = ats.fixes ?? ats.checks.filter((c) => !c.ok).map((c) => ({
    label: c.label,
    hint: c.hint || "",
  }));
  const passed = ats.checks.filter((c) => c.ok);

  const { headline, detail } = tierCopy(pct);

  return (
    <div
      className={`rounded-2xl border border-mist bg-gradient-to-br from-sage/30 to-white ${
        compact ? "p-4" : "p-6"
      }`}
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-base text-stone">ATS readiness</p>
          <p className={`font-bold text-ink ${compact ? "text-3xl" : "text-5xl"}`}>
            {pct}
            <span className="text-2xl text-stone">%</span>
          </p>
          <p className="mt-1 text-base font-semibold text-ink">{headline}</p>
          <p className="mt-0.5 text-base text-stone">{detail}</p>
        </div>
        {!compact && (
          <div
            className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-lime/40 bg-lime/10 text-xl font-bold text-ink"
            aria-hidden
          >
            {pct}%
          </div>
        )}
      </div>

      {passed.length > 0 && !compact && (
        <div className="mt-5 space-y-2">
          <p className="text-sm font-bold text-stone">What looks good</p>
          <ul className="grid gap-1.5 sm:grid-cols-2">
            {passed.slice(0, 8).map((c) => (
              <li key={c.label} className="flex gap-2 text-base text-ink">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-lime-ink" />
                <span>
                  <strong>{c.label}</strong>
                  {c.hint ? <span className="text-stone"> — {c.hint}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {fixes.length > 0 && (
        <div className="mt-5 space-y-2">
          <p className="text-sm font-bold text-stone">
            {fixes.length === 1 ? "One fix remaining" : "Improve your score"}
          </p>
          <ul className="space-y-2">
            {fixes.slice(0, 5).map((fix) => (
              <li key={fix.label} className="flex gap-2 text-base text-ink">
                <AlertCircle size={16} className="mt-0.5 shrink-0 text-warning" />
                <span>
                  <strong>{fix.label}</strong>
                  {fix.hint ? ` — ${fix.hint}` : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(onImprove || onContinue) && (
        <div className="mt-6 flex flex-wrap gap-3">
          {onImprove && (
            <Button variant="secondary" onClick={onImprove}>
              Edit resume
            </Button>
          )}
          {onContinue && (
            <Button variant="lime" onClick={onContinue}>
              {continueLabel}
              <ArrowRight size={18} />
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
