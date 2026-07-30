"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/src/lib/api/client";
import type { TrackerBoard } from "@/src/types/job";

const EMPTY_BOARD: TrackerBoard = {
  columns: { review: [], approved: [], submitted: [], active: [] },
  counts: { review: 0, approved: 0, submitted: 0, active: 0 },
};

export function useTrackerBoard(relevance: "relevant" | "all" = "relevant") {
  const [board, setBoard] = useState<TrackerBoard>(EMPTY_BOARD);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBoard = useCallback(async (background = false) => {
    if (!background) setIsLoading(true);
    setError(null);
    try {
      const data = await api.getTrackerBoard(relevance);
      setBoard(data);
    } catch (err) {
      console.error(err);
      setError("Could not load tracker");
      if (!background) setBoard(EMPTY_BOARD);
    } finally {
      if (!background) setIsLoading(false);
    }
  }, [relevance]);

  useEffect(() => {
    fetchBoard();
  }, [fetchBoard]);

  return { board, isLoading, error, refetch: fetchBoard };
}
