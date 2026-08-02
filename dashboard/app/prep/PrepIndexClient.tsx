"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BookOpen,
  ExternalLink,
  FileText,
  MapPin,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { PrepDetailPanel } from "@/src/components/prep/PrepDetailPanel";
import { Badge } from "@/src/components/ui/Badge";
import { Button } from "@/src/components/ui/Button";
import { Card } from "@/src/components/ui/Card";
import { CardSkeleton } from "@/src/components/ui/Skeleton";
import { api, ApiError, type PrepSummary } from "@/src/lib/api/client";
import { matchesPipelineSearch, usePipelineSearch } from "@/src/hooks/usePipelineSearch";

function statusLabel(item: PrepSummary): string {
  if (item.application_status && item.application_status !== "evaluated") {
    return item.application_status;
  }
  return item.pipeline_status || "prep";
}

export default function PrepIndexClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { query } = usePipelineSearch();
  const [items, setItems] = useState<PrepSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listPrep();
      setItems(res.items || []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load prep");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const job = searchParams.get("job");
    if (job) {
      setSelectedId(job);
      return;
    }
    // Auto-select first card on desktop so the detail pane is never empty.
  }, [searchParams]);

  useEffect(() => {
    if (selectedId || loading || items.length === 0) return;
    if (searchParams.get("job")) return;
    // Prefer a ready pack; otherwise the first approved role.
    const preferred = items.find((i) => i.ready) || items[0];
    if (preferred && typeof window !== "undefined" && window.innerWidth >= 1024) {
      setSelectedId(preferred.job_id);
    }
  }, [items, loading, selectedId, searchParams]);

  const openItem = (jobId: string) => {
    setSelectedId(jobId);
    router.replace(`/prep?job=${jobId}`, { scroll: false });
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      document
        .getElementById("prep-detail-pane")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const selected = items.find((i) => i.job_id === selectedId) || null;
  const visible = items.filter((i) =>
    matchesPipelineSearch({ company: i.company, title: i.role, url: i.url }, query)
  );
  const candidateName =
    selected?.candidate_name || items.find((i) => i.candidate_name)?.candidate_name || "";

  return (
    <DashboardShell title="Prep" breadcrumbs={["Home", "Prep"]}>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-3xl">
          <p className="text-base leading-relaxed text-stone">
            Cover letters, interview guides, and tailored résumés for roles you approved.
            {candidateName ? (
              <>
                {" "}
                Materials are scoped to <span className="font-semibold text-ink">{candidateName}</span>
                — regenerating rebuilds them from your live profile and CV.
              </>
            ) : null}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </div>

      {error && <p className="mb-4 text-base text-orange">{error}</p>}

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-5">
          <CardSkeleton />
          <div className="lg:col-span-3">
            <CardSkeleton />
          </div>
        </div>
      ) : visible.length === 0 ? (
        <Card padding="lg">
          <p className="text-lg font-bold text-ink">No prep packs yet</p>
          <p className="mt-2 text-base text-stone">
            Approve a role from Discover or Pipeline — Shortlistr builds cover letters and interview
            guides for those companies here.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href="/inbox">
              <Button variant="lime">Go to Discover</Button>
            </Link>
            <Link href="/pipeline">
              <Button variant="secondary">Open Pipeline</Button>
            </Link>
          </div>
        </Card>
      ) : (
        <div className="flex flex-col gap-5 lg:grid lg:grid-cols-5 lg:items-start lg:gap-6">
          <div className="order-2 space-y-3 lg:order-1 lg:col-span-2">
            <p className="text-sm font-bold text-stone">
              {visible.length} role{visible.length === 1 ? "" : "s"}
            </p>
            <div className="max-h-[min(62vh,640px)] space-y-2 overflow-y-auto overscroll-contain rounded-2xl border border-mist bg-white/70 p-2 lg:max-h-[min(78vh,860px)]">
              {visible.map((item) => {
                const selectedRow = item.job_id === selectedId;
                const initial = (item.company[0] || "?").toUpperCase();
                return (
                  <button
                    key={item.job_id}
                    type="button"
                    onClick={() => openItem(item.job_id)}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                      selectedRow
                        ? "border-lime bg-lime/10 ring-1 ring-lime/30"
                        : "border-transparent bg-white hover:border-mist hover:bg-mist/40"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ink text-sm font-bold text-lime">
                        {initial}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <p className="truncate font-bold text-ink">{item.company}</p>
                          <Badge variant={item.ready ? "lime" : "default"} className="shrink-0">
                            {item.fit_label && item.fit_label !== "—"
                              ? item.fit_label
                              : item.ready
                                ? "Ready"
                                : "New"}
                          </Badge>
                        </div>
                        <p className="mt-0.5 line-clamp-2 text-sm text-stone">{item.role}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {item.location && (
                            <span className="inline-flex items-center gap-1 text-xs text-stone">
                              <MapPin size={12} /> {item.location}
                            </span>
                          )}
                          <span
                            className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${
                              item.has_cover_draft || item.ready
                                ? "bg-sage/50 text-ink"
                                : "bg-mist/60 text-stone"
                            }`}
                          >
                            <FileText size={11} /> Letter
                          </span>
                          <span
                            className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${
                              item.has_prep_guide ? "bg-sage/50 text-ink" : "bg-mist/60 text-stone"
                            }`}
                          >
                            <BookOpen size={11} /> Guide
                          </span>
                          <span
                            className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${
                              item.has_cv_pdf ? "bg-sage/50 text-ink" : "bg-mist/60 text-stone"
                            }`}
                          >
                            <Sparkles size={11} /> CV
                          </span>
                          <span className="ml-auto text-[11px] capitalize text-stone">
                            {statusLabel(item)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div id="prep-detail-pane" className="order-1 lg:order-2 lg:col-span-3">
            <div className="sticky top-3 z-10 space-y-3 rounded-2xl border border-mist bg-sage/20 p-3 sm:p-4 lg:top-4">
              {selected ? (
                <>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-lg font-bold text-ink">
                        {selected.company}
                        {selected.fit_label && selected.fit_label !== "—" ? (
                          <span className="ml-2 text-base font-semibold text-lime-ink">
                            Fit {selected.fit_label}
                          </span>
                        ) : null}
                      </p>
                      <p className="text-sm text-stone">{selected.role}</p>
                      {selected.fit_reason ? (
                        <p className="mt-1 line-clamp-2 text-xs text-stone">{selected.fit_reason}</p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {selected.url && (
                        <a
                          href={selected.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-xl border border-mist bg-white px-3 py-2 text-sm font-semibold text-ink hover:bg-sage/40"
                        >
                          Posting <ExternalLink size={14} />
                        </a>
                      )}
                      <Link href={`/prep/${selected.job_id}`}>
                        <Button variant="ghost" size="sm">
                          Full page
                        </Button>
                      </Link>
                    </div>
                  </div>
                  <PrepDetailPanel
                    jobId={selected.job_id}
                    showActions
                    onUpdated={() => void refresh()}
                  />
                </>
              ) : (
                <Card padding="lg" className="border-0 bg-transparent shadow-none">
                  <p className="text-lg font-bold text-ink">Select a role</p>
                  <p className="mt-2 text-base text-stone">
                    Pick a company from the list to review cover letter, résumé prep, and interview
                    guide — without scrolling away from the preview.
                  </p>
                </Card>
              )}
            </div>
          </div>
        </div>
      )}
    </DashboardShell>
  );
}
