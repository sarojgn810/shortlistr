"use client";

import { Badge } from "@/src/components/ui/Badge";
import { Button } from "@/src/components/ui/Button";
import type { Job } from "@/src/types/job";
import { resolveApplyChannel } from "@/src/lib/applyChannel";
import {
  displayCompany,
  displayLocation,
  displayTitle,
  isUnverified,
  scoreBadge,
} from "@/src/lib/jobs/display";

interface JobRowProps {
  job: Job;
  onView?: () => void;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: () => void;
}

function channelLabel(c?: string): string {
  if (c === "email") return "Email";
  if (c === "form") return "Form";
  if (c === "link") return "On site";
  return c === "manual" ? "Manual" : "";
}

function scoreSublabel(kind: ReturnType<typeof scoreBadge>["kind"]): string {
  if (kind === "eval") return "/5";
  if (kind === "discovery") return "/5";
  if (kind === "basic") return "basic";
  return "";
}

export default function JobRow({ job, onView, selectable, selected, onToggle }: JobRowProps) {
  const company = displayCompany(job);
  const location = displayLocation(job);
  const score = scoreBadge(job);
  const facts = [company, location, job.salary, job.experience].filter(Boolean);
  const channel = channelLabel(resolveApplyChannel(job));

  return (
    <div
      className={`flex gap-3 rounded-2xl border bg-white px-4 py-3.5 transition-colors sm:px-5 ${
        selected ? "border-lime ring-1 ring-lime/40" : "border-mist/40 hover:border-mist"
      }`}
    >
      {selectable && (
        <input
          type="checkbox"
          checked={!!selected}
          onChange={onToggle}
          aria-label="Select job"
          className="mt-2 h-4 w-4 shrink-0 rounded border-mist"
        />
      )}
      <div className="flex h-10 w-14 shrink-0 flex-col items-center justify-center rounded-lg bg-black text-lime">
        <span className="text-sm font-bold leading-none">{score.label.split("/")[0]}</span>
        <span className="text-[9px] font-bold uppercase tracking-wider opacity-70">
          {scoreSublabel(score.kind)}
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-bold text-ink" title={displayTitle(job)}>
              {displayTitle(job)}
            </p>
            <p
              className="truncate text-sm font-semibold text-stone opacity-70"
              title={facts.length > 0 ? facts.join(" · ") : undefined}
            >
              {facts.length > 0 ? facts.join(" · ") : "Details pending verification"}
            </p>
            {(job.skills?.length ?? 0) > 0 && (
              <p className="mt-0.5 truncate text-xs font-medium text-stone/70">
                {(job.skills || []).slice(0, 4).join(" · ")}
              </p>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={onView} className="shrink-0">
            Review
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {isUnverified(job) && <Badge variant="orange">Unverified</Badge>}
          {job.source && <Badge variant="default">{job.source}</Badge>}
          {channel && <Badge variant="default">{channel}</Badge>}
          {job.eval_template_only && <Badge variant="orange">Basic score</Badge>}
          {job.pipeline_status && (
            <span className="text-[11px] font-bold uppercase tracking-widest text-stone/60">
              {job.pipeline_status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
