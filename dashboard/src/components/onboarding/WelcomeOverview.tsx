"use client";

import { Button } from "@/src/components/ui/Button";
import { Card } from "@/src/components/ui/Card";
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  Cloud,
  FileText,
  Radar,
  Send,
  Sparkles,
  UserCircle,
} from "lucide-react";

const JOURNEY = [
  {
    icon: UserCircle,
    title: "Profile & resume",
    body: "Tell Shortlistr who you are and upload your résumé. Target titles drive which jobs show up.",
  },
  {
    icon: Cloud,
    title: "More job boards (recommended)",
    body: "On Connections, paste a free Apify token ($5 credit). That unlocks LinkedIn, Naukri, and Indeed — enough for personal searching.",
  },
  {
    icon: Brain,
    title: "Optional: Local AI",
    body: "See what your computer can run, pick a model, follow the short guide. Or skip — basic scoring still works.",
  },
  {
    icon: Radar,
    title: "Discover & evaluate",
    body: "Scan job boards, open roles you like, and get a fit score against your résumé.",
  },
  {
    icon: Sparkles,
    title: "Approve → Prep",
    body: "Approve strong matches. Prep builds a cover letter, interview guide, and résumé PDF for that job.",
  },
  {
    icon: Send,
    title: "Apply yourself",
    body: "Prefill forms when you want help — you always review and click Submit. Nothing sends without you.",
  },
] as const;

const CHECKLIST = [
  "Save your profile (name, email, job titles)",
  "Upload your real résumé",
  "Pick a resume look (or keep your PDF)",
  "Recommended: add free Apify token on Connections (more job boards)",
  "Optional: set up Local AI on Connections",
  "Scan Discover and evaluate a few roles",
] as const;

interface WelcomeOverviewProps {
  onContinue: () => void;
}

export function WelcomeOverview({ onContinue }: WelcomeOverviewProps) {
  return (
    <div className="space-y-6">
      <Card padding="lg" className="space-y-4 overflow-hidden border-lime/20 bg-gradient-to-br from-sage/40 via-white to-mist/30">
        <p className="text-sm font-bold uppercase tracking-wide text-stone">Welcome to Shortlistr</p>
        <h2 className="max-w-2xl text-3xl font-bold leading-tight text-ink sm:text-4xl">
          Your job search, on this computer
        </h2>
        <p className="max-w-2xl text-lg leading-relaxed text-stone">
          Shortlistr finds roles that match you, helps you judge fit, and prepares applications —
          without blasting your résumé everywhere. Nothing is submitted until you say so.
        </p>
        <Button variant="lime" size="lg" onClick={onContinue}>
          Start setup
          <ArrowRight size={18} />
        </Button>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card padding="lg" className="space-y-4">
          <h3 className="text-lg font-bold text-ink">How you’ll use it</h3>
          <ol className="space-y-4">
            {JOURNEY.map((item, i) => {
              const Icon = item.icon;
              return (
                <li key={item.title} className="flex gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sage/50 text-ink">
                    <Icon size={18} />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-bold text-ink">
                      {i + 1}. {item.title}
                    </span>
                    <span className="mt-0.5 block text-sm leading-relaxed text-stone">{item.body}</span>
                  </span>
                </li>
              );
            })}
          </ol>
        </Card>

        <Card padding="lg" className="space-y-4">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-ink" />
            <h3 className="text-lg font-bold text-ink">First-run checklist</h3>
          </div>
          <p className="text-sm text-stone">We’ll walk you through these next. Takes a few minutes.</p>
          <ul className="space-y-3">
            {CHECKLIST.map((line) => (
              <li key={line} className="flex items-start gap-2 text-sm text-ink">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-lime-ink" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
          <div className="rounded-xl bg-sage/30 px-4 py-3 text-sm leading-relaxed text-stone">
            <strong className="text-ink">Rule of thumb:</strong> upload résumé → set titles →
            add Apify (free $5) → (optional) Local AI → scan → evaluate → approve → prep → you apply.
          </div>
          <Button variant="lime" onClick={onContinue} className="w-full sm:w-auto">
            Continue to profile
            <ArrowRight size={16} />
          </Button>
        </Card>
      </div>
    </div>
  );
}
