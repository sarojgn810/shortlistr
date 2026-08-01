"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ExternalLink, Sparkles, X } from "lucide-react";
import { Button } from "@/src/components/ui/Button";
import { useProfile } from "@/src/hooks/useProfile";
import { ApiError } from "@/src/lib/api/client";

/**
 * Demo path: paste a free Groq key so chat/eval work without waiting on Ollama.
 */
export function GroqKeyModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const { save, isSaving } = useProfile();
  const [key, setKey] = useState("");

  if (!open) return null;

  const saveKey = async () => {
    const trimmed = key.trim();
    if (!trimmed) {
      toast.error("Paste your Groq API key first");
      return;
    }
    try {
      await save({
        llm_provider: "groq",
        llm_model: "llama-3.3-70b-versatile",
        llm_api_key: trimmed,
      });
      toast.success("Groq connected — chat and evaluation will use AI");
      setKey("");
      onSaved?.();
      onClose();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save key");
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-ink/40 p-4">
      <div
        role="dialog"
        aria-labelledby="groq-modal-title"
        className="w-full max-w-md rounded-3xl border border-mist bg-white p-6 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime/20">
              <Sparkles size={18} className="text-ink" />
            </div>
            <div>
              <h2 id="groq-modal-title" className="text-lg font-bold text-ink">
                Connect free AI (Groq)
              </h2>
              <p className="mt-1 text-sm leading-relaxed text-stone">
                Chat and full job scoring need an AI helper. Groq’s free tier is enough for a
                personal search — no Local AI install required.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-stone hover:bg-mist"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <ol className="mt-4 list-decimal space-y-1.5 pl-5 text-sm text-stone">
          <li>
            Open{" "}
            <a
              href="https://console.groq.com/keys"
              target="_blank"
              rel="noreferrer"
              className="font-bold text-ink underline"
            >
              console.groq.com/keys
            </a>{" "}
            and create a key
          </li>
          <li>Paste it below — we store it in your password vault, not in git</li>
        </ol>

        <label className="mt-4 block space-y-1.5">
          <span className="text-sm font-semibold text-ink">Groq API key</span>
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="gsk_…"
            autoComplete="off"
            className="w-full rounded-xl border border-mist bg-sage/20 px-3 py-2.5 text-sm text-ink outline-none focus:border-lime/40"
          />
        </label>

        <div className="mt-5 flex flex-wrap gap-2">
          <Button variant="lime" size="sm" onClick={saveKey} isLoading={isSaving}>
            Save and use Groq
          </Button>
          <Link href="/connections">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Connections <ExternalLink size={13} />
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Not now
          </Button>
        </div>
      </div>
    </div>
  );
}
