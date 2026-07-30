import { useEffect } from "react";
import { create } from "zustand";

interface PipelineSearchState {
  query: string;
  setQuery: (query: string) => void;
}

// Keep the URL's ?q in sync with the query, without triggering a Next navigation
// (replaceState), so refresh/deep-link preserves the filter but typing stays snappy.
function syncQueryToUrl(query: string): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (query) url.searchParams.set("q", query);
  else url.searchParams.delete("q");
  window.history.replaceState(null, "", url.toString());
}

export const usePipelineSearchStore = create<PipelineSearchState>((set) => ({
  query: "",
  setQuery: (query) => {
    set({ query });
    syncQueryToUrl(query);
  },
}));

export function usePipelineSearch() {
  const query = usePipelineSearchStore((s) => s.query);
  const setQuery = usePipelineSearchStore((s) => s.setQuery);
  return { query, setQuery };
}

// Seed the store from ?q on first mount so a refreshed/deep-linked URL restores
// the filter. Call once from a client component rendered on every page (TopBar).
export function useInitPipelineSearchFromUrl(): void {
  const setQuery = usePipelineSearchStore((s) => s.setQuery);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) setQuery(q);
    // run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

export function matchesPipelineSearch(
  job: { company?: string | null; title?: string | null; url?: string | null },
  query: string
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [job.company, job.title, job.url].filter(Boolean).join(" ").toLowerCase();
  return hay.includes(q);
}
