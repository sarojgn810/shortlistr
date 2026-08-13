"use client";

import { useCallback, useState } from "react";
import { Mic, Loader2, Square } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/src/lib/api/client";
import { useVoiceSession } from "@/src/hooks/useVoiceSession";

/**
 * Dictation into a text field.
 *
 * Deliberately not the command path: no wake phrase, no intent routing, no
 * tool ever runs. Whatever is said becomes text. Sharing the command router
 * here would mean saying "skip" into a cover letter skipped a job.
 */
export function DictateButton({
  onText,
  label = "Dictate",
}: {
  onText: (text: string) => void;
  label?: string;
}) {
  const [working, setWorking] = useState(false);

  const handleUtterance = useCallback(
    async (pcm: Int16Array) => {
      setWorking(true);
      try {
        const res = await api.transcribe(pcm);
        if (!res.available) {
          toast.error(res.reason || "Speech recognition isn't set up yet.");
          return;
        }
        if (res.text) onText(res.text);
      } catch (e) {
        toast.error(e instanceof ApiError ? e.message : "Could not transcribe that.");
      } finally {
        setWorking(false);
      }
    },
    [onText],
  );

  const { state, start, stop, error } = useVoiceSession({ onUtterance: handleUtterance });
  const active = state !== "idle";

  return (
    <button
      type="button"
      onClick={() => (active ? stop() : void start())}
      title={error || (active ? "Stop dictating" : label)}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-all active:scale-95 ${
        active ? "bg-ink text-lime" : "bg-mist text-stone hover:text-ink"
      }`}
    >
      {working ? (
        <Loader2 size={14} className="animate-spin" />
      ) : active ? (
        <Square size={14} />
      ) : (
        <Mic size={14} />
      )}
      {active ? "Listening…" : label}
    </button>
  );
}
