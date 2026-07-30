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
import { Modal } from "@/src/components/ui/Modal";
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
    if (job) setSelectedId(job);
  }, [searchParams]);

  const openItem = (jobId: string) => {
    setSelectedId(jobId);
    router.replace(`/prep?job=${jobId}`, { scroll: false });
  };

  const closeModal = () => {
    setSelectedId(null);
    router.replace("/prep", { scroll: false });
  };

  const selected = items.find((i) => i.job_id === selectedId) || null;
  const visible = items.filter((i) =>
    matchesPipelineSearch({ company: i.company, title: i.role, url: i.url }, query)
  );

  return (
    <DashboardShell title="Prep" breadcrumbs={["Home", "Prep"]}>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-base leading-relaxed text-stone">
          Cover letters, interview guides, and tailored résumés for roles you have approved.
          Open a company to review everything in one place before you apply.
        </p>
        <Button variant="ghost" size="sm" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </div>

      {error && <p className="mb-4 text-base text-orange">{error}</p>}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
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
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((item) => {
            const initial = (item.company[0] || "?").toUpperCase();
            return (
              <button
                key={item.job_id}
                type="button"
                onClick={() => openItem(item.job_id)}
                className="group text-left"
              >
                <Card
                  padding="lg"
                  className="flex h-full flex-col gap-4 transition-all hover:border-lime/50 hover:shadow-lg"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-ink text-lg font-bold text-lime">
                      {initial}
                    </div>
                    <Badge variant={item.ready ? "lime" : "default"}>
                      {item.ready ? "Ready" : "Needs generate"}
                    </Badge>
                  </div>

                  <div>
                    <p className="text-lg font-bold leading-tight text-ink group-hover:text-lime-ink">
                      {item.company}
                    </p>
                    <p className="mt-1 line-clamp-2 text-base font-medium text-stone">
                      {item.role}
                    </p>
                  </div>

                  {(item.location || item.source) && (
                    <p className="flex flex-wrap items-center gap-2 text-sm text-stone">
                      {item.location && (
                        <span className="inline-flex items-center gap-1">
                          <MapPin size={14} /> {item.location}
                        </span>
                      )}
                      {item.source && <Badge variant="default">{item.source}</Badge>}
                    </p>
                  )}

                  <div className="mt-auto flex flex-wrap gap-2 border-t border-mist/60 pt-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-sm font-semibold ${
                        item.has_cover_draft || item.ready
                          ? "bg-sage/50 text-ink"
                          : "bg-mist/60 text-stone"
                      }`}
                      title="Cover letter"
                    >
                      <FileText size={14} /> Letter
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-sm font-semibold ${
                        item.has_prep_guide ? "bg-sage/50 text-ink" : "bg-mist/60 text-stone"
                      }`}
                      title="Interview guide"
                    >
                      <BookOpen size={14} /> Guide
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-sm font-semibold ${
                        item.has_cv_pdf ? "bg-sage/50 text-ink" : "bg-mist/60 text-stone"
                      }`}
                      title="Tailored CV"
                    >
                      <Sparkles size={14} /> CV
                    </span>
                    <Badge variant="default" className="ml-auto capitalize">
                      {statusLabel(item)}
                    </Badge>
                  </div>
                </Card>
              </button>
            );
          })}
        </div>
      )}

      <Modal
        isOpen={!!selectedId}
        onClose={closeModal}
        size="full"
        title={selected ? `${selected.company} — ${selected.role}` : "Application prep"}
      >
        <div className="space-y-4 p-6 pt-4">
          {selected?.url && (
            <a
              href={selected.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-stone hover:text-ink"
            >
              View job posting <ExternalLink size={14} />
            </a>
          )}
          {selectedId && (
            <PrepDetailPanel jobId={selectedId} showActions onUpdated={() => void refresh()} />
          )}
          {selectedId && (
            <p className="text-sm text-stone">
              Prefer a full page?{" "}
              <Link href={`/prep/${selectedId}`} className="font-bold text-ink underline">
                Open dedicated prep view
              </Link>
            </p>
          )}
        </div>
      </Modal>
    </DashboardShell>
  );
}
