"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/src/lib/api/client";
import type { FollowUp } from "@/src/lib/api/client";

export function useFollowUps(includeResolved = false) {
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchFollowUps = useCallback(
    async (background = false) => {
      if (!background) setIsLoading(true);
      setError(null);
      try {
        const data = await api.getFollowUps(includeResolved);
        setFollowUps(data.follow_ups ?? []);
        setOpenCount(data.open ?? 0);
      } catch (err) {
        console.error(err);
        setError("Could not load follow-ups");
        // Keep whatever is on screen on a background refresh; a transient 500
        // from the API reloading should not blank the list.
        if (!background) setFollowUps([]);
      } finally {
        if (!background) setIsLoading(false);
      }
    },
    [includeResolved],
  );

  useEffect(() => {
    fetchFollowUps();
  }, [fetchFollowUps]);

  const resolve = useCallback(async (id: number) => {
    // Optimistic: the row disappears immediately and comes back if the call
    // fails, so marking several done in a row does not feel like waiting.
    setFollowUps((prev) => prev.filter((f) => f.id !== id));
    setOpenCount((n) => Math.max(0, n - 1));
    try {
      await api.resolveFollowUp(id);
    } catch (err) {
      console.error(err);
      await fetchFollowUps(true);
      throw err;
    }
  }, [fetchFollowUps]);

  const reopen = useCallback(async (id: number) => {
    try {
      await api.reopenFollowUp(id);
    } finally {
      await fetchFollowUps(true);
    }
  }, [fetchFollowUps]);

  return { followUps, openCount, isLoading, error, refetch: fetchFollowUps, resolve, reopen };
}
