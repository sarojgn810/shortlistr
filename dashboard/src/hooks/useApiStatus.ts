"use client";

import { create } from "zustand";
import { api } from "@/src/lib/api/client";

interface ApiStatusState {
  /** null = not checked yet (hide Offline UI); true/false after first probe. */
  online: boolean | null;
  pendingCount: number;
  setOnline: (online: boolean) => void;
  setPendingCount: (count: number) => void;
  refreshPendingCount: () => Promise<void>;
}

export const useApiStatusStore = create<ApiStatusState>((set) => ({
  online: null,
  pendingCount: 0,
  setOnline: (online) => set({ online }),
  setPendingCount: (pendingCount) => set({ pendingCount }),

  /**
   * Ask the API how many targeted jobs await a decision.
   *
   * This used to be derived on the client by filtering the job list for
   * `pipeline_status === "pending"` — but that list is one page of at most 100
   * rows, so the badge really meant "pending jobs among the newest 100", and it
   * silently stopped counting past that. `pipeline_targeted` is a SQL COUNT
   * behind the same relevance + fit gate the inbox uses, so the badge and the
   * list can no longer disagree.
   */
  refreshPendingCount: async () => {
    try {
      const stats = await api.pipelineStats();
      const counts = stats.pipeline_targeted ?? stats.pipeline;
      set({ pendingCount: counts?.pending ?? 0, online: true });
    } catch {
      set({ online: false });
    }
  },
}));

export function useApiStatus() {
  return useApiStatusStore();
}
