"use client";

import Link from "next/link";
import type { SetupStatus } from "@/src/lib/api/client";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { CheckCircle2, Circle } from "lucide-react";

interface SetupChecksCardProps {
  status: SetupStatus | null;
}

export function SetupChecksCard({ status }: SetupChecksCardProps) {
  if (!status) return null;

  const checks = [
    {
      key: "cv",
      label: "Resume (cv.md)",
      ok: status.checks.cv,
      hint: "Paste your real CV in Setup or Resume",
      href: "/onboarding",
    },
    {
      key: "profile",
      label: "Profile (config/profile.yml)",
      ok: status.checks.profile,
      hint: "Fill in Setup → Profile step",
      href: "/onboarding",
    },
    {
      key: "sqlite",
      label: "Local database",
      ok: status.checks.sqlite,
      hint: "Runs automatically on first API start",
      href: "/settings",
    },
    {
      key: "apify",
      label: "Apify job boards (LinkedIn / Naukri / Indeed)",
      ok: Boolean(status.checks.apify),
      hint: "Recommended — free $5 credit. Paste token on Connections",
      href: "/connections",
    },
    {
      key: "llm",
      label: "AI scoring (Local AI or cloud key)",
      ok: status.checks.llm,
      hint: "Optional — basic scoring works without it. Set up on Connections",
      href: "/connections",
    },
    {
      key: "playwright",
      label: "Browser for form filling",
      ok: Boolean(status.checks.playwright),
      hint: "Install from Connections — no terminal needed",
      href: "/connections",
    },
  ];

  // Don't treat optional Apify/LLM/browser as blockers for the primary CTA.
  const requiredMissing = checks.filter(
    (c) => !c.ok && (c.key === "cv" || c.key === "profile" || c.key === "sqlite")
  );
  const missing = requiredMissing.length ? requiredMissing : checks.filter((c) => !c.ok);
  const fixHref = missing.find((c) => c.href)?.href || "/connections";

  return (
    <Card padding="lg" className="space-y-4">
      <div>
        <h3 className="font-bold text-ink">Local setup checklist</h3>
        <p className="mt-1 text-base text-stone">
          Self-hosted files on your machine — not cloud accounts.
        </p>
      </div>
      <ul className="space-y-2">
        {checks.map((c) => (
          <li key={c.key} className="flex items-start gap-2 text-sm">
            {c.ok ? (
              <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-lime-ink" />
            ) : (
              <Circle size={18} className="mt-0.5 shrink-0 text-stone/50" />
            )}
            <span>
              <strong className="text-ink">{c.label}</strong>
              {!c.ok && (
                <span className="text-stone">
                  {" "}
                  — {c.hint}
                  {c.href && (
                    <>
                      {" "}
                      (<Link href={c.href} className="font-bold text-ink underline">
                        fix
                      </Link>
                      )
                    </>
                  )}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {missing.length > 0 && (
        <Link href={fixHref}>
          <Button variant="secondary" size="sm">
            Open Connections
          </Button>
        </Link>
      )}
    </Card>
  );
}
