"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Radar, ChevronRight } from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import JobDetailModal from "@/src/components/jobs/JobDetailModal";
import FollowUpsPanel from "@/src/components/tracker/FollowUpsPanel";
import { Button } from "@/src/components/ui/Button";
import { Badge } from "@/src/components/ui/Badge";
import { useJobDetail } from "@/src/hooks/useJobs";
import { useTrackerBoard } from "@/src/hooks/useTrackerBoard";
import { useEvaluateJob } from "@/src/hooks/useEvaluateJob";
import { useApiStatusStore } from "@/src/hooks/useApiStatus";
import { matchesPipelineSearch, usePipelineSearch } from "@/src/hooks/usePipelineSearch";
import { api, ApiError } from "@/src/lib/api/client";
import type { TrackerCard } from "@/src/types/job";

const FUNNEL_STAGES = ["Discover", "Review", "Apply", "Track", "Learn"] as const;

// Tracker-board columns mapped onto the funnel-facing labels the user sees.
const COLUMNS: { label: string; key: "review" | "approved" | "submitted" | "active"; color: string }[] = [
  { label: "Review",   key: "review",    color: "bg-mist/60" },
  { label: "Approved", key: "approved",  color: "bg-lime/10" },
  { label: "Applied",  key: "submitted", color: "bg-orange/10" },
  { label: "Active",   key: "active",    color: "bg-sage/40" },
];

function scoreLabel(card: TrackerCard): { text: string; title: string } {
  if (card.score != null && card.score > 0) {
    return {
      text: card.score.toFixed(1),
      title: `Evaluated ${card.score.toFixed(1)}/5`,
    };
  }
  if (card.fit_score != null && card.fit_score > 0) {
    const outOf5 = Math.min(5, Math.max(0, Math.round(card.fit_score / 20)));
    return {
      text: String(outOf5),
      title: `Discovery fit ${outOf5}/5 — run Evaluate for full A–G`,
    };
  }
  return { text: "—", title: "Not scored yet" };
}

function JobCard({ card, onOpen }: { card: TrackerCard; onOpen: () => void }) {
  const skills = (card.skills || []).slice(0, 3);
  const score = scoreLabel(card);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full cursor-pointer rounded-xl border border-mist bg-white p-4 text-left shadow-sm transition-all hover:border-stone/30 hover:shadow-md active:scale-[0.98]"
    >
      <div className="mb-1 flex items-start justify-between gap-2">
        <p className="text-base font-bold leading-tight text-ink">{card.title || "Role pending"}</p>
        <span
          title={score.title}
          className="shrink-0 rounded-lg bg-ink px-2 py-0.5 text-xs font-bold text-lime"
        >
          {score.text}
        </span>
      </div>
      <p className="text-sm text-stone">{card.company || "Company"}</p>
      {(card.salary || card.experience || card.location) && (
        <p className="mt-1 line-clamp-1 text-sm font-medium text-stone/80">
          {[card.salary, card.experience, card.location].filter(Boolean).join(" · ")}
        </p>
      )}
      {skills.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {skills.map((s) => (
            <span key={s} className="rounded bg-mist/50 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-ink/60">
              {s}
            </span>
          ))}
        </div>
      )}
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {card.source && <Badge variant="default">{card.source}</Badge>}
        {card.pipeline_status && <Badge variant="default">{card.pipeline_status}</Badge>}
        {card.application_status && card.application_status !== "evaluated" && (
          <Badge variant="default">{card.application_status}</Badge>
        )}
      </div>
    </button>
  );
}

export default function PipelinePage() {
  const router = useRouter();
  const { query } = usePipelineSearch();
  const [relevance, setRelevance] = useState<"relevant" | "all">("relevant");
  const { board, isLoading, error, refetch } = useTrackerBoard(relevance);
  const { evaluate, isEvaluating, result, reset } = useEvaluateJob();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const [markingApplied, setMarkingApplied] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [applyAssisting, setApplyAssisting] = useState(false);
  const [applyReport, setApplyReport] = useState<import("@/src/types/job").ApplyAssistReport | null>(null);
  const { job: detailJob, explain, diff, receipts, isLoading: detailLoading } = useJobDetail(selectedId);

  const selected = detailJob || null;

  const refreshPendingCount = useApiStatusStore((s) => s.refreshPendingCount);

  const openJob = (card: TrackerCard) => { reset(); setApplyReport(null); setSelectedId(card.job_id); };
  const closeDrawer = () => { setSelectedId(null); reset(); };

  const handleDiscover = async () => {
    setDiscovering(true);
    try {
      await api.discover(false);
      toast.success(
        "Scan running — matching jobs land on Discover as sources finish. Keep the app open.",
        { duration: 7000 },
      );
      refetch(true);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Discovery failed — is the API running?");
    } finally {
      setDiscovering(false);
    }
  };

  const handleEvaluate = async () => {
    if (!selected) return;
    await evaluate(selected);
    refetch(true);
  };

  const handleApprove = async () => {
    if (!selected || approving) return;
    const jobId = selected.id;
    setApproving(true);
    try {
      await api.setPipelineStatus(jobId, "approved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not approve");
      setApproving(false);
      return;
    }
    // The approval has landed. Prep is a separate, best-effort step: reporting
    // "Could not approve" because prep failed used to leave the drawer open on
    // a job that was in fact approved, so it looked like nothing happened and
    // the role was left with no materials. The API also schedules prep in the
    // background, so a failure here is recoverable either way.
    try {
      toast.message("Generating prep materials…");
      await api.ensurePrep(jobId);
      toast.success("Approved — prep ready");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "prep generation failed";
      toast.warning(`Approved, but ${msg}. You can retry prep on the job page.`);
    } finally {
      setApproving(false);
      refetch(true);
      void refreshPendingCount();
      closeDrawer();
    }
  };

  const handleSkip = async () => {
    if (!selected || skipping) return;
    setSkipping(true);
    try {
      await api.setPipelineStatus(selected.id, "skipped");
      toast.success("Skipped");
      refetch(true);
      void refreshPendingCount();
      closeDrawer();
    } catch {
      toast.error("Could not update status");
    } finally {
      setSkipping(false);
    }
  };

  const handleMarkApplied = async () => {
    if (!selected || markingApplied) return;
    setMarkingApplied(true);
    try {
      await api.markSubmitted(selected.id);
      toast.success("Marked applied — moved to Applied");
      refetch(true);
      void refreshPendingCount();
      closeDrawer();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not mark applied");
    } finally {
      setMarkingApplied(false);
    }
  };

  const handleApplyAssist = async () => {
    if (!selected) return;
    setApplyAssisting(true);
    const t = toast.message("Opening browser to fill the form — up to 2 minutes…");
    try {
      const report = await api.applyAssist(selected.id, false);
      setApplyReport(report);
      toast.dismiss(t);
      toast.success("Form filled — review in browser and submit yourself");
    } catch (e) {
      toast.dismiss(t);
      const detail = e instanceof ApiError ? e.message : "Apply assist failed";
      if (/playwright|chromium/i.test(detail)) toast.error(`${detail}. Open Connections → Install Playwright.`);
      else if (/no application fields/i.test(detail)) toast.error("Could not find form fields. Open the posting, hit Apply, then retry.");
      else toast.error(detail);
    } finally {
      setApplyAssisting(false);
    }
  };

  const cardsForColumn = (key: typeof COLUMNS[number]["key"]) =>
    (board.columns[key] || []).filter((c) => matchesPipelineSearch(c, query));

  // Highlight the funnel stage that maps to the leftmost non-empty column.
  const activeColIndex = COLUMNS.findIndex((col) => cardsForColumn(col.key).length > 0);
  const activeFunnelIndex = activeColIndex >= 0 ? activeColIndex + 1 : 0;

  return (
    <DashboardShell title="Pipeline" breadcrumbs={["Home", "Pipeline"]}>
      {/* Above the funnel on purpose: a stalled questionnaire is the most
          time-sensitive thing on this page, and it is invisible in the board
          below because those applications have no job row. */}
      <FollowUpsPanel />

      {/* Funnel strip */}
      <div className="mb-6 flex items-center gap-1">
        {FUNNEL_STAGES.map((stage, i) => (
          <span key={stage} className="flex items-center gap-1">
            <span
              className={`rounded-full px-3.5 py-1.5 text-sm font-bold ${
                i === activeFunnelIndex
                  ? "bg-ink text-lime"
                  : "bg-mist text-stone"
              }`}
            >
              {stage}
            </span>
            {i < FUNNEL_STAGES.length - 1 && (
              <ChevronRight size={12} className="text-stone/40" />
            )}
          </span>
        ))}
      </div>

      {/* Action bar */}
      <div className="mb-5 flex items-center gap-3">
        <Button variant="lime" onClick={handleDiscover} isLoading={discovering}>
          <Radar size={16} /> {discovering ? "Scanning sources…" : "Discover"}
        </Button>
        <Button variant="ghost" onClick={() => refetch(true)}>Refresh</Button>
        <div className="flex overflow-hidden rounded-lg border border-mist">
          {(["relevant", "all"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setRelevance(mode)}
              className={`px-3.5 py-2 text-sm font-bold capitalize transition-colors ${
                relevance === mode ? "bg-ink text-lime" : "bg-white text-stone hover:text-ink"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        {error && <p className="text-sm text-orange">{error}</p>}
        <button
          type="button"
          onClick={() => router.push("/apply")}
          className="ml-auto text-sm font-bold text-stone hover:text-ink"
        >
          Apply runner →
        </button>
      </div>

      {/* Kanban board */}
      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          {COLUMNS.map((col) => (
            <div key={col.label} className={`min-h-64 animate-pulse rounded-2xl ${col.color}`} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((col) => {
            const colCards = cardsForColumn(col.key);
            return (
              <div key={col.label} className={`flex flex-col rounded-2xl ${col.color} min-h-64 p-3`}>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-bold text-stone">
                    {col.label}
                  </span>
                  <span className="rounded-full bg-white/70 px-2.5 py-0.5 text-xs font-bold text-stone">
                    {colCards.length}
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  {colCards.map((card) => (
                    <JobCard key={card.job_id} card={card} onOpen={() => openJob(card)} />
                  ))}
                  {colCards.length === 0 && (
                    <p className="py-8 text-center text-sm text-stone/40">Empty</p>
                  )}
                </div>
              </div>
            );
          })}
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
        onClose={closeDrawer}
        onEvaluate={handleEvaluate}
        onApprove={handleApprove}
        onSkip={handleSkip}
        onMarkApplied={handleMarkApplied}
        isApproving={approving}
        isSkipping={skipping}
        isMarkingApplied={markingApplied}
        onApplyAssist={handleApplyAssist}
        isApplyAssisting={applyAssisting}
        applyAssistReport={applyReport}
      />
    </DashboardShell>
  );
}
