"use client";

import { useState } from "react";
import { Mail, Copy, Check, Loader2, UserX } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type OutreachDraft } from "@/src/lib/api/client";

/**
 * A drafted note to whoever is actually hiring, for the user to send.
 *
 * Deliberately copy-to-clipboard rather than a Send button. Reaching out is
 * worth doing well and badly worth doing at scale — and on LinkedIn in
 * particular, automated messaging is what gets accounts restricted. Drafting is
 * the part a machine is good at; pressing send is the user's.
 *
 * When no suitable contact is found it says so and why, instead of quietly
 * offering nothing.
 */
export function OutreachPanel({ jobId }: { jobId: string }) {
  const [state, setState] = useState<OutreachDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setState(await api.outreachDraft(jobId));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not draft outreach.");
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    if (!state?.draft) return;
    try {
      await navigator.clipboard.writeText(state.draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy — select the text and copy it manually.");
    }
  };

  if (!state) {
    return (
      <button
        onClick={() => void load()}
        disabled={loading}
        className="flex items-center gap-1.5 text-sm font-semibold text-stone underline hover:text-ink disabled:opacity-50"
      >
        {loading ? <Loader2 size={13} className="animate-spin" /> : <Mail size={13} />}
        Draft outreach
      </button>
    );
  }

  if (!state.ok) {
    return (
      <div className="rounded-xl border border-mist bg-sage/40 p-3">
        <p className="mb-1 flex items-center gap-1.5 text-sm font-bold text-ink">
          <UserX size={14} /> No one worth writing to yet
        </p>
        <p className="text-sm leading-relaxed text-stone">{state.reason}</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-mist bg-white p-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-ink">
            {state.contact?.full_name || "Contact"}
          </p>
          <p className="truncate text-xs text-stone">
            {state.contact?.title}
            {state.email ? ` · ${state.email}` : ""}
          </p>
        </div>
        <button
          onClick={() => void copy()}
          className="flex shrink-0 items-center gap-1 rounded-full bg-mist px-3 py-1.5 text-sm font-semibold text-ink transition-all active:scale-95"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-stone">
        {state.draft}
      </pre>
      <p className="mt-2 text-xs text-stone/70">
        Read it before you send. Nothing is sent for you.
      </p>
    </div>
  );
}
