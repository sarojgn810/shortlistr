"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import DashboardShell from "@/src/components/layout/DashboardShell";
import JobCard from "@/src/components/jobs/JobCard";
import JobRow from "@/src/components/jobs/JobRow";
import JobDetailModal from "@/src/components/jobs/JobDetailModal";
import { Button } from "@/src/components/ui/Button";
import { CardSkeleton } from "@/src/components/ui/Skeleton";
import { useJobs, useJobDetail } from "@/src/hooks/useJobs";
import { useEvaluateJob } from "@/src/hooks/useEvaluateJob";
import { api, ApiError, type AutomationSettings } from "@/src/lib/api/client";
import type { Job } from "@/src/types/job";
import { matchesPipelineSearch, usePipelineSearch } from "@/src/hooks/usePipelineSearch";

import { useSetupStatus } from "@/src/hooks/useSetupStatus";
import { Radar, RefreshCw, Sparkles, Clock, ChevronLeft, ChevronRight } from "lucide-react";

/** Jobs shown per Discover page (client window over the fetched list). */
const DISPLAY_PAGE_SIZE = 20;

/** Min-score filter uses the 0–5 eval scale; map discovery /100 and ignore placeholder template /5. */
function scoreOf(j: Job): number {
  if (j.eval_template_only) {
    if (j.fit_score > 0) return j.fit_score / 20;
    return j.eval_score ?? 0;
  }
  if (j.eval_score != null && j.eval_score > 0) return j.eval_score;
  return j.fit_score ? j.fit_score / 20 : 0;
}

export default function InboxPage() {
  const router = useRouter();
  const { query } = usePipelineSearch();
  const { status: setupStatus } = useSetupStatus();
  const llmAvailable = setupStatus?.llm?.available ?? false;
  const savedJobCount = setupStatus?.counts?.jobs ?? 0;
  const [relevance, setRelevance] = useState<"relevant" | "all">("all");
  const {
    jobs,
    isLoading,
    isLoadingMore,
    hasMore,
    isDiscovering,
    newJobCount,
    clearNewJobCount,
    error,
    scanError,
    clearScanError,
    discover,
    refetch,
    loadMore,
    patchJobStatus,
    removeJob,
  } = useJobs("inbox", relevance);
  const { evaluate, isEvaluating, result, reset } = useEvaluateJob();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bulkEvaluating, setBulkEvaluating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const [applyAssisting, setApplyAssisting] = useState(false);
  const [applyReport, setApplyReport] = useState<import("@/src/types/job").ApplyAssistReport | null>(null);
  const { job: detailJob, explain, diff, receipts, isLoading: detailLoading } = useJobDetail(selectedId);

  const selected = detailJob || jobs.find((j) => j.id === selectedId) || null;
  const staleTemplateJobs = jobs.filter((j) => j.eval_template_only);
  const visibleJobs = jobs.filter((j) => matchesPipelineSearch(j, query));

  // ── Batch apply: filters + selection ─────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [minScore, setMinScore] = useState(0);
  const [sourceFilter, setSourceFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [view, setView] = useState<"rows" | "cards">("rows");
  const [page, setPage] = useState(1);
  const [tipsOpen, setTipsOpen] = useState(false);

  const [scanInfo, setScanInfo] = useState<AutomationSettings | null>(null);
  const loadScanInfo = useCallback(() => {
    api.getAutomation().then(setScanInfo).catch(() => {});
  }, []);
  useEffect(() => {
    loadScanInfo();
  }, [loadScanInfo]);
  // A finished scan (manual or background) moves "Last scan" — re-read it so the
  // banner reflects the click instead of the previous scheduled run.
  const wasDiscovering = useRef(false);
  useEffect(() => {
    if (wasDiscovering.current && !isDiscovering) loadScanInfo();
    wasDiscovering.current = isDiscovering;
  }, [isDiscovering, loadScanInfo]);

  const SOURCE_LABELS: Record<string, string> = {
    RemoteOK: "Remote OK",
    WeWorkRemotely: "We Work Remotely",
    Greenhouse: "Greenhouse",
    Lever: "Lever",
    NoDesk: "NoDesk",
    Jobspresso: "Jobspresso",
    DuckDuckGo: "DuckDuckGo",
  };
  const HIDDEN_SOURCES = new Set(["eval", "test", "sample"]);
  const sources = Array.from(new Set(jobs.map((j) => j.source).filter(Boolean)))
    .filter((s) => !HIDDEN_SOURCES.has(s.toLowerCase()));
  const filtered = visibleJobs.filter(
    (j) =>
      scoreOf(j) >= minScore &&
      (!sourceFilter || j.source === sourceFilter) &&
      (!locationFilter || (j.location || "").toLowerCase().includes(locationFilter.toLowerCase())) &&
      (!companyFilter || (j.company || "").toLowerCase().includes(companyFilter.toLowerCase())) &&
      (!remoteOnly || /remote|wfh|anywhere/i.test(j.location || ""))
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / DISPLAY_PAGE_SIZE) || 1);
  const safePage = Math.min(Math.max(1, page), totalPages);
  const pageStart = (safePage - 1) * DISPLAY_PAGE_SIZE;
  const pageJobs = filtered.slice(pageStart, pageStart + DISPLAY_PAGE_SIZE);
  const rangeFrom = filtered.length === 0 ? 0 : pageStart + 1;
  const rangeTo = Math.min(pageStart + DISPLAY_PAGE_SIZE, filtered.length);

  useEffect(() => {
    setPage(1);
  }, [relevance, minScore, sourceFilter, locationFilter, companyFilter, remoteOnly, query]);

  useEffect(() => {
    if (page !== safePage) setPage(safePage);
  }, [page, safePage]);

  // Prefetch the next server chunk only when the user is on the last display page.
  useEffect(() => {
    if (!hasMore || isLoadingMore || isLoading) return;
    if (safePage < totalPages) return;
    void loadMore();
  }, [safePage, totalPages, hasMore, isLoadingMore, isLoading, loadMore]);

  const toggleSelect = (id: string) =>
    setSelectedIds((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const selectAllFiltered = () => setSelectedIds(new Set(filtered.map((j) => j.id)));
  const clearSelection = () => setSelectedIds(new Set());

  const confirmBatch = async () => {
    setBatchBusy(true);
    try {
      const res = await api.applyBatch(Array.from(selectedIds), true);
      toast.success(`Queued ${res.count} job(s) for apply`);
      setConfirmOpen(false);
      clearSelection();
      router.push("/apply");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Batch apply failed");
    } finally {
      setBatchBusy(false);
    }
  };

  const openJob = (job: Job) => {
    reset();
    setApplyReport(null);
    setSelectedId(job.id);
  };

  const closeModal = () => {
    setSelectedId(null);
    reset();
  };

  const handleEvaluate = async () => {
    if (!selected) return;
    await evaluate(selected);
    refetch();
  };

  const handleApprove = async () => {
    if (!selected || approving) return;
    const jobId = selected.id;
    setApproving(true);
    patchJobStatus(jobId, "approved");
    try {
      await api.setPipelineStatus(jobId, "approved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not approve");
      patchJobStatus(jobId, selected.pipeline_status || "evaluated");
      setApproving(false);
      void refetch(true);
      return;
    }
    // Approval already landed. Prep is best-effort: a prep failure must not make
    // the user think the approval didn't happen.
    try {
      toast.message("Generating prep materials…");
      await api.ensurePrep(jobId);
      toast.success("Approved — prep ready");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "prep generation failed";
      toast.warning(`Approved, but ${msg}. You can retry prep on the job page.`);
    } finally {
      setApproving(false);
      closeModal();
      router.push(`/prep/${jobId}`);
      void refetch(true);
    }
  };

  const handleSkip = async () => {
    if (!selected || skipping) return;
    const jobId = selected.id;
    const prev = selected.pipeline_status;
    setSkipping(true);
    removeJob(jobId);
    closeModal();
    try {
      await api.setPipelineStatus(jobId, "skipped");
      toast.success("Skipped");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not skip");
      void refetch(true);
      if (prev) patchJobStatus(jobId, prev);
    } finally {
      setSkipping(false);
    }
  };

  const handleReEvaluateStale = async () => {
    if (!staleTemplateJobs.length) return;
    setBulkEvaluating(true);
    let ok = 0;
    let templateOnly = 0;
    try {
      for (const job of staleTemplateJobs) {
        try {
          const data = await api.evaluateJob(job.id);
          ok += 1;
          if (data.template_only) templateOnly += 1;
        } catch {
          toast.error(`Failed to re-evaluate ${job.company || job.id}`);
        }
      }
      if (ok) {
        if (templateOnly === ok || !llmAvailable) {
          toast.message(
            `Re-scored ${ok} job(s) with basic scoring. Set up AI on Connections for full A–G analysis.`
          );
        } else if (templateOnly > 0) {
          toast.success(`Re-evaluated ${ok} job(s) (${templateOnly} still basic scoring)`);
        } else {
          toast.success(`Re-evaluated ${ok} job(s)`);
        }
      }
      refetch();
    } finally {
      setBulkEvaluating(false);
    }
  };

  const handleApplyAssist = async () => {
    if (!selected) return;
    setApplyAssisting(true);
    const pending = toast.message("Opening browser to fill the form — up to 2 minutes…");
    try {
      const report = await api.applyAssist(selected.id, false);
      setApplyReport(report);
      toast.dismiss(pending);
      toast.success("Form filled — review in browser and submit yourself");
    } catch (e) {
      toast.dismiss(pending);
      const detail = e instanceof ApiError ? e.message : "Apply assist failed";
      if (/playwright|chromium/i.test(detail)) {
        toast.error(`${detail}. Open Connections → Install Playwright.`);
      } else if (/no application fields/i.test(detail)) {
        toast.error(
          "Could not find form fields on this page. Click Open posting, hit Apply, then try again."
        );
      } else {
        toast.error(detail);
      }
    } finally {
      setApplyAssisting(false);
    }
  };

  return (
    <DashboardShell title="Discover" breadcrumbs={["Home", "Discover"]}>
      <div className="mb-8 flex flex-wrap items-center gap-3">
        <Button
          variant="lime"
          onClick={async () => {
            try {
              const res = await discover(false);
              if (res && "enqueued" in res) {
                toast.success(
                  "Scan running in the background — keep this tab open. Matching jobs land as each source finishes (often a few minutes).",
                  { duration: 8000 },
                );
              } else if (res && typeof res.relevant === "number") {
                const kept = res.kept ?? res.relevant;
                const dropped =
                  (res.dropped_off_target ?? res.off_target ?? 0) +
                  (res.dropped_low_fit ?? 0);
                if (kept === 0 && (res.discovered ?? 0) === 0) {
                  toast.message("No new jobs found. Check your target titles in Profile and company sources in Connections.");
                } else if (kept === 0) {
                  toast.message(
                    `Scanned ${res.discovered} job(s) but none cleared your profile gate. Adjust titles, locations, or fit floor in Profile.`,
                  );
                } else {
                  toast.success(
                    dropped > 0
                      ? `Saved ${kept} matching · skipped ${dropped} off-target/low-fit`
                      : `Saved ${kept} matching`,
                  );
                }
              } else {
                toast.success("Scan complete");
              }
            } catch (e) {
              toast.error(e instanceof ApiError ? e.message : "Scan failed — is the API running?");
            }
          }}
          isLoading={isDiscovering}
          title="Crawl configured boards in the background. ATS feeds arrive first; slower careers pages keep adding matches — leave the tab open and check back."
        >
          <Radar size={18} />
          {isDiscovering ? "Scanning… keep this tab open" : "Scan job boards"}
        </Button>
        <Button variant="ghost" onClick={() => refetch(true)} title="Reload the job list from the database">
          <RefreshCw size={16} />
        </Button>
        {isDiscovering && (
          <span className="flex max-w-xl items-start gap-2 rounded-xl bg-sage/40 px-3.5 py-2 text-sm font-medium text-stone">
            <span className="mt-1.5 h-2 w-2 shrink-0 animate-pulse rounded-full bg-lime" />
            <span>
              Fast ATS boards (Greenhouse, Lever, Ashby, Workday) fill first. More
              matching roles can still land over the next few minutes — leave this
              page open; you don’t need to click Scan again.
            </span>
          </span>
        )}
        {newJobCount > 0 && (
          <button
            type="button"
            onClick={clearNewJobCount}
            className="rounded-xl border border-lime bg-lime/20 px-3.5 py-2 text-sm font-bold text-ink"
            title="Dismiss"
          >
            +{newJobCount} new job{newJobCount === 1 ? "" : "s"} added
          </button>
        )}
        {staleTemplateJobs.length > 0 && (
          <Button
            variant="secondary"
            onClick={handleReEvaluateStale}
            disabled={bulkEvaluating || isEvaluating}
            title={
              llmAvailable
                ? "Re-run full A–G scoring with your AI helper"
                : "Re-score with basic keyword matching (set up AI on Connections for full analysis)"
            }
          >
            <Sparkles size={18} />
            {bulkEvaluating
              ? "Re-evaluating…"
              : `Re-score ${staleTemplateJobs.length} with AI`}
          </Button>
        )}
        {error && <p className="text-sm text-orange">{error}</p>}
        {scanError && (
          <div className="flex max-w-xl items-start gap-2 rounded-xl border border-orange/40 bg-orange/10 px-3.5 py-2 text-sm text-ink">
            <span className="flex-1">{scanError}</span>
            <button
              type="button"
              className="shrink-0 font-bold text-stone hover:text-ink"
              onClick={clearScanError}
              aria-label="Dismiss scan error"
            >
              ×
            </button>
          </div>
        )}
      </div>

      {(staleTemplateJobs.length > 0 || relevance === "relevant") && (
        <div className="mb-4">
          <button
            type="button"
            onClick={() => setTipsOpen((o) => !o)}
            className="text-sm font-semibold text-stone underline-offset-2 hover:text-ink hover:underline"
          >
            {tipsOpen ? "Hide tips" : "Scoring & Relevant tips"}
          </button>
          {tipsOpen && (
            <div className="mt-2 space-y-2 rounded-xl border border-mist bg-white/80 px-4 py-3 text-sm text-stone">
              {staleTemplateJobs.length > 0 && (
                <p>
                  <strong className="text-ink">Basic score</strong> means keyword-only scoring —
                  full A–G needs a working AI connection (Connections). Use{" "}
                  <span className="font-semibold text-ink">Re-score with AI</span> after the
                  provider responds.
                </p>
              )}
              {relevance === "relevant" && (
                <p>
                  <strong className="text-ink">Relevant</strong> hides off-target titles and
                  unverified Gmail alerts. Scanned jobs are never auto-deleted — switch to{" "}
                  <strong className="text-ink">All</strong> to see everything; discard only when
                  you want a job gone.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {scanInfo?.scan_enabled && (
        <p className="mb-4 flex items-center gap-2 text-sm text-stone">
          <Clock size={14} className="shrink-0" />
          <span>
            Background scan every {scanInfo.scan_interval_hours}h
            {scanInfo.last_scan_at && (
              <> · last {new Date(scanInfo.last_scan_at).toLocaleString()}</>
            )}
          </span>
        </p>
      )}

      {jobs.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-mist bg-white p-4 text-base">
          <label className="flex items-center gap-2 text-stone">
            Min score
            <input
              type="number"
              min={0}
              max={5}
              step={0.5}
              value={minScore}
              onChange={(e) => setMinScore(parseFloat(e.target.value) || 0)}
              className="w-16 rounded-lg border border-mist px-2 py-1 text-ink"
            />
          </label>
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="rounded-lg border border-mist px-2 py-1 text-ink"
          >
            <option value="">All sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {SOURCE_LABELS[s] || s}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Location…"
            value={locationFilter}
            onChange={(e) => setLocationFilter(e.target.value)}
            className="w-28 rounded-lg border border-mist px-2 py-1 text-ink placeholder:text-stone/50"
          />
          <input
            type="text"
            placeholder="Company…"
            value={companyFilter}
            onChange={(e) => setCompanyFilter(e.target.value)}
            className="w-28 rounded-lg border border-mist px-2 py-1 text-ink placeholder:text-stone/50"
          />
          <label className="flex items-center gap-2 text-stone">
            <input type="checkbox" checked={remoteOnly} onChange={(e) => setRemoteOnly(e.target.checked)} />
            Remote only
          </label>
          <span className="ml-auto text-stone">
            {filtered.length} match{filtered.length === 1 ? "" : "es"}
            {hasMore ? "+" : ""} · {selectedIds.size} selected
            {filtered.length > 0 && (
              <>
                {" "}
                · {rangeFrom}–{rangeTo}
              </>
            )}
          </span>
          <div className="flex overflow-hidden rounded-lg border border-mist" title="Relevant hides off-target discovery finds">
            <button
              type="button"
              onClick={() => setRelevance("relevant")}
              className={`px-3 py-1.5 text-sm font-bold ${relevance === "relevant" ? "bg-lime text-ink" : "bg-white text-stone"}`}
            >
              Relevant
            </button>
            <button
              type="button"
              onClick={() => setRelevance("all")}
              className={`px-3 py-1.5 text-sm font-bold ${relevance === "all" ? "bg-lime text-ink" : "bg-white text-stone"}`}
            >
              All
            </button>
          </div>
          <div className="flex overflow-hidden rounded-lg border border-mist">
            <button
              type="button"
              onClick={() => setView("rows")}
              className={`px-3 py-1.5 text-sm font-bold ${view === "rows" ? "bg-lime text-ink" : "bg-white text-stone"}`}
            >
              Rows
            </button>
            <button
              type="button"
              onClick={() => setView("cards")}
              className={`px-3 py-1.5 text-sm font-bold ${view === "cards" ? "bg-lime text-ink" : "bg-white text-stone"}`}
            >
              Cards
            </button>
          </div>
          <Button variant="ghost" onClick={selectAllFiltered}>
            Select all
          </Button>
          {selectedIds.size > 0 && (
            <Button variant="ghost" onClick={clearSelection}>
              Clear
            </Button>
          )}
          <Button
            variant="lime"
            disabled={selectedIds.size === 0}
            onClick={() => setConfirmOpen(true)}
          >
            {`Prepare ${selectedIds.size} application${selectedIds.size === 1 ? "" : "s"}`}
          </Button>
        </div>
      )}

      {confirmOpen && (
        <div className="mb-6 rounded-2xl border border-mist bg-sage/30 p-4 text-sm">
          <p className="font-bold text-ink">Prepare {selectedIds.size} application(s)?</p>
          <p className="mt-1 text-stone">
            Un-evaluated jobs get scored first, then you&apos;ll go through them one at a time:
            <strong> Form</strong> jobs open &amp; pre-fill (you click Submit);
            <strong> Email</strong> jobs show the cover letter for you to review &amp; send.
            Nothing is sent or submitted automatically.
          </p>
          <div className="mt-3 flex gap-2">
            <Button variant="lime" isLoading={batchBusy} onClick={confirmBatch}>
              Confirm
            </Button>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : jobs.length === 0 ? (
        <div className="rounded-[32px] border border-mist bg-white p-12 text-center">
          {savedJobCount > 0 && relevance === "relevant" ? (
            <>
              <p className="text-lg font-bold text-ink">
                Nothing on target in view — {savedJobCount.toLocaleString()} stored
              </p>
              <p className="mt-2 text-sm text-stone">
                New scans only keep profile matches. Leftover rows are usually older
                saves or in-flight applications. Widen targeting, or show everything stored.
              </p>
              <div className="mt-4 flex justify-center gap-2">
                <Button variant="lime" onClick={() => setRelevance("all")}>
                  Show all {savedJobCount.toLocaleString()}
                </Button>
                <Button variant="ghost" onClick={() => router.push("/profile")}>
                  Edit targeting
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-lg font-bold text-ink">No new jobs yet</p>
              <p className="mt-2 text-sm text-stone">
                Run discovery to start finding roles that match your profile.
              </p>
            </>
          )}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-[32px] border border-mist bg-white p-12 text-center">
          <p className="text-lg font-bold text-ink">No matches</p>
          <p className="mt-2 text-sm text-stone">Adjust the filters or clear the pipeline search.</p>
        </div>
      ) : view === "rows" ? (
        <div className="space-y-2">
          {pageJobs.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onView={() => openJob(job)}
              selectable
              selected={selectedIds.has(job.id)}
              onToggle={() => toggleSelect(job.id)}
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
          {pageJobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onView={() => openJob(job)}
              selectable
              selected={selectedIds.has(job.id)}
              onToggle={() => toggleSelect(job.id)}
            />
          ))}
        </div>
      )}

      {filtered.length > 0 && (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            disabled={safePage <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            aria-label="Previous page"
          >
            <ChevronLeft size={16} />
            Prev
          </Button>
          <span className="text-sm font-semibold text-stone">
            Page {safePage} of {totalPages}
            {hasMore ? "+" : ""}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={safePage >= totalPages && !hasMore}
            isLoading={isLoadingMore && safePage >= totalPages}
            onClick={() => {
              if (safePage < totalPages) {
                setPage((p) => p + 1);
                return;
              }
              if (!hasMore) return;
              void loadMore().then(() => setPage((p) => p + 1));
            }}
            aria-label="Next page"
          >
            Next
            <ChevronRight size={16} />
          </Button>
          {hasMore && (
            <Button variant="ghost" size="sm" onClick={() => void loadMore()} isLoading={isLoadingMore}>
              Load more from server
            </Button>
          )}
        </div>
      )}

      <JobDetailModal
        job={selected}
        explain={explain}
        diff={diff}
        receipts={receipts}
        evalResult={result}
        isOpen={!!selectedId}
        isLoading={detailLoading && !result}
        isEvaluating={isEvaluating}
        onClose={closeModal}
        onEvaluate={handleEvaluate}
        onApprove={handleApprove}
        onSkip={handleSkip}
        isApproving={approving}
        isSkipping={skipping}
        onApplyAssist={handleApplyAssist}
        isApplyAssisting={applyAssisting}
        applyAssistReport={applyReport}
      />
    </DashboardShell>
  );
}
