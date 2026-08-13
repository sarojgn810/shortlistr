"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Orb } from "@/src/components/voice/Orb";
import { Transcript } from "@/src/components/voice/Transcript";
import { ToolTicker } from "@/src/components/voice/ToolTicker";
import { ConfirmCard } from "@/src/components/voice/ConfirmCard";
import { OfferCard } from "@/src/components/voice/OfferCard";
import { useVoiceSession } from "@/src/hooks/useVoiceSession";
import { useVoiceDialogue } from "@/src/hooks/useVoiceDialogue";
import { api, ApiError, type VoiceStatus } from "@/src/lib/api/client";
import { createSpeaker, isEcho, primeVoices, type Speaker } from "@/src/lib/voice/speech";

/** Time for the tail of our own audio to clear the room before listening again. */
const ECHO_TAIL_MS = 500;

/**
 * The voice console.
 *
 * Flow per utterance: Silero VAD endpoints it in the browser, faster-whisper
 * transcribes locally, then /voice/command checks the wake phrase, tries the
 * deterministic router, and only falls back to the LLM on a miss.
 */
export default function VoicePage() {
  const router = useRouter();
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [heard, setHeard] = useState("");
  const [remaining, setRemaining] = useState(0);
  const [speaking, setSpeaking] = useState(false);

  // Speech synthesis is free, local, and starts well inside the time any model
  // would take to generate audio. createSpeaker handles Chrome's two traps:
  // voices that load late (speak() before then is silently dropped) and the
  // agent's own output coming back through the microphone.
  const captureRef = useRef<{ pause: () => void; resume: () => void }>({
    pause: () => {},
    resume: () => {},
  });

  const speakerRef = useRef<Speaker | null>(null);
  if (typeof window !== "undefined" && !speakerRef.current) {
    speakerRef.current = createSpeaker(window.speechSynthesis, {
      // Deafen the mic for exactly as long as we are talking. Without this the
      // agent transcribes its own reply and answers it, forever.
      onStart: () => {
        setSpeaking(true);
        captureRef.current.pause();
      },
      onEnd: () => {
        setSpeaking(false);
        // A beat for the tail of the audio to leave the room before listening
        // again; the echo filter covers whatever still slips through.
        setTimeout(() => captureRef.current.resume(), ECHO_TAIL_MS);
      },
    });
  }

  const speak = useCallback((text: string) => {
    void speakerRef.current?.speak(text);
  }, []);

  // Warm the voice list on mount so the first reply is not the one that waits.
  useEffect(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      void primeVoices(window.speechSynthesis);
    }
  }, []);

  const dialogue = useVoiceDialogue(speak);
  const {
    turns, offer, setOffer, pendingConfirm, setPendingConfirm,
    tools, apply, say, addUserTurn, inFollowUp, followUpUntil, openFollowUp,
  } = dialogue;

  const offerRef = useRef(offer);
  const followUpRef = useRef(inFollowUp);
  useEffect(() => {
    offerRef.current = offer;
    followUpRef.current = inFollowUp;
  }, [offer, inFollowUp]);

  useEffect(() => {
    api.voiceStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  // Follow-up countdown — the user should never have to guess whether a bare
  // command will be heard.
  useEffect(() => {
    const id = setInterval(
      () => setRemaining(Math.max(0, Math.ceil((followUpUntil - Date.now()) / 1000))),
      250,
    );
    return () => clearInterval(id);
  }, [followUpUntil]);

  const handleUtterance = useCallback(
    async (pcm: Int16Array) => {
      try {
        const heardRes = await api.transcribe(pcm);
        if (!heardRes.available) {
          say(heardRes.reason || "Speech recognition isn't set up yet.");
          return;
        }
        const text = heardRes.text.trim();
        if (!text) return;

        // Backstop for the tail that arrives while capture is resuming: our own
        // reply read back to us is a valid-looking command, and acting on it is
        // how the agent ends up interviewing itself.
        if (speakerRef.current?.isSpeaking() || isEcho(text, speakerRef.current?.lastSpoken() ?? "")) {
          return;
        }
        setHeard(text);

        const res = await api.voiceCommand({
          text,
          woken: followUpRef.current(),
          offer: offerRef.current,
          job_id: offerRef.current?.job_id ?? null,
          history: turns.slice(-6).map((t) => ({ role: t.role, content: t.text })),
        });

        // Not addressed to us — room noise. Say nothing, log nothing.
        if (!res.woke) return;

        addUserTurn(res.heard || text);
        if (!res.miss) setOffer(null);
        apply(res, (route) => router.push(route));
      } catch (e) {
        say(e instanceof ApiError ? e.message : "Something went wrong there.");
      }
    },
    [addUserTurn, apply, router, say, setOffer, turns],
  );

  const { state, level, error, start, stop, pauseCapture, resumeCapture } = useVoiceSession({
    onUtterance: handleUtterance,
    // Barge-in: talking over the agent stops it mid-sentence, the way a person
    // would stop.
    // Barge-in — but bargeIn() declines inside the guard window, where the
    // "speech" is our own reply reaching the mic through the speakers.
    onSpeechStart: () => speakerRef.current?.bargeIn(),
  });

  // The speaker is created during render, before the session hook exists, so
  // the pause/resume pair is handed over through a ref.
  useEffect(() => {
    captureRef.current = { pause: pauseCapture, resume: resumeCapture };
  }, [pauseCapture, resumeCapture]);

  // "speaking" is the agent's turn; otherwise the session's own phase applies.
  const orbState = speaking && state !== "idle" ? "speaking" : state;

  const confirm = useCallback(
    async (ok: boolean) => {
      const p = pendingConfirm;
      setPendingConfirm(undefined);
      if (!p) return;
      if (!ok) {
        say("Cancelled.");
        return;
      }
      try {
        const res = await api.voiceCommand({ confirm_tool: p.tool, confirm_args: p.args });
        apply(res as never);
      } catch (e) {
        toast.error(e instanceof ApiError ? e.message : "That action failed.");
      }
    },
    [apply, pendingConfirm, say, setPendingConfirm],
  );

  const chooseOffer = useCallback(
    async (option: string) => {
      addUserTurn(option);
      openFollowUp();
      try {
        const res = await api.voiceCommand({
          text: option,
          woken: true,
          offer: offerRef.current,
          job_id: offerRef.current?.job_id ?? null,
        });
        setOffer(null);
        apply(res, (route) => router.push(route));
      } catch (e) {
        toast.error(e instanceof ApiError ? e.message : "That didn't work.");
      }
    },
    [addUserTurn, apply, openFollowUp, router, setOffer],
  );

  const needsSetup = status && !status.available;

  return (
    <DashboardShell title="Voice" breadcrumbs={["Voice"]}>
      <div className="mx-auto grid max-w-5xl gap-4 py-4 md:grid-cols-[1fr_20rem]">
        <section className="flex min-h-[26rem] flex-col gap-6 rounded-2xl border border-mist bg-white p-6">
          <div className="flex justify-center pt-4">
            <Orb
              state={orbState}
              level={level}
              onClick={() => {
                if (state !== "idle") return stop();
                // Synchronous, inside the click: this is the only moment Chrome
                // will accept as user activation for speech.
                speakerRef.current?.unlock();
                // Clicking start *is* addressing the app, so the first command
                // needs no wake phrase. Without this, a mangled "Hey
                // Shortlistr" leaves no way in at all — which is exactly how
                // this read as completely broken.
                openFollowUp();
                void start();
              }}
            />
          </div>

          {remaining > 0 && state !== "idle" && (
            <p className="text-center text-xs text-stone">
              Follow-ups need no wake phrase · {remaining}s
            </p>
          )}

          {heard && state !== "idle" && (
            <p className="text-center text-xs italic text-stone/70">heard: “{heard}”</p>
          )}

          <div className="min-h-0 flex-1">
            <Transcript turns={turns} />
          </div>
        </section>

        <aside className="space-y-3">
          {error && (
            <div className="rounded-2xl border border-danger/40 bg-danger-soft p-3 text-sm text-ink">
              {error}
            </div>
          )}

          {needsSetup && (
            <div className="rounded-2xl border border-orange/40 bg-orange/5 p-3">
              <div className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-ink">
                <AlertTriangle size={14} className="text-orange" /> Voice needs setup
              </div>
              <p className="text-sm text-stone">
                {status?.reason || "The speech model isn't downloaded yet."}
              </p>
              <button
                onClick={() => router.push("/connections")}
                className="mt-2 text-sm font-semibold text-ink underline"
              >
                Open Connections
              </button>
            </div>
          )}

          {pendingConfirm && (
            <ConfirmCard
              pending={pendingConfirm}
              onConfirm={() => void confirm(true)}
              onCancel={() => void confirm(false)}
            />
          )}

          {offer && <OfferCard offer={offer} onChoose={(o) => void chooseOffer(o)} />}

          <ToolTicker tools={tools} />

          <div className="rounded-2xl border border-mist bg-white p-3">
            <p className="mb-2 text-xs font-bold uppercase tracking-widest text-stone/60">Try</p>
            <ul className="space-y-1 text-sm text-stone">
              <li>“Hey Shortlistr, what&rsquo;s my status”</li>
              <li>“…scan for jobs”</li>
              <li>“…open my tracker”</li>
              <li>“…how&rsquo;s the search going?”</li>
            </ul>
          </div>
        </aside>
      </div>
    </DashboardShell>
  );
}
