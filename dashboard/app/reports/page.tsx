"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Card } from "@/src/components/ui/Card";
import { Badge } from "@/src/components/ui/Badge";
import { useJobs } from "@/src/hooks/useJobs";
import { matchesPipelineSearch, usePipelineSearch } from "@/src/hooks/usePipelineSearch";
import { api, ApiError } from "@/src/lib/api/client";
import { Button } from "@/src/components/ui/Button";
import { FileText, ExternalLink, Download } from "lucide-react";

export default function ReportsPage() {
  const { jobs, isLoading, isLoadingMore, hasMore, loadMore } = useJobs("evaluated");
  const { query } = usePipelineSearch();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [blocksById, setBlocksById] = useState<Record<string, Record<string, string>>>({});
  const [loadingBlocks, setLoadingBlocks] = useState<string | null>(null);
  const [reportFiles, setReportFiles] = useState<string[]>([]);
  const [learnings, setLearnings] = useState<{ insight: string; key: string }[]>([]);

  useEffect(() => {
    api
      .listReports()
      .then((r) => setReportFiles(r.reports || []))
      .catch(() => setReportFiles([]));
    api
      .getOutcomeInsights()
      .then((r) => setLearnings(r.learnings || []))
      .catch(() => setLearnings([]));
  }, []);

  const withEval = jobs
    .filter((j) => j.eval_score != null || j.eval_blocks)
    .filter((j) => matchesPipelineSearch(j, query));

  /** Slim /jobs omits eval_blocks — load full detail only when expanding A–G. */
  const toggleBlocks = async (jobId: string, currentlyOpen: boolean) => {
    if (currentlyOpen) {
      setExpanded(null);
      return;
    }
    setExpanded(jobId);
    const cached = blocksById[jobId];
    if (cached && Object.keys(cached).length > 0) return;
    setLoadingBlocks(jobId);
    try {
      const detail = await api.getJob(jobId);
      const blocks = (detail.eval_blocks as Record<string, string> | undefined) || {};
      setBlocksById((prev) => ({ ...prev, [jobId]: blocks }));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not load evaluation blocks");
      setExpanded(null);
    } finally {
      setLoadingBlocks(null);
    }
  };
  return (
    <DashboardShell title="Reports" breadcrumbs={["Home", "Reports"]}>
      <p className="mb-6 text-base leading-relaxed text-stone">
        Evaluated roles from your pipeline. Expand <strong className="text-ink">View A–G</strong>{" "}
        for full blocks; markdown reports in{" "}
        <code className="text-ink">reports/</code> are written by the IDE workflow.
      </p>

      {learnings.length > 0 && (
        <Card padding="md" className="mb-6 border-lime/40 bg-lime/5">
          <h2 className="mb-3 text-sm font-bold text-stone">
            What&apos;s working — learned from outcomes
          </h2>
          <ul className="space-y-2 text-base text-ink">
            {learnings.map((l) => (
              <li key={l.key} className="flex items-start gap-2">
                <span className="mt-0.5 text-lime">•</span>
                <span>{l.insight}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {reportFiles.length > 0 && (
        <Card padding="md" className="mb-6">
          <h2 className="mb-3 text-sm font-bold text-stone">
            Report files ({reportFiles.length})
          </h2>
          <ul className="space-y-2">
            {reportFiles.map((name) => (
              <li key={name} className="flex items-center justify-between gap-3">
                <span className="truncate font-mono text-sm text-ink">{name}</span>
                <button
                  type="button"
                  onClick={() =>
                    api
                      .downloadReport(name)
                      .catch((e) =>
                        toast.error(e instanceof ApiError ? e.message : "Could not download report")
                      )
                  }
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-mist bg-white px-3 py-1.5 text-sm font-bold text-ink hover:opacity-80"
                >
                  <Download size={13} /> Download
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {isLoading ? (
        <p className="text-stone">Loading…</p>
      ) : withEval.length === 0 ? (
        <Card padding="lg">
          <p className="font-bold text-ink">No evaluations yet</p>
          <p className="mt-2 text-base text-stone">
            Evaluate jobs from the{" "}
            <Link href="/inbox" className="font-bold text-ink underline">
              inbox
            </Link>{" "}
            to generate scores and blocks.
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {withEval.map((job) => {
            const listBlocks = job.eval_blocks;
            const hasListBlocks =
              !!listBlocks && typeof listBlocks === "object" && Object.keys(listBlocks).length > 0;
            const blocks = hasListBlocks ? listBlocks : blocksById[job.id];
            const summary =
              blocks?.B?.split("\n")[0] ||
              blocks?.A?.split("\n")[0] ||
              job.fit_reason ||
              "";
            const open = expanded === job.id;
            const loadingThis = loadingBlocks === job.id;
            return (
              <Card key={job.id} padding="md" className="space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="rounded-xl bg-black p-3 text-lime">
                      <FileText size={20} />
                    </div>
                    <div>
                      <p className="font-bold text-ink">{job.title || "Role"}</p>
                      <p className="text-sm font-semibold text-stone">
                        {job.company} · {job.eval_score?.toFixed(1)}/5
                      </p>
                      {summary && (
                        <p className="mt-2 line-clamp-2 text-base text-stone">{summary}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {job.legitimacy && <Badge variant="lime">{job.legitimacy}</Badge>}
                    {job.eval_template_only && <Badge variant="orange">Basic score</Badge>}
                    <button
                      type="button"
                      onClick={() => void toggleBlocks(job.id, open)}
                      disabled={loadingThis}
                      className="text-sm font-bold text-ink underline disabled:opacity-50"
                    >
                      {loadingThis ? "Loading…" : open ? "Hide blocks" : "View A–G"}
                    </button>
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-sm text-stone hover:text-ink"
                    >
                      Posting <ExternalLink size={14} />
                    </a>
                  </div>
                </div>
                {open && (
                  <div className="space-y-2 border-t border-mist/50 pt-4">
                    {loadingThis ? (
                      <p className="text-sm text-stone">Loading A–G blocks…</p>
                    ) : blocks && Object.keys(blocks).length > 0 ? (
                      ["A", "B", "C", "D", "E", "F", "G"]
                        .filter((k) => blocks[k])
                        .map((k) => (
                          <div key={k} className="rounded-xl bg-sage/30 p-4 text-base">
                            <p className="mb-1.5 text-sm font-bold text-stone">Block {k}</p>
                            <p className="whitespace-pre-wrap leading-relaxed text-ink">
                              {blocks[k]}
                            </p>
                          </div>
                        ))
                    ) : (
                      <p className="text-sm text-stone">No A–G blocks stored for this evaluation.</p>
                    )}
                  </div>
                )}
              </Card>
            );
          })}        </div>
      )}

      {hasMore && !isLoading && (
        <div className="mt-6 flex justify-center">
          <Button variant="secondary" onClick={loadMore} isLoading={isLoadingMore}>
            Load more evaluations
          </Button>
        </div>
      )}
    </DashboardShell>
  );
}
