"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Radar, Save } from "lucide-react";
import { Button } from "@/src/components/ui/Button";
import { api, ApiError } from "@/src/lib/api/client";

type Proposal = {
  url: string;
  detected?: boolean;
  name?: string;
  ats_type?: string;
  token?: string;
  careers_url?: string;
  scan_method?: string;
  api?: string;
  notes?: string;
  enabled?: boolean;
  error?: string;
};

/**
 * Detect public ATS boards from careers URLs and merge into portals.yml
 * only after the user confirms — never silent overwrite.
 */
export default function PortalsFingerprintPanel() {
  const [urlsText, setUrlsText] = useState("");
  const [companyHint, setCompanyHint] = useState("");
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [selected, setSelected] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState<"scan" | "apply" | null>(null);

  const scan = async () => {
    const urls = urlsText
      .split(/[\n,]+/)
      .map((u) => u.trim())
      .filter(Boolean);
    if (!urls.length) {
      toast.error("Paste at least one careers URL");
      return;
    }
    setBusy("scan");
    try {
      const res = await api.fingerprintPortals(urls, companyHint.trim() || undefined);
      setProposals((res.proposals || []) as Proposal[]);
      const next: Record<number, boolean> = {};
      ((res.proposals || []) as Proposal[]).forEach((p, i) => {
        next[i] = Boolean(p.detected);
      });
      setSelected(next);
      const hits = ((res.proposals || []) as Proposal[]).filter((p) => p.detected).length;
      toast.success(
        hits
          ? `Found ${hits} ATS board${hits === 1 ? "" : "s"} — review, then save`
          : "No public ATS boards found on those URLs"
      );
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Scan failed");
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    const chosen = proposals.filter((p, i) => p.detected && selected[i]);
    if (!chosen.length) {
      toast.error("Select at least one detected board to save");
      return;
    }
    setBusy("apply");
    try {
      const res = await api.applyPortalFingerprints(chosen);
      toast.success(
        `Watchlist updated — added ${res.added}, updated ${res.updated}`
      );
      setProposals([]);
      setSelected({});
      setUrlsText("");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not update portals");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-stone">
        Paste company careers pages. We detect Greenhouse, Lever, Ashby, Workday,
        SmartRecruiters, and Recruitee boards, then add them to your watchlist only
        when you confirm. Your existing portals.yml is never wiped.
      </p>
      <label className="block space-y-1.5">
        <span className="text-sm font-semibold text-ink">Careers URLs</span>
        <textarea
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
          rows={4}
          placeholder={"https://jobs.lever.co/acme\nhttps://careers.example.com"}
          className="w-full rounded-2xl border border-mist bg-sage/20 p-3 text-sm text-ink outline-none focus:border-lime/40"
        />
      </label>
      <label className="block max-w-md space-y-1.5">
        <span className="text-sm font-semibold text-ink">Company name (optional)</span>
        <input
          value={companyHint}
          onChange={(e) => setCompanyHint(e.target.value)}
          placeholder="Acme Corp"
          className="w-full rounded-xl border border-mist bg-white px-3 py-2.5 text-sm text-ink outline-none focus:border-lime/40"
        />
      </label>
      <Button variant="secondary" size="sm" onClick={scan} isLoading={busy === "scan"}>
        <Radar size={14} /> Detect ATS boards
      </Button>

      {proposals.length > 0 && (
        <ul className="space-y-2">
          {proposals.map((p, i) => (
            <li
              key={`${p.url}-${i}`}
              className="flex items-start gap-3 rounded-xl border border-mist bg-white px-3 py-3 text-sm"
            >
              {p.detected ? (
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 shrink-0"
                  checked={Boolean(selected[i])}
                  onChange={(e) =>
                    setSelected((s) => ({ ...s, [i]: e.target.checked }))
                  }
                />
              ) : (
                <span className="mt-1 h-4 w-4 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                {p.detected ? (
                  <>
                    <p className="font-semibold text-ink">
                      {p.name}{" "}
                      <span className="font-normal text-stone">
                        · {p.ats_type} · {p.token}
                      </span>
                    </p>
                    <p className="mt-0.5 truncate text-xs text-stone">{p.careers_url}</p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-orange">Not detected</p>
                    <p className="mt-0.5 truncate text-xs text-stone">
                      {p.error || p.url}
                    </p>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {proposals.some((p) => p.detected) && (
        <Button variant="lime" size="sm" onClick={apply} isLoading={busy === "apply"}>
          <Save size={14} /> Save selected to watchlist
        </Button>
      )}
    </div>
  );
}
