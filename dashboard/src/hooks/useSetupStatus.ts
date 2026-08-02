"use client";

import { useState, useEffect, useCallback } from "react";
import { api, type SetupStatus } from "@/src/lib/api/client";

export function useSetupStatus() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.setupStatus();
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "API unreachable");
      setStatus(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { status, isLoading, error, refetch };
}
