"use client";

import { useEffect } from "react";
import { ExternalLink, X } from "lucide-react";
import { Button } from "@/src/components/ui/Button";
import { Badge } from "@/src/components/ui/Badge";
import { Skeleton } from "@/src/components/ui/Skeleton";
import { useSetupStatus } from "@/src/hooks/useSetupStatus";
import type {
  Job,
  EvalResult,
  ExplainResult,
  ResumeDiff,
  ApplicationReceipt,
} from "@/src/types/job";
import { plainJobDescription } from "@/src/lib/text";
import { isLinkOnlyJob } from "@/src/lib/applyChannel";
import { displayCompany, displayTitle, discoveryFitOutOf5, formatScoreOutOf5 } from "@/src/lib/jobs/display";

const BLOCK_LABELS: Record<string, string> = {
  // Keep in sync with automation/eval/prompts/evaluate_v1.txt
  A: "Role summary & fit",
  B: "Requirements match",
  C: "Compensation & logistics",
  D: "Risks & gaps",
  E: "Application strategy",
  F: "Interview angles",
  G: "Legitimacy",
};

interface JobDetailModalProps {
  job: Job | null;
  explain: ExplainResult | Record<string, unknown> | null;
  evalResult: EvalResult | null;
  diff?: ResumeDiff | null;
  receipts?: ApplicationReceipt[];
  isOpen: boolean;
  isLoading: boolean;
  isEvaluating: boolean;
  onClose: () => void;
  onEvaluate: () => void;
  onApprove?: () => void;
  onSkip?: () => void;
  onMarkApplied?: () => void;
  isApproving?: boolean;
  isSkipping?: boolean;
  isMarkingApplied?: boolean;
  onApplyAssist?: () => void;
  isApplyAssisting?: boolean;
  applyAssistReport?: import("@/src/types/job").ApplyAssistReport | null;
}

function asExplain(
  explain: ExplainResult | Record<string, unknown> | null
): ExplainResult | null {
  if (!explain || typeof explain !== "object") return null;
  if (!("job_id" in explain)) return null;
  return explain as ExplainResult;
}

export default function JobDetailModal({
  job,
  explain: explainProp,
  evalResult,
  diff,
  receipts = [],
  isOpen,
  isLoading,
  isEvaluating,
  onClose,
  onEvaluate,
  onApprove,
  onSkip,
  onMarkApplied,
  isApproving,
  isSkipping,
  isMarkingApplied,
  onApplyAssist,
  isApplyAssisting,
  applyAssistReport,
}: JobDetailModalProps) {
  const { status: setupStatus } = useSetupStatus();
  const apiKeySet = setupStatus?.llm?.api_key_set ?? false;

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  if (!job && !isOpen) return null;

  const explain = evalResult?.explain || asExplain(explainProp);
  const company =
    evalResult?.company ||
    explain?.company ||
    (job ? displayCompany(job) : null) ||
    "—";
  const role =
    evalResult?.role ||
    explain?.role ||
    (job ? displayTitle(job) : "—");
  const evalScore =
    evalResult?.score ??
    explain?.eval_score ??
    (job?.eval_score != null ? job.eval_score : null);
  const discoveryFit = job && job.fit_score > 0 ? job.fit_score : null;
  const templateOnly = Boolean(evalResult?.template_only || job?.eval_template_only);
  // Keyword-only scores must not read as full A–G /5 in the drawer header.
  const score =
    !templateOnly && evalScore != null
      ? Math.min(5, Number(evalScore))
      : null;
  const legitimacy = evalResult?.legitimacy || explain?.legitimacy || job?.legitimacy;
  const blocks = evalResult?.blocks || job?.eval_blocks || {};
  const bullets = explain?.bullets || [];
  const linkOnly = isLinkOnlyJob(job);
  const canMarkApplied =
    Boolean(onMarkApplied) &&
    (job?.pipeline_status === "approved" || job?.pipeline_status === "evaluated");

  return (
    <>
      {/* Backdrop — click anywhere outside the drawer to close (all breakpoints) */}
      {isOpen && (
        <div
          className="fixed inset-0 z-[55] bg-black/20 backdrop-blur-[1px]"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Right-side drawer */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={role}
        className={`fixed right-0 top-0 z-[56] flex h-screen w-full flex-col border-l border-mist bg-white shadow-2xl transition-transform duration-300 sm:w-[520px] ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-mist px-5 py-4">
          <div className="min-w-0">
            <p className="truncate font-bold text-ink">{role}</p>
            <p className="text-sm font-semibold text-stone">{company}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="ml-4 shrink-0 text-stone hover:text-ink">
            <X size={20} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 space-y-6 overflow-y-auto p-5">
          {isLoading && (
            <div className="space-y-3">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-20 w-full" />
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Badge variant="score">
              {score != null
                ? formatScoreOutOf5(score)
                : discoveryFit != null
                  ? `Discovery ${formatScoreOutOf5(discoveryFitOutOf5(discoveryFit), 0)}`
                  : "Not evaluated"}
            </Badge>
            {score != null && discoveryFit != null && (
              <Badge variant="default">
                Discovery {formatScoreOutOf5(discoveryFitOutOf5(discoveryFit), 0)}
              </Badge>
            )}
            {job?.verification === "unverified" && <Badge variant="orange">Unverified</Badge>}
            {templateOnly && (
              <Badge variant="orange">Basic score</Badge>
            )}
            {legitimacy && !templateOnly && <Badge variant="lime">{legitimacy}</Badge>}
            {job?.source && <Badge variant="default">{job.source}</Badge>}
            {job?.location && <Badge variant="default">{job.location}</Badge>}
            {linkOnly && <Badge variant="default">Open posting only</Badge>}
          </div>

          {job?.verification === "unverified" && (
            <div className="rounded-2xl border border-orange/30 bg-orange/10 p-4 text-sm text-ink">
              <strong>Unverified alert.</strong> We have not confirmed a live posting yet.
              Open the original link or wait for the next verify pass — full details publish
              only after confirmation.
            </div>
          )}

          {linkOnly && (
            <div className="rounded-2xl border border-mist bg-sage/30 p-4 text-sm text-ink">
              This is a job-board listing (LinkedIn/Naukri and similar) — there is no form to
              prefill. Open the posting and apply on the board, or find the employer ATS link.
            </div>
          )}

          {!isLoading && score == null && job?.verification !== "unverified" && (
            <div className="rounded-2xl border border-orange/30 bg-orange/10 p-4 text-sm text-ink">
              <strong>Not evaluated yet.</strong> Run Evaluate to fetch the job description and
              build A–G fit blocks
              {discoveryFit != null ? ` (discovery fit is ${formatScoreOutOf5(discoveryFitOutOf5(discoveryFit), 0)})` : ""}.
              Approve still works, but Prefill/prep are stronger after evaluation.
            </div>
          )}

          {job && (job.salary || job.experience || job.location || (job.skills && job.skills.length > 0)) && (
            <div className="space-y-3 rounded-2xl border border-mist bg-sage/20 p-4">
              <h3 className="text-sm font-bold text-stone">Facts</h3>
              <dl className="grid gap-3 sm:grid-cols-2">
                {job.location && (
                  <div>
                    <dt className="text-xs font-bold uppercase tracking-wider text-stone/60">Location</dt>
                    <dd className="mt-0.5 text-base font-medium text-ink">{job.location}</dd>
                  </div>
                )}
                {job.experience && (
                  <div>
                    <dt className="text-xs font-bold uppercase tracking-wider text-stone/60">Experience</dt>
                    <dd className="mt-0.5 text-base font-medium text-ink">{job.experience}</dd>
                  </div>
                )}
                {job.salary && (
                  <div>
                    <dt className="text-xs font-bold uppercase tracking-wider text-stone/60">Salary</dt>
                    <dd className="mt-0.5 text-base font-medium text-ink">{job.salary}</dd>
                  </div>
                )}
                {job.source && (
                  <div>
                    <dt className="text-xs font-bold uppercase tracking-wider text-stone/60">Source</dt>
                    <dd className="mt-0.5 text-base font-medium text-ink">{job.source}</dd>
                  </div>
                )}
              </dl>
              {(job.skills?.length ?? 0) > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wider text-stone/60">Skills</p>
                  <div className="flex flex-wrap gap-1.5">
                    {job.skills!.slice(0, 12).map((s) => (
                      <span
                        key={s}
                        className="rounded-md bg-white px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-ink/70"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!isLoading && templateOnly && (
            <div className="rounded-2xl border border-orange/30 bg-orange/10 p-4 text-sm text-ink">
              <strong>Basic score only</strong> — keyword matching, not full A–G analysis.{" "}
              {apiKeySet ? (
                <>
                  AI is configured but this eval did not use it (connection error or
                  provider issue).{" "}
                  <a href="/connections" className="font-bold underline">
                    Check Connections →
                  </a>{" "}
                  then Re-evaluate.
                </>
              ) : (
                <>
                  <a href="/connections" className="font-bold underline">
                    Add an LLM key in Connections →
                  </a>{" "}
                  then re-evaluate here.
                </>
              )}
            </div>
          )}

          {(evalResult?.summary || explain?.summary || bullets.length > 0 || Object.keys(blocks).length > 0) && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-stone">Fit</h3>
              {(evalResult?.summary || explain?.summary) && (
                <p className="text-sm leading-relaxed text-stone">
                  {evalResult?.summary || explain?.summary}
                </p>
              )}
              {bullets.length > 0 && (
                <ul className="space-y-2 text-base text-ink">
                  {bullets.map((b, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-lime-ink">•</span>
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              )}
              {Object.keys(blocks).length > 0 && (
                <div className="space-y-3">
                  {["A", "B", "C", "D", "E", "F", "G"]
                    .filter((k) => blocks[k])
                    .map((k) => (
                      <div key={k} className="rounded-2xl border border-mist bg-sage/20 p-4">
                        <p className="mb-1 text-sm font-bold text-stone">
                          {BLOCK_LABELS[k] || `Block ${k}`}
                        </p>
                        <p className="whitespace-pre-wrap text-base leading-relaxed text-ink">
                          {String(blocks[k])}
                        </p>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}

          {diff && !templateOnly && (
            <div>
              <h3 className="mb-2 text-sm font-bold text-stone">Résumé prep</h3>
              <p className="text-sm text-ink">
                {diff.summary ||
                  (diff.same_as_baseline
                    ? "Same content as your baseline résumé."
                    : `${diff.change_count} change${diff.change_count === 1 ? "" : "s"}`)}
              </p>
              {(diff.highlights?.length || diff.diff?.length) ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-stone">
                  {(diff.highlights?.length ? diff.highlights : diff.diff)
                    .slice(0, 6)
                    .map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                </ul>
              ) : null}
            </div>
          )}

          {receipts.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-bold text-stone">
                Application receipts
              </h3>
              <ul className="space-y-2 text-sm">
                {receipts.map((r) => (
                  <li
                    key={r.id}
                    className="rounded-xl border border-mist/50 bg-white px-4 py-3 text-ink"
                  >
                    <span className="font-bold capitalize">{r.channel}</span>
                    {r.submitted_at && (
                      <span className="ml-2 text-stone">· {r.submitted_at.slice(0, 16)}</span>
                    )}
                    {r.resume_path && (
                      <p className="mt-1 truncate font-mono text-sm text-stone">{r.resume_path}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {job?.jd_text ? (
            <div>
              <h3 className="mb-2 text-sm font-bold text-stone">Description</h3>
              <div className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-2xl border border-mist bg-sage/30 p-4 text-base text-stone">
                {plainJobDescription(job.jd_text)}
              </div>
            </div>
          ) : (
            !isLoading && (
              <div className="rounded-2xl border border-mist bg-sage/20 p-4 text-sm text-stone">
                No job description stored yet.{" "}
                {job?.url ? (
                  <>
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold text-ink underline"
                    >
                      Open posting
                    </a>
                    {" · "}
                  </>
                ) : null}
                Run Evaluate to fetch the JD when a live page is available.
              </div>
            )
          )}

          {applyAssistReport && (
            <div className="rounded-2xl border border-lime/40 bg-lime/10 p-4 text-sm text-ink">
              <p className="font-bold">Apply assist complete (not submitted)</p>
              <p className="mt-1 text-stone">
                Filled: {applyAssistReport.filled?.join(", ") || "none"}
              </p>
              {applyAssistReport.submit_detected && (
                <p className="mt-1 text-orange">Submit button detected — you must click it manually.</p>
              )}
            </div>
          )}
        </div>

        {/* Sticky action bar */}
        <div className="flex flex-wrap gap-3 border-t border-mist bg-white p-4">
          <Button variant="lime" onClick={onEvaluate} isLoading={isEvaluating}>
            {score != null ? "Re-evaluate" : "Evaluate"}
          </Button>
          {onApprove && job?.pipeline_status !== "approved" && job?.pipeline_status !== "submitted" && (
            <Button variant="primary" onClick={onApprove} isLoading={isApproving} disabled={isApproving || isSkipping}>
              Approve
            </Button>
          )}
          {canMarkApplied && (
            <Button
              variant="secondary"
              onClick={onMarkApplied}
              isLoading={isMarkingApplied}
              disabled={isMarkingApplied}
            >
              Mark applied
            </Button>
          )}
          {onApplyAssist &&
            !linkOnly &&
            (job?.pipeline_status === "approved" || job?.pipeline_status === "evaluated") && (
              <Button variant="secondary" onClick={onApplyAssist} isLoading={isApplyAssisting}>
                Fill form
              </Button>
            )}
          {onSkip && (
            <Button variant="ghost" onClick={onSkip} isLoading={isSkipping} disabled={isApproving || isSkipping}>
              Skip
            </Button>
          )}
          {job?.url && (
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-mist bg-white px-4 py-2.5 text-sm font-semibold text-ink transition-all hover:bg-sage/50 active:scale-95"
            >
              {linkOnly ? "Open posting" : "Open"} <ExternalLink size={14} />
            </a>
          )}
        </div>
      </div>
    </>
  );
}
