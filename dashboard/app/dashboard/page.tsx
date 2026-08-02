"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { CardSkeleton } from "@/src/components/ui/Skeleton";
import { useSetupStatus } from "@/src/hooks/useSetupStatus";
import { api } from "@/src/lib/api/client";
import { Inbox, Kanban, Radar, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const router = useRouter();
  const [pipelineCounts, setPipelineCounts] = useState<Record<string, number> | null>(null);
  const [appCounts, setAppCounts] = useState<Record<string, number> | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    // Targeted counts so these headlines match Discover and Pipeline. Deriving
    // them from the first page of /jobs or /applications caps at 100 and —
    // worse — "New jobs to review" used to count every inbox row, including
    // ones already evaluated and approved.
    api.pipelineStats()
      .then((s) => {
        setPipelineCounts(s.pipeline_targeted ?? s.pipeline);
        setAppCounts(s.applications ?? null);
      })
      .catch(() => {
        setPipelineCounts(null);
        setAppCounts(null);
      })
      .finally(() => setStatsLoading(false));
  }, []);

  const pendingCount = pipelineCounts?.pending ?? 0;
  const evaluatedOnly = pipelineCounts?.evaluated ?? 0;
  const approvedCount = pipelineCounts?.approved ?? 0;
  const activeCount =
    (appCounts?.responded ?? 0) + (appCounts?.interview ?? 0) + (appCounts?.offer ?? 0);

  const isLoading = statsLoading;

  const { status } = useSetupStatus();
  const showOnboarding = status && !status.onboarding_complete;
  const onboardingGaps = status?.onboarding_gaps ?? [];

  // First-run guard: a user with no profile yet should set up before landing on
  // a dashboard full of untargeted jobs. Send them to onboarding.
  useEffect(() => {
    if (status?.checks && status.checks.profile === false) {
      router.replace("/onboarding");
    }
  }, [status, router]);

  return (
    <DashboardShell title="Today" breadcrumbs={["Home", "Today"]}>
      <div className="space-y-8">
        {showOnboarding && (
          <Card padding="lg" className="border-lime/40 bg-lime/10">
            <p className="font-bold text-ink">Complete setup</p>
            <p className="mt-1.5 text-base leading-relaxed text-stone">
              {onboardingGaps.length > 0
                ? `Still needed: ${onboardingGaps.join("; ")}.`
                : "Add your CV, pick an ATS LaTeX template, and enable scheduled scans."}
            </p>
            <Link href="/onboarding" className="mt-3 inline-block">
              <Button variant="lime">Continue setup</Button>
            </Link>
          </Card>
        )}

        {/* Action cards — what to work on right now */}
        <div className="grid gap-4 sm:grid-cols-3">
          {isLoading ? (
            <>
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
            </>
          ) : (
            <>
              <ActionCard
                count={pendingCount}
                label="New jobs to review"
                description="Evaluate and decide what to pursue"
                icon={Inbox}
                href="/inbox"
                cta="Go to Discover"
              />
              <ActionCard
                count={evaluatedOnly}
                label="Evaluated, ready to decide"
                description="Approve or skip on Pipeline — Apply only shows approved roles"
                icon={Radar}
                href="/pipeline"
                cta="Open Pipeline"
                highlight={evaluatedOnly > 0}
              />
              <ActionCard
                count={approvedCount > 0 ? approvedCount : activeCount}
                label={approvedCount > 0 ? "Approved, ready to apply" : "Active conversations"}
                description={
                  approvedCount > 0
                    ? "Prefill or open the posting — you always click Submit"
                    : "Interviews, offers, and responses in progress"
                }
                icon={Kanban}
                href={approvedCount > 0 ? "/apply" : "/pipeline"}
                cta={approvedCount > 0 ? "Open apply runner" : "See Pipeline"}
                highlight={approvedCount > 0}
              />
            </>
          )}
        </div>

        <Card variant="glass" padding="lg">
          <h2 className="mb-2 text-xl font-bold text-ink">Judgment-first workflow</h2>
          <p className="max-w-2xl text-sm leading-relaxed text-stone">
            Scan and discover roles, evaluate each offer (A–G + legitimacy), approve before
            applying, then track outcomes. No volume counters — quality over blast radius.
          </p>
        </Card>
      </div>
    </DashboardShell>
  );
}

function ActionCard({
  count,
  label,
  description,
  icon: Icon,
  href,
  cta,
  highlight = false,
}: {
  count: number;
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number }>;
  href: string;
  cta: string;
  highlight?: boolean;
}) {
  return (
    <Card
      variant="elevated"
      padding="lg"
      className={`flex flex-col gap-4 ${highlight ? "border-lime/40 bg-lime/5" : ""}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-stone">{label}</span>
        <div className={`rounded-xl p-2 ${highlight ? "bg-lime text-ink" : "bg-black text-lime"}`}>
          <Icon size={18} />
        </div>
      </div>
      <div className="text-5xl font-normal tracking-tighter text-ink">{count}</div>
      <p className="text-base text-stone">{description}</p>
      <Link href={href}>
        <Button variant={highlight ? "lime" : "secondary"} size="sm">
          {cta} <ArrowRight size={14} />
        </Button>
      </Link>
    </Card>
  );
}
