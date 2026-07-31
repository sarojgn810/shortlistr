"use client";

import { MapPin, Clock, ArrowUpRight, Sparkles, Shield, Briefcase, Banknote } from "lucide-react";
import { Badge } from "@/src/components/ui/Badge";
import type { Job } from "@/src/types/job";
import { resolveApplyChannel } from "@/src/lib/applyChannel";

interface JobCardProps {
  job: Job;
  onView?: () => void;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: () => void;
}

function displayScore(job: Job): string {
  // Eval is already 0–5. Discovery fit_score is 0–100-ish; /10 was the
  // historical mapping but title+skills+location can exceed 50, which made
  // pending cards show impossible values like "6.0/5". Clamp the display.
  if (job.eval_score != null && job.eval_score > 0) {
    return `${Math.min(5, job.eval_score).toFixed(1)}/5`;
  }
  if (job.fit_score > 0) {
    return `${Math.min(5, job.fit_score / 10).toFixed(1)}/5`;
  }
  return "—";
}

function displayCompany(job: Job): string {
  if (job.company) return job.company;
  return "Company pending";
}

function displayTitle(job: Job): string {
  if (job.title) return job.title;
  return "Open to review role details";
}

function legitimacyVariant(tier?: string | null): "success" | "warning" | "error" | "default" {
  const t = (tier || "").toLowerCase();
  if (t.includes("verified") || t.includes("likely") || t.includes("high")) return "success";
  if (t.includes("suspicious") || t.includes("low")) return "error";
  if (t.includes("uncertain") || t.includes("medium")) return "warning";
  return "default";
}

export default function JobCard({ job, onView, selectable, selected, onToggle }: JobCardProps) {
  const company = displayCompany(job);
  const role = displayTitle(job);
  const location = job.location || "Remote";
  const scoreLabel = displayScore(job);
  const initial = company[0]?.toUpperCase() || "?";
  const skills = (job.skills || []).slice(0, 5);

  return (
    <div
      className={`group relative flex h-full flex-col justify-between overflow-hidden rounded-[28px] border bg-white p-5 shadow-sm transition-all hover:shadow-xl ${
        selected ? "border-lime ring-2 ring-lime/40" : "border-mist/30 hover:border-mist/60"
      }`}
    >
      {selectable && (
        <input
          type="checkbox"
          checked={!!selected}
          onChange={onToggle}
          onClick={(e) => e.stopPropagation()}
          aria-label="Select job"
          className="absolute left-4 top-4 z-30 h-5 w-5 rounded border-mist"
        />
      )}
      <div className="absolute right-0 top-0 z-20 flex items-center gap-1.5 rounded-bl-[20px] bg-black px-4 py-2 text-sm font-bold uppercase tracking-widest text-lime shadow-lg">
        <Sparkles size={14} className="fill-lime" />
        {scoreLabel}
      </div>

      <div>
        <div className="mb-4 flex items-start justify-between">
          <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black text-lg font-bold text-white shadow-lg transition-transform group-hover:scale-110">
            {initial}
          </div>
          <div className="mt-8 flex flex-col items-end gap-2">
            {job.legitimacy && (
              <Badge variant={legitimacyVariant(job.legitimacy)} className="gap-1">
                <Shield size={12} />
                {job.legitimacy}
              </Badge>
            )}
            {job.eval_template_only && (
              <Badge variant="orange" className="gap-1">
                Template mode
              </Badge>
            )}
            {(job.apply_channel || job.url || job.source) && (
              <Badge variant="default" className="gap-1">
                {(() => {
                  const ch = resolveApplyChannel(job);
                  if (ch === "email") return "Email apply";
                  if (ch === "form") return "Form apply";
                  if (ch === "link") return "Apply on site";
                  return "Manual apply";
                })()}
              </Badge>
            )}
          </div>
        </div>

        <div className="mb-4">
          <h3 className="mb-1 line-clamp-2 text-lg font-bold leading-tight tracking-tight text-ink transition-colors group-hover:text-lime-ink">
            {role}
          </h3>
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-stone opacity-70">
            <span>{company}</span>
            <span className="h-1 w-1 rounded-full bg-stone/40" />
            <span className="flex items-center gap-1">
              <MapPin size={12} /> {location}
            </span>
          </div>
        </div>

        {(job.salary || job.experience || job.source) && (
          <div className="mb-3 flex flex-wrap gap-2">
            {job.salary && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-mist/40 bg-sage/40 px-2.5 py-1 text-sm font-bold text-ink">
                <Banknote size={12} />
                {job.salary}
              </span>
            )}
            {job.experience && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-mist/40 bg-white px-2.5 py-1 text-sm font-bold text-stone">
                <Briefcase size={12} />
                {job.experience}
              </span>
            )}
            {job.source && (
              <span className="rounded-lg border border-mist/30 px-2.5 py-1 text-xs font-bold uppercase tracking-widest text-stone/70">
                {job.source}
              </span>
            )}
          </div>
        )}

        {skills.length > 0 && (
          <div className="mb-4 flex flex-wrap gap-1.5">
            {skills.map((s) => (
              <span
                key={s}
                className="rounded-md bg-mist/40 px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-ink/70"
              >
                {s}
              </span>
            ))}
          </div>
        )}

        {job.fit_reason && (
          <p className="mb-5 line-clamp-2 text-base font-medium leading-relaxed text-stone opacity-80">
            {job.fit_reason}
          </p>
        )}
      </div>

      <div className="mt-auto border-t border-mist/50 pt-5">
        <div className="mb-4 flex items-center justify-between">
          <span className="text-sm font-semibold text-stone opacity-70">
            {job.salary ? "Comp listed" : "Comp TBD"}
          </span>
          <span className="flex items-center gap-1.5 text-sm font-semibold text-stone opacity-70">
            <Clock size={14} />
            {job.pipeline_status || job.status}
          </span>
        </div>

        <button
          type="button"
          onClick={onView}
          className="group/btn flex w-full items-center justify-center gap-3 rounded-2xl bg-black py-4 font-bold text-white shadow-xl transition-all hover:bg-lime hover:text-black active:scale-95"
        >
          Review evaluation
          <ArrowUpRight
            size={20}
            className="transition-transform group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5"
          />
        </button>
      </div>
    </div>
  );
}
