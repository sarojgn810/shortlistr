"use client";

import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/src/lib/api/client";
import type { EvalResult, ExplainResult, Job } from "@/src/types/job";

function parseExplain(data: Record<string, unknown> | undefined): ExplainResult | undefined {
  if (!data || !data.job_id) return undefined;
  return {
    job_id: String(data.job_id),
    company: (data.company as string) ?? null,
    role: (data.role as string) ?? null,
    score: Number(data.score ?? 0),
    eval_score: data.eval_score != null ? Number(data.eval_score) : null,
    fit_score: data.fit_score != null ? Number(data.fit_score) : undefined,
    legitimacy: data.legitimacy as string | undefined,
    bullets: Array.isArray(data.bullets) ? (data.bullets as string[]) : [],
    summary: String(data.summary ?? ""),
  };
}

export function useEvaluateJob() {
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [result, setResult] = useState<EvalResult | null>(null);

  const evaluate = async (job: Job) => {
    setIsEvaluating(true);
    try {
      const data = await api.evaluateJob(job.id);
      const blocks = (data.blocks as Record<string, string>) || {};
      const explain = parseExplain(data.explain as Record<string, unknown> | undefined);
      const evalResult: EvalResult = {
        score: Number(data.score ?? 0),
        legitimacy: (data.legitimacy as string) || explain?.legitimacy,
        company: (data.company as string) || explain?.company || job.company || undefined,
        role: (data.role as string) || explain?.role || job.title || undefined,
        summary:
          (data.summary as string) ||
          explain?.summary ||
          job.fit_reason ||
          blocks.B?.split("\n")[0],
        blocks,
        explain,
        job: data.job ? (data.job as Job) : undefined,
        template_only: Boolean(data.template_only),
      };
      setResult(evalResult);
      if (evalResult.template_only) {
        toast.message("Basic scoring — résumé/JD overlap only. Set up AI on Connections for full A–G analysis.");
      } else {
        toast.success(`Evaluated: ${evalResult.score.toFixed(1)}/5`);
      }
      return evalResult;
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : "Evaluation failed";
      toast.error(detail);
      throw err;
    } finally {
      setIsEvaluating(false);
    }
  };

  const reset = () => setResult(null);

  return { evaluate, isEvaluating, result, reset };
}
