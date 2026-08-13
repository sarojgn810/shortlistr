"use client";

import { motion } from "framer-motion";
import { Mic, Loader2, Volume2 } from "lucide-react";
import type { VoiceState } from "@/src/hooks/useVoiceSession";

/**
 * The orb is the latency story. It scales from the live analyser level, so it
 * moves within a frame of someone speaking — long before the ~500ms it takes to
 * get text back. Driving it from the transcript instead would make the feature
 * feel broken no matter how fast the model is.
 *
 * `armed` and `listening` are deliberately different: "the mic is on" and "I am
 * hearing you right now" are not the same promise, and confusing them is how a
 * voice UI loses trust.
 */

const COPY: Record<VoiceState, string> = {
  idle: "Tap to start",
  armed: 'Say "Hey Shortlistr"',
  listening: "Listening",
  thinking: "Working on it",
  speaking: "Speaking",
};

export function Orb({
  state,
  level,
  onClick,
}: {
  state: VoiceState;
  level: number;
  onClick: () => void;
}) {
  const live = state === "listening";
  const scale = live ? 1 + level * 0.35 : 1;

  return (
    <div className="flex flex-col items-center gap-4">
      <button
        onClick={onClick}
        aria-label={state === "idle" ? "Start voice session" : "Stop voice session"}
        className="relative grid h-44 w-44 place-items-center rounded-full outline-none focus-visible:ring-4 focus-visible:ring-lime/50"
      >
        {/* Halo — tracks amplitude, so it breathes with the room. */}
        <motion.span
          aria-hidden
          className={`absolute inset-0 rounded-full ${
            live ? "bg-lime/30" : state === "idle" ? "bg-stone/10" : "bg-lime/15"
          }`}
          animate={{ scale: live ? 1 + level * 0.55 : state === "armed" ? [1, 1.06, 1] : 1 }}
          transition={
            live
              ? { type: "spring", stiffness: 500, damping: 24 }
              : { duration: 2.4, repeat: Infinity, ease: "easeInOut" }
          }
        />
        <motion.span
          aria-hidden
          className={`absolute inset-6 rounded-full ${live ? "bg-lime/50" : "bg-lime/20"}`}
          animate={{ scale }}
          transition={{ type: "spring", stiffness: 600, damping: 20 }}
        />
        <motion.span
          className={`relative grid h-24 w-24 place-items-center rounded-full shadow-lg ${
            state === "idle" ? "bg-stone/80 text-white" : "bg-ink text-lime"
          }`}
          animate={{ scale: live ? 1 + level * 0.12 : 1 }}
          transition={{ type: "spring", stiffness: 600, damping: 20 }}
        >
          {state === "thinking" ? (
            <Loader2 size={30} className="animate-spin" />
          ) : state === "speaking" ? (
            <Volume2 size={30} />
          ) : (
            <Mic size={30} strokeWidth={live ? 2.5 : 1.75} />
          )}
        </motion.span>
      </button>
      <p className="text-sm font-medium text-stone">{COPY[state]}</p>
    </div>
  );
}
