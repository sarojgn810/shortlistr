"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/src/lib/api/client";
import { useApiStatusStore } from "@/src/hooks/useApiStatus";
import type { Job, ApplicationReceipt, ResumeDiff, ExplainResult } from "@/src/types/job";

const PAGE_SIZE = 100;

const PLACEHOLDERS = new Set(["", "unknown", "untitled", "n/a"]);

const BOILERPLATE = /llm not configured|template eval|template evaluation/i;

function cleanLabel(value: unknown): string | null {
  if (value == null) return null;
  const s = String(value).trim();
  if (PLACEHOLDERS.has(s.toLowerCase())) return null;
  if (BOILERPLATE.test(s)) return null;
  return s;
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
    company: cleanLabel(row.company),
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
  };
}

// Reuse the previous object when a row's rendered fields are unchanged, so a
// background refresh does not remount every card/row (that flicker is what made
// a polling scan look like a full page reload).
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

  // Keep pages the user already loaded via "Load more" — a first-page refresh
  // must not silently drop them.
  if (prev.length > incoming.length) {
    const incomingIds = new Set(incoming.map((j) => j.id));
    const tail = prev.slice(incoming.length).filter((j) => !incomingIds.has(j.id));
    return [...merged, ...tail];
  }
  return merged;
}

export function useJobs(status = "inbox", relevance: "relevant" | "all" = "relevant") {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [newJobCount, setNewJobCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { setOnline, setPendingCount, refreshPendingCount } = useApiStatusStore();
  const offsetRef = useRef(0);
  const scanAbortRef = useRef(false);

  const fetchJobs = useCallback(
    async (background = false) => {
      if (!background) setIsLoading(true);
      setError(null);
      try {
        const [rows, healthy] = await Promise.all([
          api.listJobs(status, relevance, 0),
          api.health().then(() => true).catch(() => false),
        ]);
        setOnline(healthy);
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
        setHasMore(rows.length >= PAGE_SIZE);
        if (!background || offsetRef.current < normalized.length) {
          offsetRef.current = normalized.length;
        }
        // Counted in SQL, not from `normalized` — this list is one page.
        void refreshPendingCount();
        return normalized.length;
      } catch (err) {
        console.error("Failed to fetch jobs:", err);
        setOnline(false);
        if (!background) {
          setJobs([]);
          setPendingCount(0);
        }
        setError("API unreachable. Start the backend: make api");
        return 0;
      } finally {
        if (!background) setIsLoading(false);
      }
    },
    [status, relevance, setOnline, setPendingCount, refreshPendingCount]
  );

  const clearNewJobCount = useCallback(() => setNewJobCount(0), []);

  const loadMore = useCallback(async () => {
    if (isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    try {
      const rows = await api.listJobs(status, relevance, offsetRef.current);
      const normalized = rows.map(normalizeJob);
      setJobs((prev) => {
        const seen = new Set(prev.map((j) => j.id));
        const fresh = normalized.filter((j) => !seen.has(j.id));
        return [...prev, ...fresh];
      });
      setHasMore(rows.length >= PAGE_SIZE);
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

  // Follow a running scan in the background: poll the cheap status endpoint and
  // only merge the job list, never toggling the page-level loading state.
  const watchScan = useCallback(async () => {
    const pollInterval = 4000;
    const maxWaitMs = 15 * 60 * 1000;
    const startedAt = Date.now();
    scanAbortRef.current = false;
    setIsDiscovering(true);
    try {
      // Grace period: the queue row may not be claimed the instant we return.
      let sawRunning = false;
      while (!scanAbortRef.current && Date.now() - startedAt < maxWaitMs) {
        await new Promise((r) => setTimeout(r, pollInterval));
        let running = false;
        try {
          const st = await api.discoverStatus();
          running = st.running;
        } catch {
          // API busy mid-scan; assume still running and retry.
          running = true;
        }
        if (running) sawRunning = true;
        await fetchJobs(true);
        if (!running && (sawRunning || Date.now() - startedAt > 20000)) break;
      }
    } finally {
      setIsDiscovering(false);
    }
  }, [fetchJobs]);

  const discover = async (dryRun = true) => {
    setNewJobCount(0);
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

  // Attach to a scan that is already running (background scheduler, another tab,
  // or a scan still going after a page navigation).
  useEffect(() => {
    let cancelled = false;
    api
      .discoverStatus()
      .then((st) => {
        if (!cancelled && st.running) void watchScan();
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      scanAbortRef.current = true;
    };
  }, [watchScan]);

  return {
    jobs,
    isLoading,
    isLoadingMore,
    hasMore,
    isDiscovering,
    newJobCount,
    clearNewJobCount,
    error,
    refetch: fetchJobs,
    loadMore,
    discover,
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
