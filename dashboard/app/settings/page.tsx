"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  RefreshCw, Download, ExternalLink, HelpCircle,
  ChevronDown, ChevronUp, CheckCircle2, XCircle, Brain, Search, Sliders, Database,
} from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { useApiStatus } from "@/src/hooks/useApiStatus";
import { useSetupStatus } from "@/src/hooks/useSetupStatus";
import { api, type AutomationSettings } from "@/src/lib/api/client";
import AutomationPanel from "@/src/components/settings/AutomationPanel";
import { useProfile } from "@/src/hooks/useProfile";

function HelpDetails({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="rounded-xl border border-mist/80 bg-mist/30 px-4 py-3">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-bold text-ink">
        <HelpCircle size={15} className="shrink-0 text-stone" />
        {title}
      </summary>
      <div className="mt-2.5 space-y-2 text-sm leading-relaxed text-stone">{children}</div>
    </details>
  );
}

function Section({
  icon: Icon,
  title,
  subtitle,
  children,
  defaultOpen = true,
}: {
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card padding="lg" className="space-y-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="flex items-start gap-2.5">
          <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ink/5">
            <Icon size={19} className="text-ink" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-ink">{title}</h2>
            {subtitle && <p className="mt-1 text-sm leading-relaxed text-stone">{subtitle}</p>}
          </div>
        </div>
        {open ? (
          <ChevronUp size={18} className="mt-1 shrink-0 text-stone" />
        ) : (
          <ChevronDown size={18} className="mt-1 shrink-0 text-stone" />
        )}
      </button>
      {open && children}
    </Card>
  );
}

export default function SettingsPage() {
  const { online } = useApiStatus();
  const { status, isLoading, refetch } = useSetupStatus();
  const llm = status?.llm;
  const { profile, save: saveProfile, isSaving: profileSaving } = useProfile();
  const [triageSaving, setTriageSaving] = useState(false);

  const [scoring, setScoring] = useState<Pick<
    AutomationSettings,
    "auto_evaluate_min_score" | "auto_approve_score"
  > | null>(null);
  const [scoringSaving, setScoringSaving] = useState(false);

  useEffect(() => {
    api
      .getAutomation()
      .then((s) => {
        setScoring({
          auto_evaluate_min_score: s.auto_evaluate_min_score,
          auto_approve_score: s.auto_approve_score,
        });
      })
      .catch(() => null);
  }, []);

  const clamp = (value: number, min: number, max: number) =>
    Number.isNaN(value) ? min : Math.min(max, Math.max(min, value));

  const saveScoring = async () => {
    if (!scoring) return;
    setScoringSaving(true);
    try {
      const updated = await api.setAutomation(scoring as AutomationSettings);
      setScoring({
        auto_evaluate_min_score: updated.auto_evaluate_min_score,
        auto_approve_score: updated.auto_approve_score,
      });
      toast.success("Saved");
    } catch {
      toast.error("Couldn’t save — is Shortlistr running?");
    } finally {
      setScoringSaving(false);
    }
  };

  const handleExportTracker = async () => {
    try {
      await api.exportTracker();
      toast.success("Your application list was exported");
      refetch();
    } catch {
      toast.error("Export failed — is Shortlistr running?");
    }
  };

  const inputCls =
    "w-28 rounded-xl border border-mist bg-white px-3.5 py-2.5 text-base text-ink outline-none focus:border-lime/60";

  return (
    <DashboardShell title="Settings" breadcrumbs={["Home", "Settings"]}>
      <div className="w-full space-y-6">
        <div className="rounded-2xl border border-mist bg-sage/20 px-5 py-4 text-base leading-relaxed text-stone">
          <p className="text-lg font-bold text-ink">How Shortlistr works for you</p>
          <p className="mt-1.5">
            Change how often jobs are found, how strict scoring is, and export your data.
            Logins, email, and AI keys live on{" "}
            <Link href="/connections" className="font-bold text-ink underline">
              Connections
            </Link>
            .
          </p>
        </div>

        {/* App status */}
        <Section
          icon={online ? CheckCircle2 : XCircle}
          title="App status"
          subtitle="Whether Shortlistr is running on this computer."
        >
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-mist/60 bg-white p-5">
            <div>
              <p className="text-base font-bold text-ink">
                {online ? "Running" : "Not connected"}
              </p>
              <p className="mt-1 text-sm leading-relaxed text-stone">
                {online
                  ? "Discover, Profile, and Connections can talk to Shortlistr."
                  : "Start Shortlistr from your Start app shortcut, then press Refresh."}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`rounded-full px-3 py-1 text-sm font-bold ${
                  online ? "bg-lime/20 text-lime-ink" : "bg-orange/15 text-orange"
                }`}
              >
                {online ? "Online" : "Offline"}
              </span>
              <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isLoading}>
                <RefreshCw size={14} />
                Refresh
              </Button>
            </div>
          </div>
        </Section>

        {/* Automatic job finding */}
        <Section
          icon={Search}
          title="Automatic job finding"
          subtitle="Background scans while Shortlistr is open — no extra apps to start."
        >
          <AutomationPanel />
        </Section>

        {/* Scoring */}
        <Section
          icon={Sliders}
          title="How picky should scoring be?"
          subtitle="Controls which jobs get a deeper look after a scan. You always approve before applying."
        >
          {scoring ? (
            <div className="max-w-2xl space-y-5">
              <HelpDetails title="What do these numbers mean?">
                <p>
                  <strong className="text-ink">Quick filter</strong> uses a simple 0–100 match
                  against your target titles. Jobs below the number are left alone so you aren’t
                  flooded.
                </p>
                <p>
                  <strong className="text-ink">Auto-approve</strong> is optional. Leave it at 0
                  (recommended) so you personally review every role. Raising it lets Shortlistr
                  mark very strong matches as approved for you — still never submits without you.
                </p>
              </HelpDetails>

              <div className="space-y-1.5">
                <label className="block text-sm font-semibold text-ink">
                  Only score jobs that look this relevant (0–100)
                </label>
                <div className="flex flex-wrap items-center gap-3">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={5}
                    value={scoring.auto_evaluate_min_score}
                    onChange={(e) =>
                      setScoring({
                        ...scoring,
                        auto_evaluate_min_score: clamp(Number(e.target.value), 0, 100),
                      })
                    }
                    className={inputCls}
                  />
                  <span className="text-sm text-stone">
                    Higher = fewer jobs scored. Try 40 if you’re unsure.
                  </span>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-sm font-semibold text-ink">
                  Auto-approve score (out of 5)
                </label>
                <div className="flex flex-wrap items-center gap-3">
                  <input
                    type="number"
                    min={0}
                    max={5}
                    step={0.5}
                    value={scoring.auto_approve_score}
                    onChange={(e) =>
                      setScoring({
                        ...scoring,
                        auto_approve_score: clamp(Number(e.target.value), 0, 5),
                      })
                    }
                    className={inputCls}
                  />
                  <span className="text-sm text-stone">
                    {scoring.auto_approve_score === 0
                      ? "Off — you review every job (recommended)"
                      : `Approve jobs scoring ${scoring.auto_approve_score}+ automatically`}
                  </span>
                </div>
              </div>

              <p className="text-sm text-stone">
                Which job titles and locations count as a match is set in{" "}
                <Link href="/profile" className="font-bold text-ink underline">
                  Profile
                </Link>
                .
              </p>

              <Button variant="lime" size="sm" onClick={saveScoring} isLoading={scoringSaving}>
                Save scoring
              </Button>
            </div>
          ) : (
            <p className="text-sm text-orange">
              Start Shortlistr to change scoring. Use your Start app shortcut, then refresh this page.
            </p>
          )}
        </Section>

        {/* AI summary → Connections */}
        <Section
          icon={Brain}
          title="AI helper"
          subtitle="Status only — change provider and key on Connections."
        >
          {llm ? (
            <div className="max-w-2xl space-y-4 rounded-2xl border border-mist/60 bg-white p-5">
              <dl className="space-y-2.5 text-base">
                <div className="flex justify-between gap-4">
                  <dt className="text-stone">Provider</dt>
                  <dd className="font-semibold text-ink">
                    {llm.provider === "none" ? "Not set" : llm.provider}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-stone">Model</dt>
                  <dd className="font-semibold text-ink">{llm.model || "Default"}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-stone">Job scoring</dt>
                  <dd className={`font-semibold ${llm.available ? "text-lime-ink" : "text-stone"}`}>
                    {llm.available ? "Full AI scoring" : "Basic scoring (no AI key)"}
                  </dd>
                </div>
              </dl>
              <Link href="/connections">
                <Button variant="secondary" size="sm">
                  Set up AI on Connections <ExternalLink size={13} />
                </Button>
              </Link>
            </div>
          ) : (
            <p className="text-sm text-stone">Start Shortlistr to see AI status.</p>
          )}

          {profile && (
            <label className="mt-4 flex max-w-2xl cursor-pointer items-start gap-3 rounded-2xl border border-mist bg-sage/20 p-4">
              <input
                type="checkbox"
                className="mt-1 h-5 w-5 shrink-0"
                checked={Boolean(profile.llm_two_stage_triage)}
                disabled={triageSaving || profileSaving}
                onChange={async (e) => {
                  setTriageSaving(true);
                  try {
                    await saveProfile({ llm_two_stage_triage: e.target.checked });
                    toast.success(
                      e.target.checked
                        ? "Two-stage triage on — weak fits skip full A–G"
                        : "Full A–G evaluation for every job"
                    );
                  } catch {
                    toast.error("Couldn’t save triage setting");
                  } finally {
                    setTriageSaving(false);
                  }
                }}
              />
              <span>
                <span className="block text-base font-bold text-ink">
                  Two-stage evaluation (save tokens)
                </span>
                <span className="mt-1 block text-sm leading-relaxed text-stone">
                  A short AI check runs first. Clear mismatches skip the full A–G report.
                  Turn off if you want a full write-up every time.
                </span>
              </span>
            </label>
          )}
        </Section>

        {/* Your data */}
        <Section
          icon={Database}
          title="Your data"
          subtitle="Everything stays on this computer. Export a readable copy anytime."
        >
          <div className="max-w-2xl space-y-4">
            {status?.counts && (
              <p className="text-base text-stone">
                Saved so far:{" "}
                <strong className="text-ink">{status.counts.jobs} jobs</strong>
                {" · "}
                <strong className="text-ink">{status.counts.pipeline} in your pipeline</strong>
              </p>
            )}
            <HelpDetails title="What does Export do?">
              <p>
                Creates simple text files of your pipeline and applications you can open in any
                editor or back up yourself. It does not upload anything.
              </p>
            </HelpDetails>
            <Button variant="secondary" size="sm" onClick={handleExportTracker}>
              <Download size={14} />
              Export my application list
            </Button>
            <HelpDetails title="Instantly / outreach CSV">
              <p>
                From Prep → Reach out, use <strong className="text-ink">Instantly CSV</strong> to
                download contacts you already collected. You import the file into Instantly (or any
                sequencer) yourself — AutoJob never auto-sends email.
              </p>
            </HelpDetails>
          </div>
        </Section>
      </div>
    </DashboardShell>
  );
}
