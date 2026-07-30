"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/src/components/ui/Button";
import { Skeleton } from "@/src/components/ui/Skeleton";
import { PrepGuide } from "@/src/components/prep/PrepGuide";
import { api, ApiError } from "@/src/lib/api/client";
import type { PrepBundle, ResumeDiff } from "@/src/types/job";

function isResumeDiff(diff: PrepBundle["diff"]): diff is ResumeDiff {
  return Boolean(diff && "diff" in diff && Array.isArray((diff as ResumeDiff).diff));
}

interface PrepDetailPanelProps {
  jobId: string;
  /** Hide the outer action strip when embedded in a page that already has one. */
  showActions?: boolean;
  onUpdated?: () => void;
}

/**
 * Cover letter + CV + interview guide for one company/role.
 * Used by the Prep modal and the /prep/[jobId] deep-link page.
 */
export function PrepDetailPanel({
  jobId,
  showActions = true,
  onUpdated,
}: PrepDetailPanelProps) {
  const [bundle, setBundle] = useState<PrepBundle | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [coverDraft, setCoverDraft] = useState("");
  const [isSavingCover, setIsSavingCover] = useState(false);
  const [applyAssisting, setApplyAssisting] = useState(false);

  const load = async (generate = false) => {
    setIsLoading(true);
    try {
      const data = generate ? await api.generatePrep(jobId) : await api.getPrep(jobId);
      setBundle(data);
      setCoverDraft(data.cover_letter?.body || "");
      if (generate) {
        toast.success("Prep materials generated");
        onUpdated?.();
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not load prep");
      setBundle(null);
    } finally {
      setIsLoading(false);
      setIsGenerating(false);
    }
  };

  useEffect(() => {
    void load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    await load(true);
  };

  const handleApplyAssist = async () => {
    setApplyAssisting(true);
    try {
      toast.message("Opening browser to fill the form…");
      await api.applyAssist(jobId, false);
      toast.success("Form filled — submit manually in the browser");
    } catch (e) {
      const detail = e instanceof ApiError ? e.message : "Apply assist failed";
      if (/playwright|chromium/i.test(detail)) {
        toast.error(`${detail}. Open Connections → Install Playwright.`);
      } else {
        toast.error(detail);
      }
    } finally {
      setApplyAssisting(false);
    }
  };

  const handleSaveCover = async () => {
    setIsSavingCover(true);
    try {
      await api.savePrepCoverLetter(jobId, coverDraft);
      toast.success("Cover letter saved");
      onUpdated?.();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save cover letter");
    } finally {
      setIsSavingCover(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4 p-1">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!bundle) {
    return <p className="text-base text-stone">Prep not found for this role.</p>;
  }

  return (
    <div className="space-y-6">
      {showActions && (
        <div className="flex flex-wrap gap-2">
          <Button variant="lime" onClick={handleGenerate} isLoading={isGenerating}>
            Generate / refresh materials
          </Button>
          <Button variant="secondary" onClick={handleApplyAssist} isLoading={applyAssisting}>
            Prefill form
          </Button>
          {bundle.url && (
            <a
              href={bundle.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center rounded-2xl border border-mist bg-white px-5 py-2.5 text-sm font-semibold text-ink hover:bg-sage/40"
            >
              Open posting
            </a>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-6">
          <div className="rounded-2xl border border-mist bg-white p-5">
            <h3 className="mb-2 text-lg font-bold text-ink">Cover letter</h3>
            <p className="mb-3 text-sm text-stone">
              Mode: {bundle.cover_letter.mode} · Subject: {bundle.cover_letter.subject}
            </p>
            <textarea
              value={coverDraft}
              onChange={(e) => setCoverDraft(e.target.value)}
              rows={12}
              className="w-full rounded-2xl border border-mist bg-sage/20 p-4 text-base leading-relaxed text-ink outline-none focus:border-lime/40"
            />
            <Button
              variant="secondary"
              size="sm"
              className="mt-3"
              onClick={handleSaveCover}
              isLoading={isSavingCover}
            >
              Save cover letter
            </Button>
          </div>

          {bundle.cv_pdf_path && (
            <div className="rounded-2xl border border-lime/30 bg-lime/10 p-5 text-base">
              <p className="font-bold text-ink">Tailored CV PDF</p>
              <p className="mt-1 truncate font-mono text-sm text-stone">{bundle.cv_pdf_path}</p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={() =>
                  api
                    .downloadJobCvPdf(jobId)
                    .catch((e) =>
                      toast.error(e instanceof ApiError ? e.message : "Could not download CV PDF")
                    )
                }
              >
                Download CV PDF
              </Button>
            </div>
          )}
        </section>

        <section className="space-y-6">
          {isResumeDiff(bundle.diff) && (
            <div className="rounded-2xl border border-mist bg-white p-5">
              <h3 className="mb-3 text-lg font-bold text-ink">
                Résumé prep ({bundle.diff.change_count} changes)
              </h3>
              <pre className="max-h-64 overflow-y-auto rounded-2xl bg-black/5 p-4 font-mono text-sm text-ink">
                {bundle.diff.diff.slice(0, 50).join("\n") || bundle.diff.tailored_preview}
              </pre>
            </div>
          )}

          <div className="rounded-2xl border border-mist bg-sage/20 p-5 text-base text-stone">
            <p className="font-bold text-ink">Next steps</p>
            <ol className="mt-3 list-decimal space-y-2 pl-5">
              <li>Review cover letter and edit if needed</li>
              <li>Prefill the application form in the browser</li>
              <li>Attach the CV PDF if the form did not auto-upload</li>
              <li>Click Submit yourself on the employer site</li>
            </ol>
          </div>
        </section>

        <section className="lg:col-span-2">
          {bundle.prep_content ? (
            <div className="rounded-2xl border border-mist bg-white p-5">
              <h3 className="mb-4 text-lg font-bold text-ink">Interview prep guide</h3>
              <PrepGuide markdown={bundle.prep_content} />
            </div>
          ) : (
            <div className="rounded-2xl border border-mist bg-white p-5 text-base">
              <p className="font-bold text-ink">Interview prep guide</p>
              <p className="mt-2 text-stone">
                Click <span className="font-semibold text-ink">Generate / refresh materials</span> to
                build the guide here.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
