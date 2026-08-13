"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type VoiceCommandResponse } from "@/src/lib/api/client";

/**
 * The conversation itself: what was said, what is on offer, what to announce.
 *
 * Three rules here exist because a scan can land 160 jobs and speech is serial —
 * you cannot skim it and you cannot interrupt a monologue politely:
 *
 *  - only jobs scoring at or above ANNOUNCE_MIN_SCORE are worth interrupting
 *    for, the same threshold the Telegram ping already uses;
 *  - at most ANNOUNCE_LIMIT per scan, best first, the rest land silently;
 *  - one at a time, and never while the user is mid-turn.
 */

/**
 * How long a bare command is accepted after an exchange.
 *
 * Was 15s, which expired in the middle of a live conversation: three
 * consecutive utterances were dropped in one session, the last of them "Are you
 * there?" — the user checking whether it had died. It had not; it had stopped
 * listening fifteen seconds earlier and said nothing about it.
 *
 * A turn costs more time than it looks: the agent's own reply plays for several
 * seconds, then the user has to think. The window has to cover both.
 */
export const FOLLOW_UP_MS = 45_000;
const ANNOUNCE_MIN_SCORE = 3.5;
const ANNOUNCE_LIMIT = 3;
const DISCOVER_POLL_MS = 15_000;

export interface Turn {
  role: "user" | "assistant";
  text: string;
}

export interface Offer {
  job_id: string;
  options: string[];
}

interface Job {
  id: string;
  company?: string | null;
  title?: string | null;
  score?: number | null;
  location?: string | null;
}

export function useVoiceDialogue(speak: (text: string) => void) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<VoiceCommandResponse["pending_confirm"]>();
  const [tools, setTools] = useState<string[]>([]);
  const [muted, setMuted] = useState(false);
  const [watching, setWatching] = useState(false);
  const [followUpUntil, setFollowUpUntil] = useState(0);

  // Announced ids persist across scans so a job is briefed once, not every poll.
  const announced = useRef<Set<string>>(new Set());
  const busy = useRef(false);

  const say = useCallback(
    (text: string) => {
      if (!text) return;
      setTurns((t) => [...t, { role: "assistant", text }]);
      speak(text);
    },
    [speak],
  );

  const openFollowUp = useCallback(() => setFollowUpUntil(Date.now() + FOLLOW_UP_MS), []);

  /** Apply a command response: speak it, and pick up any state it carries. */
  const apply = useCallback(
    (res: VoiceCommandResponse, onNav?: (route: string) => void) => {
      if (res.ack) speak(res.ack);
      if (res.speech) say(res.speech);
      if (res.actions?.length) {
        setTools((t) => [...res.actions.map((a) => a.tool), ...t].slice(0, 12));
      }
      setPendingConfirm(res.pending_confirm);
      if (res.nav && onNav) onNav(res.nav);
      if (res.watch?.kind === "discover") setWatching(true);
      if (res.triage === "mute") {
        setMuted(true);
        say("I'll stop announcing new jobs.");
      }
      openFollowUp();
    },
    [say, speak, openFollowUp],
  );

  const addUserTurn = useCallback((text: string) => {
    setTurns((t) => [...t, { role: "user", text }]);
  }, []);

  /** A brief plus an offer. Kept short — see the module note. */
  const announce = useCallback(
    (job: Job) => {
      const company = (job.company || "").trim();
      const title = (job.title || "a role").trim();
      const where = job.location ? ` in ${job.location}` : "";
      const score =
        typeof job.score === "number" ? ` Scored ${Math.round(job.score * 10) / 10}.` : "";
      const lead = company ? `${company} are hiring a ${title}${where}.` : `A ${title} just came in.`;
      say(`${lead}${score} Want me to evaluate it, or prep an application?`);
      setOffer({ job_id: job.id, options: ["evaluate", "prep", "skip"] });
      openFollowUp();
    },
    [say, openFollowUp],
  );

  /** Poll the queued scan and brief what it found. */
  useEffect(() => {
    if (!watching) return;
    let alive = true;

    const check = async () => {
      try {
        const status = await api.discoverStatus();
        if (!alive || status.running) return;
        setWatching(false);
        if (muted) return;

        const rows = (await api.listJobs("inbox", "relevant")) as unknown as Job[];
        const fresh = rows
          .filter((j) => j.id && !announced.current.has(j.id))
          .filter((j) => typeof j.score !== "number" || j.score >= ANNOUNCE_MIN_SCORE)
          .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

        if (!fresh.length) {
          say("The scan finished — nothing new worth flagging.");
          return;
        }
        // Mark every id seen, including the ones we deliberately stay quiet
        // about, so the next scan does not read the backlog out loud.
        rows.forEach((j) => j.id && announced.current.add(j.id));

        const top = fresh.slice(0, ANNOUNCE_LIMIT);
        say(
          fresh.length > top.length
            ? `The scan found ${fresh.length} worth a look. Here are the best ${top.length}.`
            : `The scan found ${top.length}.`,
        );
        announce(top[0]);
      } catch {
        // A failed poll is not worth interrupting the user about; the next
        // tick retries, and the console still shows the scan as running.
      }
    };

    void check();
    const id = setInterval(check, DISCOVER_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [watching, muted, say, announce]);

  const inFollowUp = useCallback(() => Date.now() < followUpUntil, [followUpUntil]);

  return {
    turns,
    offer,
    setOffer,
    pendingConfirm,
    setPendingConfirm,
    tools,
    muted,
    setMuted,
    watching,
    apply,
    say,
    addUserTurn,
    announce,
    inFollowUp,
    followUpUntil,
    openFollowUp,
    busy,
  };
}
