"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/src/lib/api/client";
import { useApiStatusStore } from "@/src/hooks/useApiStatus";
import type { Application } from "@/src/types/job";

function normalizeApplication(row: Record<string, unknown>): Application {
  const clean = (v: unknown) => {
    if (v == null) return null;
    const s = String(v).trim();
    if (!s || s.toLowerCase() === "unknown") return null;
    return s;
  };
  return {
    id: Number(row.id ?? 0),
    job_id: (row.job_id as string) ?? null,
    company: clean(row.company),
    role: clean(row.role),
    score: row.score != null ? Number(row.score) : null,
    status: (row.status as string) ?? null,
    applied_date: (row.applied_date as string) ?? null,
    report_path: (row.report_path as string) ?? null,
    notes: (row.notes as string) ?? null,
    created_at: (row.created_at as string) ?? undefined,
  };
}

export function useApplications() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { setOnline } = useApiStatusStore();

  const fetchApplications = useCallback(async () => {
    setIsLoading(true);
    try {
      const rows = await api.listApplications();
      setOnline(true);
      setApplications(rows.map(normalizeApplication));
    } catch (err) {
      console.error("Failed to fetch applications:", err);
      setOnline(false);
      setApplications([]);
    } finally {
      setIsLoading(false);
    }
  }, [setOnline]);

  useEffect(() => {
    fetchApplications();
  }, [fetchApplications]);

  return { applications, isLoading, refetch: fetchApplications };
}
