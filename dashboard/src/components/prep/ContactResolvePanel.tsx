"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Radar, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/src/components/ui/Button";
import { api, ApiError } from "@/src/lib/api/client";
import type { ContactResolution, ContactResolutionEmail, ReachOutContact } from "@/src/types/job";

function decisionLabel(d?: string): string {
  if (d === "SEND_NOW") return "Looks good";
  if (d === "VERIFY_FIRST") return "Double-check";
  if (d === "SKIP") return "Skip";
  return "Needs review";
}

function decisionClass(d?: string): string {
  if (d === "SEND_NOW") return "bg-lime/25 text-lime-ink";
  if (d === "VERIFY_FIRST") return "bg-sage text-ink";
  if (d === "REVIEW") return "bg-orange/15 text-orange";
  return "bg-mist text-stone";
}

function confidenceLabel(score?: number): string {
  const s = Number(score) || 0;
  if (s >= 0.75) return "High confidence";
  if (s >= 0.55) return "Medium confidence";
  return "Low confidence — guess only";
}

function howFound(method?: string): string {
  const m = (method || "").toLowerCase();
  if (m.includes("ats") || m.includes("jd")) return "From the job posting";
  if (m === "pattern" || m.startsWith("pattern")) return "Matches this company’s email style";
  if (m.startsWith("permute") || m === "permute") return "Guessed from their name";
  if (m.includes("github")) return "From GitHub";
  if (m.includes("verify")) return "Checked online";
  return "Suggested address";
}

function verifyLabel(status?: string): string {
  const s = (status || "").toLowerCase();
  if (s === "valid" || s === "verified") return "Verified deliverable";
  if (s === "accept_all") return "Company accepts most addresses";
  if (s === "invalid") return "Likely invalid";
  if (s === "risky") return "Risky";
  return "Not verified yet";
}

function patternHint(pattern?: string): string | null {
  const p = (pattern || "").trim();
  if (!p) return null;
  const map: Record<string, string> = {
    "{first}.{last}": "first.last@",
    "{f}{last}": "flast@",
    "{first}{last}": "firstlast@",
    "{first}_{last}": "first_last@",
    "{first}": "first@",
    "{last}.{first}": "last.first@",
    "{f}.{last}": "f.last@",
  };
  return map[p] || p.replace(/[{}]/g, "");
}

function mxLabel(mx?: string): string | null {
  const m = (mx || "").toLowerCase();
  if (!m || m === "unknown") return null;
  if (m === "google") return "Google Workspace";
  if (m === "microsoft" || m === "office365") return "Microsoft 365";
  if (m === "proofpoint" || m === "mimecast") return m[0].toUpperCase() + m.slice(1);
  return m[0].toUpperCase() + m.slice(1);
}

function emailLooksValid(email?: string): boolean {
  const e = (email || "").trim();
  if (!e.includes("@")) return false;
  const local = e.split("@")[0] || "";
  if (!local || local.endsWith(".") || local.startsWith(".") || local.includes("..")) return false;
  if (local.endsWith("_") || local.startsWith("_")) return false;
  return true;
}

function displayName(e: ContactResolutionEmail): string {
  const n = (e.person_name || "").trim();
  if (n && /\s/.test(n) && !/-/.test(n.split(/\s/)[0] || "")) return n;
  if (n && !n.includes("-") && !n.includes("_") && n.toLowerCase() !== "contact") return n;
  return "Suggested contact";
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
    const toastId = toast.loading("Looking up hiring contacts…");
    try {
      const res = await api.resolveContact(jobId);
      setData(res);
      const usable = (res.emails || []).filter((e) => emailLooksValid(e.email));
      toast.success(
        usable.length
          ? `Found ${usable.length} address${usable.length === 1 ? "" : "es"} — review before you email`
          : "No clear email yet — try LinkedIn or add a contact manually",
        { id: toastId }
      );
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Lookup failed", { id: toastId });
    } finally {
      setLoading(false);
    }
  };

  const summary = data?.summary;
  const emails = (data?.emails || []).filter((e) => emailLooksValid(e.email));
  const notes = summary?.notes || [];
  const searches = summary?.linkedin_searches || [];
  const domain = summary?.domain?.email_domain;
  const mx = mxLabel(summary?.domain?.mx_provider);
  const style = patternHint(summary?.pattern?.pattern);

  return (
    <div className="mt-5 space-y-3 rounded-xl border border-mist bg-mist/25 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-xl">
          <p className="text-sm font-bold text-ink">Find hiring contact</p>
          <p className="mt-0.5 text-xs leading-relaxed text-stone">
            Looks for a real person and a likely work email from the posting. You always
            send — Shortlistr never emails for you.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={run} isLoading={loading || booting}>
          <Radar size={13} /> {data ? "Search again" : "Find contact"}
        </Button>
      </div>

      {domain ? (
        <p className="text-xs leading-relaxed text-stone">
          Company domain{" "}
          <span className="font-semibold text-ink">{domain}</span>
          {mx ? (
            <>
              {" "}
              · Mail: <span className="font-semibold text-ink">{mx}</span>
            </>
          ) : null}
          {style ? (
            <>
              {" "}
              · Typical format: <span className="font-semibold text-ink">{style}</span>
            </>
          ) : null}
        </p>
      ) : null}

      {emails.length > 0 ? (
        <ul className="space-y-2">
          {emails.slice(0, 6).map((e) => (
            <li
              key={e.email_id || e.email}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-mist bg-white px-3 py-2.5 text-xs"
            >
              <div className="min-w-0">
                <p className="font-semibold text-ink">{displayName(e)}</p>
                <p className="mt-0.5 font-medium text-ink/80">{e.email}</p>
                <p className="mt-1 text-stone">
                  {howFound(e.gen_method)} · {confidenceLabel(e.final_score)} ·{" "}
                  {verifyLabel(e.verify_status)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${decisionClass(
                    e.decision || "REVIEW"
                  )}`}
                >
                  {decisionLabel(e.decision)}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    onAddContact({
                      id: `cr-${e.email_id || Date.now()}`,
                      name: displayName(e) === "Suggested contact" ? "" : displayName(e),
                      email: e.email,
                      linkedin_url: e.linkedin_url || "",
                      note: `${decisionLabel(e.decision)} · ${confidenceLabel(e.final_score)}`,
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
        <p className="text-xs leading-relaxed text-stone">
          No safe email guess for this job yet. Use the LinkedIn searches below, or add
          someone you found yourself.
        </p>
      ) : (
        <p className="text-xs leading-relaxed text-stone">
          Click <span className="font-semibold text-ink">Find contact</span> to search the
          job posting for a recruiter or hiring manager email.
        </p>
      )}

      {searches.length > 0 ? (
        <div>
          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-stone/60">
            Open on LinkedIn
          </p>
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
