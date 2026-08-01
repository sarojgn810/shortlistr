"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Radar, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/src/components/ui/Button";
import { api, ApiError } from "@/src/lib/api/client";
import type { ContactResolution, ReachOutContact } from "@/src/types/job";

function decisionClass(d: string): string {
  if (d === "SEND_NOW") return "bg-lime/25 text-lime-ink";
  if (d === "VERIFY_FIRST") return "bg-sage text-ink";
  if (d === "REVIEW") return "bg-orange/15 text-orange";
  return "bg-mist text-stone";
}

interface Props {
  jobId: string;
  onAddContact: (c: ReachOutContact) => void;
}

export function ContactResolvePanel({ jobId, onAddContact }: Props) {
  const [data, setData] = useState<ContactResolution | null>(null);
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await api.getContactResolution(jobId);
      if (res && res.status && res.status !== "none") setData(res);
    } catch {
      /* no prior resolution */
    } finally {
      setBooting(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async () => {
    setLoading(true);
    const toastId = toast.loading("Resolving contact (domain → person → email)…");
    try {
      const res = await api.resolveContact(jobId);
      setData(res);
      toast.success(
        res.people?.length
          ? `Found ${res.people.length} contact(s) — review scores before emailing`
          : "No named contact yet — try LinkedIn searches or add a Serper key",
        { id: toastId }
      );
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Resolve failed", { id: toastId });
    } finally {
      setLoading(false);
    }
  };

  const summary = data?.summary;
  const emails = data?.emails || [];
  const notes = summary?.notes || [];
  const searches = summary?.linkedin_searches || [];

  return (
    <div className="mt-5 space-y-3 rounded-xl border border-mist bg-mist/25 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-ink">Resolve contact</p>
          <p className="mt-0.5 text-xs leading-relaxed text-stone">
            Domain → person (JD / ATS / GitHub / SERP) → email pattern → score. Never auto-sent.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={run} isLoading={loading || booting}>
          <Radar size={13} /> {data ? "Re-run" : "Resolve"}
        </Button>
      </div>

      {summary?.domain?.email_domain ? (
        <p className="text-xs text-stone">
          Domain{" "}
          <span className="font-semibold text-ink">{summary.domain.email_domain}</span>
          {summary.domain.mx_provider ? (
            <>
              {" "}
              · MX <span className="font-semibold text-ink">{summary.domain.mx_provider}</span>
            </>
          ) : null}
          {summary.pattern?.pattern ? (
            <>
              {" "}
              · Pattern{" "}
              <span className="font-semibold text-ink">{summary.pattern.pattern}</span>
              {summary.pattern.confidence != null
                ? ` (${Math.round(Number(summary.pattern.confidence) * 100)}%)`
                : ""}
            </>
          ) : null}
        </p>
      ) : null}

      {emails.length > 0 ? (
        <ul className="space-y-2">
          {emails.slice(0, 6).map((e) => (
            <li
              key={e.email_id || e.email}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-mist bg-white px-3 py-2 text-xs"
            >
              <div className="min-w-0">
                <p className="font-semibold text-ink">
                  {e.person_name || "Contact"}{" "}
                  <span className="font-normal text-stone">{e.email}</span>
                </p>
                <p className="mt-0.5 text-stone">
                  {e.gen_method} · score {e.final_score?.toFixed?.(2) ?? e.final_score} ·{" "}
                  {e.verify_status}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${decisionClass(
                    e.decision || "REVIEW"
                  )}`}
                >
                  {e.decision || "REVIEW"}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    onAddContact({
                      id: `cr-${e.email_id || Date.now()}`,
                      name: e.person_name || "",
                      email: e.email,
                      linkedin_url: e.linkedin_url || "",
                      note: `Resolved · ${e.decision} · score ${e.final_score}`,
                      source: "user",
                    })
                  }
                >
                  <UserPlus size={12} /> Add
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : data ? (
        <p className="text-xs text-stone">No email candidates yet for this job.</p>
      ) : null}

      {searches.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {searches.map((s) => (
            <a
              key={s.url}
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-mist bg-white px-2 py-1 text-[11px] font-semibold text-ink hover:bg-sage/40"
            >
              <ExternalLink size={11} /> {s.label}
            </a>
          ))}
        </div>
      ) : null}

      {notes.length > 0 ? (
        <ul className="list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-stone">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
