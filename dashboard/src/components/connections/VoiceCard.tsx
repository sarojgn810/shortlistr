"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AudioLines, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { api, ApiError, type VoiceStatus } from "@/src/lib/api/client";

/**
 * Voice setup — the one-click path to local speech recognition.
 *
 * Setup belongs here rather than in a terminal: once `make start` has run, the
 * dashboard is the only place a user should need. The download is ~145MB and
 * runs in a background thread on the API, so this polls rather than blocking.
 */

const POLL_MS = 3000;

export function VoiceCard() {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.voiceStatus();
      setStatus(next);
      return next;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [refresh]);

  // Poll only while something is actually in flight.
  useEffect(() => {
    const busy = status?.phase === "downloading" || status?.phase === "loading";
    if (!busy) {
      if (timer.current) clearInterval(timer.current);
      timer.current = null;
      return;
    }
    timer.current = setInterval(() => void refresh(), POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [status?.phase, refresh]);

  const setup = async () => {
    setStarting(true);
    try {
      setStatus(await api.voiceEnsure());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not start voice setup.");
    } finally {
      setStarting(false);
    }
  };

  const ready = status?.available ?? false;
  const busy = status?.phase === "downloading" || status?.phase === "loading";

  return (
    <Card padding="lg" className="space-y-3">
      <div className="flex items-center gap-2">
        <AudioLines size={18} className="text-ink" />
        <h2 className="text-lg font-bold text-ink">Voice</h2>
        {ready && (
          <span className="ml-auto flex items-center gap-1 text-sm font-bold text-lime-ink">
            <CheckCircle2 size={15} /> Ready
          </span>
        )}
      </div>

      <p className="text-base leading-relaxed text-stone">
        Talk to Shortlistr instead of clicking. Speech is recognised on this machine — the
        audio never leaves your laptop and there is no account or key to add.
      </p>

      {!status?.library_installed && (
        <p className="rounded-xl border border-mist bg-sage/40 p-3 text-sm text-stone">
          The speech package isn&apos;t installed in this environment yet. It ships with
          Shortlistr&apos;s Python requirements — reinstall them and this card will light up.
        </p>
      )}

      {busy && (
        <p className="flex items-center gap-2 text-sm text-stone">
          <Loader2 size={14} className="animate-spin" />
          {status?.message || "Setting up…"} This is a one-off ~145MB download.
        </p>
      )}

      {status?.phase === "error" && status.error && (
        <p className="rounded-xl border border-danger/40 bg-danger-soft p-3 text-sm text-ink">
          {status.error}
        </p>
      )}

      {status?.library_installed && !ready && !busy && (
        <Button onClick={setup} isLoading={starting}>
          Set up voice
        </Button>
      )}

      {ready && (
        <p className="text-sm text-stone">
          Open <span className="font-semibold text-ink">Voice</span> in the sidebar, press
          start, and say &ldquo;Hey Shortlistr&rdquo;. Model: {status?.model}.
        </p>
      )}
    </Card>
  );
}
