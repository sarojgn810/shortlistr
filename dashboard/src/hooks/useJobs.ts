"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/src/lib/api/client";
import { useApiStatusStore } from "@/src/hooks/useApiStatus";
import { isPlausibleCompany } from "@/src/lib/jobs/display";
import type { Job, ApplicationReceipt, ResumeDiff, ExplainResult } from "@/src/types/job";

/** Server page size for /jobs list. Discover UI paginates a smaller window over this. */
export const JOBS_FETCH_PAGE_SIZE = 100;

const PLACEHOLDERS = new Set(["", "unknown", "untitled", "n/a"]);

const BOILERPLATE = /llm not configured|template eval|template evaluation/i;

function cleanLabel(value: unknown): string | null {
  if (value == null) return null;
  const s = String(value).trim();
  if (PLACEHOLDERS.has(s.toLowerCase())) return null;
  if (BOILERPLATE.test(s)) return null;
  return s;
}

function cleanCompany(value: unknown): string | null {
  const c = cleanLabel(value);
  return c && isPlausibleCompany(c) ? c : null;
}

function normalizeJob(row: Record<string, unknown>): Job {
  const blocks = row.eval_blocks as Record<string, string> | undefined;
  const skillsRaw = row.skills;
  const skills = Array.isArray(skillsRaw)
    ? skillsRaw.map((s) => String(s).trim()).filter(Boolean).slice(0, 12)
    : [];
  return {
    id: String(row.id ?? ""),
    url: String(row.url ?? ""),
    source: String(row.source ?? ""),
    company: cleanCompany(row.company),
    title: cleanLabel(row.title),
    location: cleanLabel(row.location),
    jd_text: (row.jd_text as string) || null,
    salary: cleanLabel(row.salary),
    skills,
    experience: cleanLabel(row.experience),
    fit_score: Number(row.fit_score ?? 0),
    fit_reason: String(row.fit_reason ?? ""),
    status: String(row.status ?? "New"),
    discovered_at: (row.discovered_at as string) ?? null,
    notes: (row.notes as string) ?? undefined,
    company_email: (row.company_email as string) ?? null,
    apply_channel: (row.apply_channel as string) ?? undefined,
    pipeline_status: (row.pipeline_status as string) ?? null,
    eval_score: row.eval_score != null ? Number(row.eval_score) : null,
    legitimacy: cleanLabel(row.legitimacy ?? row.eval_legitimacy) ?? undefined,
    eval_blocks: blocks,
    eval_template_only: Boolean(row.eval_template_only),
    verification: cleanLabel(row.verification) ?? undefined,
  };
}

function mergeJobs(prev: Job[], incoming: Job[]): Job[] {
  if (prev.length === 0) return incoming;
  const prevById = new Map(prev.map((j) => [j.id, j]));
  const merged = incoming.map((next) => {
    const old = prevById.get(next.id);
    if (!old) return next;
    const same =
      old.title === next.title &&
      old.company === next.company &&
      old.location === next.location &&
      old.salary === next.salary &&
      old.experience === next.experience &&
      old.source === next.source &&
      old.fit_score === next.fit_score &&
      old.fit_reason === next.fit_reason &&
      old.status === next.status &&
      old.pipeline_status === next.pipeline_status &&
      old.eval_score === next.eval_score &&
      old.legitimacy === next.legitimacy &&
      old.eval_template_only === next.eval_template_only &&
      old.apply_channel === next.apply_channel &&
      old.url === next.url &&
      (old.skills || []).join("|") === (next.skills || []).join("|");
    return same ? old : next;
  });

  if (prev.length > incoming.length) {
    const incomingIds = new Set(incoming.map((j) => j.id));
    const tail = prev.slice(incoming.length).filter((j) => !incomingIds.has(j.id));
    return [...merged, ...tail];
  }
  return merged;
}

export function useJobs(status = "inbox", relevance: "relevant" | "all" = "all") {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [newJobCount, setNewJobCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const { setOnline, setPendingCount, refreshPendingCount } = useApiStatusStore();
  const offsetRef = useRef(0);
  const scanAbortRef = useRef(false);
  const lastJobsFetchRef = useRef(0);
  const scanFailToastedRef = useRef(false);

  const clearScanError = useCallback(() => setScanError(null), []);

  const fetchJobs = useCallback(
    async (background = false) => {
      if (!background) setIsLoading(true);
      setError(null);
      try {
        const rows = await api.listJobs(status, relevance, 0);
        setOnline(true);
        lastJobsFetchRef.current = Date.now();
        const normalized = rows.map(normalizeJob);
        let addedCount = 0;
        setJobs((prev) => {
          if (background) {
            const known = new Set(prev.map((j) => j.id));
            addedCount = normalized.filter((j) => !known.has(j.id)).length;
            return mergeJobs(prev, normalized);
          }
          return normalized;
        });
        if (background && addedCount > 0) {
          setNewJobCount((n) => n + addedCount);
        }
        // Background polls only refresh page 0. Never shrink offset or flip
        // hasMore off after the user has Load-more'd — that stranded page-2 jobs.
        if (!background) {
          setHasMore(rows.length >= JOBS_FETCH_PAGE_SIZE);
          offsetRef.current = normalized.length;
        } else if (offsetRef.current <= JOBS_FETCH_PAGE_SIZE) {
          setHasMore(rows.length >= JOBS_FETCH_PAGE_SIZE);
          if (offsetRef.current < normalized.length) {
            offsetRef.current = normalized.length;
          }
        }
        void refreshPendingCount();
        return normalized.length;
      } catch (err) {
        console.error("Failed to fetch jobs:", err);
        // Never wipe the list on a transient 500 (SQLite locked mid-scan) —
        // that made Discover bounce empty ↔ full.
        const detail =
          err instanceof ApiError
            ? err.message
            : "API unreachable. Start Shortlistr (make start / Start app).";
        const transient =
          err instanceof ApiError &&
          (err.status === 500 || err.status === 503 || /locked|reload|temporar/i.test(detail));
        if (!transient) {
          setOnline(false);
          if (!background) {
            setJobs([]);
            setPendingCount(0);
          }
        }
        setError(
          transient
            ? "Refreshing jobs — scan is writing to the database. List will update shortly."
            : detail
        );
        return 0;
      } finally {
        if (!background) setIsLoading(false);
      }
    },
    [status, relevance, setOnline, setPendingCount, refreshPendingCount]
  );

  /** Instant local pipeline_status update — rollback via refetch on failure. */
  const patchJobStatus = useCallback((jobId: string, pipelineStatus: string | null) => {
    setJobs((prev) =>
      prev.map((j) => (j.id === jobId ? { ...j, pipeline_status: pipelineStatus } : j))
    );
  }, []);

  const removeJob = useCallback((jobId: string) => {
    setJobs((prev) => prev.filter((j) => j.id !== jobId));
  }, []);

  const clearNewJobCount = useCallback(() => setNewJobCount(0), []);

  const loadMore = useCallback(async () => {
    if (isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    try {
      const rows = await api.listJobs(status, relevance, offsetRef.current);
      const normalized = rows.map(normalizeJob);
      let added = 0;
      setJobs((prev) => {
        const seen = new Set(prev.map((j) => j.id));
        const fresh = normalized.filter((j) => !seen.has(j.id));
        added = fresh.length;
        return [...prev, ...fresh];
      });
      // Exhausted when the server returns a short page, or only duplicates.
      setHasMore(rows.length >= JOBS_FETCH_PAGE_SIZE && added > 0);
      offsetRef.current += normalized.length;
    } catch (err) {
      console.error("Failed to load more jobs:", err);
    } finally {
      setIsLoadingMore(false);
    }
  }, [status, relevance, isLoadingMore, hasMore]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Poll discoverStatus cheaply; refetch the job list at most every 12s while
  // scanning (was every 4s — that made every click feel stuck behind a list reload).
  const watchScan = useCallback(async () => {
    const pollInterval = 4000;
    const jobsMinInterval = 12000;
    const maxWaitMs = 15 * 60 * 1000;
    const startedAt = Date.now();
    scanAbortRef.current = false;
    scanFailToastedRef.current = false;
    setScanError(null);
    setIsDiscovering(true);
    let lastStatus: string | null = null;
    try {
      let sawRunning = false;
      while (!scanAbortRef.current && Date.now() - startedAt < maxWaitMs) {
        await new Promise((r) => setTimeout(r, pollInterval));
        let running = false;
        try {
          const st = await api.discoverStatus();
          running = st.running;
          lastStatus = st.last_status;
        } catch {
          running = true;
        }
        if (running) sawRunning = true;
        const due = Date.now() - lastJobsFetchRef.current >= jobsMinInterval;
        if (due || !running) {
          await fetchJobs(true);
        }
        if (!running && (sawRunning || Date.now() - startedAt > 20000)) break;
      }
    } finally {
      setIsDiscovering(false);
      if (lastStatus === "failed" && !scanFailToastedRef.current) {
        scanFailToastedRef.current = true;
        const msg =
          "Last scan failed or timed out. Try Scan again — check Connections if sources keep failing.";
        setScanError(msg);
        toast.error(msg, { duration: 10000 });
      }
    }
  }, [fetchJobs]);

  const discover = async (dryRun = true) => {
    setNewJobCount(0);
    setScanError(null);
    setIsDiscovering(true);
    try {
      const res = await api.discover(dryRun);
      if (res && "enqueued" in res) {
        void watchScan();
      } else {
        await fetchJobs(true);
        setIsDiscovering(false);
      }
      return res;
    } catch (e) {
      setIsDiscovering(false);
      throw e;
    }
  };

  useEffect(() => {
    let cancelled = false;
    api
      .discoverStatus()
      .then((st) => {
        if (cancelled) return;
        if (st.running) {
          void watchScan();
          return;
        }
        if (st.last_status === "failed") {
          setScanError(
            "Last scan failed or timed out. Try Scan again — check Connections if sources keep failing."
          );
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      scanAbortRef.current = true;
    };
  }, [watchScan]);

  return {
    jobs,
    setJobs,
    isLoading,
    isLoadingMore,
    hasMore,
    isDiscovering,
    newJobCount,
    clearNewJobCount,
    error,
    scanError,
    clearScanError,
    refetch: fetchJobs,
    loadMore,
    discover,
    patchJobStatus,
    removeJob,
  };
}

export function useJobDetail(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null);
  const [explain, setExplain] = useState<ExplainResult | null>(null);
  const [diff, setDiff] = useState<ResumeDiff | null>(null);
  const [receipts, setReceipts] = useState<ApplicationReceipt[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setExplain(null);
      setDiff(null);
      setReceipts([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setIsLoading(true);
      try {
        const [jobRow, explainRow, diffRow, receiptRows] = await Promise.all([
          api.getJob(jobId),
          api.getExplain(jobId).catch(() => null),
          api.getDiff(jobId).catch(() => null),
          api.getReceipts(jobId).catch(() => []),
        ]);
        if (!cancelled) {
          setJob(normalizeJob(jobRow));
          setExplain(explainRow);
          setDiff(diffRow);
          setReceipts(receiptRows);
        }
      } catch (e) {
        console.error(e);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  return { job, explain, diff, receipts, isLoading };
}
