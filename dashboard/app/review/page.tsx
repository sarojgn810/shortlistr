"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Sparkles, RefreshCw } from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { ReviewCard } from "@/src/components/review/ReviewCard";
import { Button } from "@/src/components/ui/Button";
import { PendingSubmissions } from "@/src/components/review/PendingSubmissions";
import { api, ApiError, type PendingSubmission, type ReviewQueue } from "@/src/lib/api/client";

/**
 * The review queue: one job at a time, best first, approve or skip.
 *
 * This replaces scrolling a list of hundreds of evaluated jobs that mostly
 * shared a score. Ordering comes from evidence — how many of a posting's stated
 * requirements the CV actually answers — so the top of the queue means
 * something. Jobs evaluated before requirements were recorded are not mixed in;
 * they are counted, with one button to bring them into the ranking.
 */
export default function ReviewPage() {
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);
  const [reevaluating, setReevaluating] = useState(false);
  const [pending, setPending] = useState<PendingSubmission[]>([]);

  const load = useCallback(async () => {
    try {
      setQueue(await api.reviewQueue(50));
      setCursor(0);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not load the queue.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshPending = useCallback(async () => {
    try {
      setPending((await api.applyPending()).pending);
    } catch {
      // A failed poll is not worth interrupting a review session for.
    }
  }, []);

  useEffect(() => {
    void refreshPending();
    const id = setInterval(() => void refreshPending(), 10_000);
    return () => clearInterval(id);
  }, [refreshPending]);

  const decide = async (status: "approved" | "skipped", andSend = false) => {
    const item = queue?.items[cursor];
    if (!item || busy) return;
    setBusy(true);
    try {
      await api.setPipelineStatus(item.job_id, status);

      if (andSend) {
        const res = await api.applySchedule(item.job_id);
        if (!res.scheduled) {
          // Approval still stands — only the sending was refused, and the
          // reason says what to do about it.
          toast.error(res.reason);
        } else {
          await refreshPending();
        }
      }
      // Advance locally rather than refetching: a refetch would renumber the
      // queue underneath the user and lose their place.
      setCursor((c) => c + 1);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "That didn't save.");
    } finally {
      setBusy(false);
    }
  };

  const cancelSend = async (jobId: string) => {
    try {
      await api.applyCancel(jobId);
      await refreshPending();
      toast.success("Cancelled — nothing was sent.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not cancel that.");
    }
  };

  const reevaluate = async () => {
    setReevaluating(true);
    try {
      const { enqueued } = await api.reviewReevaluate();
      toast.success(
        enqueued
          ? `Re-evaluating ${enqueued} job${enqueued === 1 ? "" : "s"} — this takes a few minutes.`
          : "Nothing needs re-evaluating.",
      );
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not start re-evaluation.");
    } finally {
      setReevaluating(false);
    }
  };

  const item = queue?.items[cursor];
  const remaining = queue ? queue.items.length - cursor : 0;

  return (
    <DashboardShell title="Review" breadcrumbs={["Review"]}>
      <div className="mx-auto max-w-3xl space-y-4 py-4">
        {!queue ? (
          <div className="flex items-center justify-center gap-2 py-20 text-stone">
            <Loader2 size={18} className="animate-spin" /> Loading your queue…
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-mist bg-white px-5 py-3">
              <p className="text-base text-stone">
                {remaining > 0 ? (
                  <>
                    <span className="font-bold text-ink">{remaining}</span> to review, best first
                  </>
                ) : (
                  <span className="font-bold text-ink">Queue clear</span>
                )}
              </p>
              <button
                onClick={() => void load()}
                className="flex items-center gap-1.5 text-sm font-semibold text-stone hover:text-ink"
              >
                <RefreshCw size={13} /> Refresh
              </button>
            </div>

            {queue.pending_reevaluation > 0 && (
              <div className="rounded-2xl border border-mist bg-sage/40 p-4">
                <p className="text-base text-stone">
                  <span className="font-bold text-ink">{queue.pending_reevaluation} job
                  {queue.pending_reevaluation === 1 ? "" : "s"}</span> were scored before
                  requirements were recorded, so they can&apos;t be ranked against these yet.
                </p>
                <Button
                  variant="lime"
                  size="sm"
                  className="mt-3"
                  onClick={() => void reevaluate()}
                  isLoading={reevaluating}
                >
                  <Sparkles size={14} /> Re-evaluate them
                </Button>
              </div>
            )}

            <PendingSubmissions pending={pending} onCancel={(id) => void cancelSend(id)} />

            {item ? (
              <ReviewCard
                item={item}
                busy={busy}
                onApprove={() => void decide("approved")}
                onApproveAndSend={() => void decide("approved", true)}
                onSkip={() => void decide("skipped")}
              />
            ) : (
              <div className="rounded-2xl border border-mist bg-white p-10 text-center">
                <p className="text-lg font-bold text-ink">Nothing left to review</p>
                <p className="mt-1 text-base text-stone">
                  {queue.total > 0
                    ? "You've been through every ranked job. Approved ones are waiting on Apply."
                    : "Run a scan to find new roles."}
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </DashboardShell>
  );
}
