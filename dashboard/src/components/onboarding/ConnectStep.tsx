"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, CheckCircle2, ExternalLink, SkipForward } from "lucide-react";
import { Button } from "@/src/components/ui/Button";
import { Card } from "@/src/components/ui/Card";
import { api, ApiError, type ConnectionsSetup } from "@/src/lib/api/client";

/** One key at a time, each with what it buys and what it costs.
 *
 * The Connections page shows every connector at once, which is the right shape
 * for coming back to change one thing and the wrong shape for a first run —
 * eighteen cards, no order, nothing saying which two actually matter. This walks
 * the four that do, one screen each, and every one can be skipped.
 *
 * Nothing here blocks finishing setup. The app runs without any of it; these
 * only decide how good the scoring and research are.
 */

type Field = { key: string; label: string; placeholder: string; hint?: string };

interface Connector {
  id: string;
  title: string;
  /** Why someone should care, in terms of what appears in the app. */
  unlocks: string;
  /** The honest cost — free tier limits, or a card requirement. */
  cost: string;
  href: string;
  hrefLabel: string;
  steps: string[];
  fields: Field[];
  recommended: boolean;
  done: (c: ConnectionsSetup | null, llmKeySet: boolean) => boolean;
}

const CONNECTORS: Connector[] = [
  {
    id: "gemini",
    title: "Google Gemini — AI scoring",
    unlocks:
      "Real A–G evaluation of each job against your résumé, cover letters, and chat. Without it, scoring is keyword-only and every card reads “Basic score”.",
    cost: "Free, no card. Around 1,500 requests a day on gemini-2.0-flash — far more than one job search uses.",
    href: "https://aistudio.google.com/apikey",
    hrefLabel: "Get a Gemini key",
    steps: [
      "Sign in with your Google account and press “Create API key”.",
      "Copy the key — it starts with AIza.",
    ],
    fields: [{ key: "llm_api_key", label: "Gemini API key", placeholder: "AIza…" }],
    recommended: true,
    done: (_c, llmKeySet) => llmKeySet,
  },
  {
    id: "cse",
    title: "Google Custom Search — interview research",
    unlocks:
      "The interview-prep reading list, the “how this company interviews” section, and web job search. Without it those sections stay empty.",
    cost: "Free, no card. 100 queries a day.",
    href: "https://programmablesearchengine.google.com/",
    hrefLabel: "Create a search engine",
    steps: [
      "Create an engine, add a few sites (Connections lists the ones Shortlistr searches), then Create.",
      "The Search engine ID is the cx= value shown on the Code page.",
      "Separately, enable the Custom Search API in Google Cloud and create an API key there — the search engine page never shows one.",
    ],
    fields: [
      { key: "google_cse_api_key", label: "API key", placeholder: "AIza…" },
      { key: "google_cse_cx", label: "Search engine ID (CX)", placeholder: "a1b2c3d4e5f6…" },
    ],
    recommended: true,
    done: (c) => Boolean(c?.google_cse?.ready),
  },
  {
    id: "gmail",
    title: "Gmail — job alerts and sending",
    unlocks:
      "Imports job-alert emails into Discover, and lets Prep draft replies. Nothing is ever sent without you pressing send.",
    cost: "Free. Needs a Google app password, not your account password.",
    href: "https://myaccount.google.com/apppasswords",
    hrefLabel: "Create an app password",
    steps: [
      "Two-step verification must be on for your Google account.",
      "Create an app password named “Shortlistr” and copy the 16 characters.",
    ],
    fields: [
      { key: "gmail_sender", label: "Gmail address", placeholder: "you@gmail.com" },
      { key: "gmail_app_password", label: "App password", placeholder: "16 characters" },
    ],
    recommended: false,
    done: (c) => Boolean(c?.gmail?.app_password_set || c?.gmail?.token_present),
  },
  {
    id: "apify",
    title: "Apify — more job boards",
    unlocks:
      "LinkedIn, Naukri and Indeed listings on top of the free boards Shortlistr already reads.",
    cost: "$5 of free credit on signup, no card. Enough for personal searching; it is the only paid source and it stays off until you add a token.",
    href: "https://console.apify.com/settings/integrations",
    hrefLabel: "Get an Apify token",
    steps: ["Sign up, open Settings → Integrations, and copy the Personal API token."],
    fields: [{ key: "apify_token", label: "Apify token", placeholder: "apify_api_…" }],
    recommended: false,
    done: (c) => Boolean(c?.apify?.token_set),
  },
];

interface ConnectStepProps {
  connections: ConnectionsSetup | null;
  llmKeySet: boolean;
  onSaveLlmKey: (key: string) => Promise<void>;
  onSaved: () => Promise<void> | void;
  onFinish: () => void;
}

export function ConnectStep({
  connections,
  llmKeySet,
  onSaveLlmKey,
  onSaved,
  onFinish,
}: ConnectStepProps) {
  const [index, setIndex] = useState(0);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const connector = CONNECTORS[index];
  const isLast = index === CONNECTORS.length - 1;
  const alreadyDone = connector.done(connections, llmKeySet);

  const doneCount = useMemo(
    () => CONNECTORS.filter((c) => c.done(connections, llmKeySet)).length,
    [connections, llmKeySet],
  );

  const advance = () => (isLast ? onFinish() : setIndex((i) => i + 1));

  const save = async () => {
    const filled = connector.fields.filter((f) => (values[f.key] || "").trim());
    if (!filled.length) {
      advance();
      return;
    }
    setSaving(true);
    try {
      if (connector.id === "gemini") {
        await onSaveLlmKey(values.llm_api_key.trim());
      } else {
        const body: Record<string, string | boolean> = {};
        for (const f of filled) body[f.key] = values[f.key].trim();
        if (connector.id === "apify") body.apify_enabled = true;
        await api.saveConnections(body);
      }
      await onSaved();
      toast.success(`${connector.title.split(" — ")[0]} saved`);
      setValues({});
      advance();
    } catch (e) {
      // The API validates keys and explains what was pasted instead — an OAuth
      // client ID, a search engine ID — so show that rather than "failed".
      toast.error(e instanceof ApiError ? e.message : "Could not save that");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card padding="lg" className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-bold text-ink">Connect what you want</h2>
          <span className="text-sm font-bold text-stone">
            {index + 1} of {CONNECTORS.length} · {doneCount} connected
          </span>
        </div>
        <p className="text-base leading-relaxed text-stone">
          Every one of these is optional and each can be added later from
          Connections. The first two are free and make the biggest difference.
        </p>
        <div className="flex gap-1.5 pt-1">
          {CONNECTORS.map((c, i) => (
            <span
              key={c.id}
              className={`h-1.5 flex-1 rounded-full ${
                i < index ? "bg-lime" : i === index ? "bg-ink" : "bg-mist"
              }`}
            />
          ))}
        </div>
      </Card>

      <Card padding="lg" className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-[16rem] flex-1">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-ink">{connector.title}</h3>
              {connector.recommended && (
                <span className="rounded-full bg-lime/20 px-2.5 py-0.5 text-xs font-bold text-lime-ink">
                  Recommended
                </span>
              )}
            </div>
            <p className="mt-2 text-base leading-relaxed text-stone">{connector.unlocks}</p>
            <p className="mt-1.5 text-sm leading-relaxed text-stone">
              <strong className="text-ink">Cost:</strong> {connector.cost}
            </p>
          </div>
          {alreadyDone && (
            <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-lime/20 px-3 py-1 text-sm font-bold text-lime-ink">
              <CheckCircle2 size={14} /> Connected
            </span>
          )}
        </div>

        <a
          href={connector.href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-xl border border-mist bg-white px-4 py-2.5 text-sm font-bold text-ink hover:opacity-80"
        >
          {connector.hrefLabel}
          <ExternalLink size={14} />
        </a>

        <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-relaxed text-stone">
          {connector.steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>

        <div className="max-w-xl space-y-3">
          {connector.fields.map((f) => (
            <div key={f.key} className="space-y-1.5">
              <label className="block text-sm font-semibold text-ink">{f.label}</label>
              <input
                type={f.key.includes("password") ? "password" : "text"}
                value={values[f.key] || ""}
                placeholder={alreadyDone ? "Already saved — leave blank to keep it" : f.placeholder}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                className="w-full rounded-xl border border-mist bg-white px-3.5 py-2.5 text-base text-ink outline-none focus:border-lime/60 placeholder:text-stone/40"
              />
              {f.hint && <p className="text-sm text-stone">{f.hint}</p>}
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button variant="lime" onClick={save} disabled={saving}>
            {saving ? "Saving…" : isLast ? "Save and finish" : "Save and continue"}
            <ArrowRight size={16} />
          </Button>
          <Button variant="ghost" onClick={advance} disabled={saving}>
            <SkipForward size={15} />
            {isLast ? "Skip and finish" : "Skip for now"}
          </Button>
          {index > 0 && (
            <button
              type="button"
              onClick={() => setIndex((i) => i - 1)}
              className="text-sm font-semibold text-stone underline"
            >
              Back
            </button>
          )}
        </div>
      </Card>
    </div>
  );
}
