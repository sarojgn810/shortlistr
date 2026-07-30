"use client";

import { Badge } from "@/src/components/ui/Badge";
import { Button } from "@/src/components/ui/Button";
import type { Job } from "@/src/types/job";

interface JobRowProps {
  job: Job;
  onView?: () => void;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: () => void;
}

function scoreLabel(job: Job): string {
  if (job.eval_score != null && job.eval_score > 0) return job.eval_score.toFixed(1);
  if (job.fit_score > 0) return (job.fit_score / 10).toFixed(1);
  return "—";
}

function channelLabel(c?: string): string {
  return c === "email" ? "Email" : c === "form" ? "Form" : c === "manual" ? "Manual" : "";
}

export default function JobRow({ job, onView, selectable, selected, onToggle }: JobRowProps) {
  return (
    <div
      className={`flex items-center gap-3 rounded-2xl border bg-white px-5 py-3.5 transition-colors ${
        selected ? "border-lime ring-1 ring-lime/40" : "border-mist/40 hover:border-mist"
      }`}
    >
      {selectable && (
        <input
          type="checkbox"
          checked={!!selected}
          onChange={onToggle}
          aria-label="Select job"
          className="h-4 w-4 shrink-0 rounded border-mist"
        />
      )}
      <div className="flex h-10 w-12 shrink-0 items-center justify-center rounded-lg bg-black text-sm font-bold text-lime">
        {scoreLabel(job)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-base font-bold text-ink">{job.title || "Role pending"}</p>
        <p className="truncate text-sm font-semibold text-stone opacity-70">
          {(job.company || "Company pending")} · {job.location || "Remote"}
          {job.salary ? ` · ${job.salary}` : ""}
          {job.experience ? ` · ${job.experience}` : ""}
        </p>
        {(job.skills?.length ?? 0) > 0 && (
          <p className="mt-0.5 truncate text-xs font-medium text-stone/70">
            {(job.skills || []).slice(0, 4).join(" · ")}
          </p>
        )}
      </div>
      <div className="hidden shrink-0 items-center gap-2 md:flex">
        {job.source && <Badge variant="default">{job.source}</Badge>}
        {job.apply_channel && <Badge variant="default">{channelLabel(job.apply_channel)}</Badge>}
        {job.eval_template_only && <Badge variant="orange">Template</Badge>}
        {job.legitimacy && <Badge variant="lime">{job.legitimacy}</Badge>}
        {job.pipeline_status && (
          <span className="text-xs font-bold uppercase tracking-widest text-stone/70">
            {job.pipeline_status}
          </span>
        )}
      </div>
      <Button variant="secondary" size="sm" onClick={onView} className="shrink-0">
        Review
      </Button>
    </div>
  );
}
