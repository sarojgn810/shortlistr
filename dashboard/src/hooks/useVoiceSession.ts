"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Microphone capture with local voice-activity detection.
 *
 * The mic opens only when `start()` is called and is fully released by `stop()`
 * — there is no ambient listening and no wake-word model. Silero VAD decides
 * where an utterance begins and ends; the transcript decides whether it was
 * addressed to us.
 *
 * `level` is the load-bearing detail. It updates every animation frame straight
 * from the analyser, with no dependency on transcription, which is what lets the
 * orb react the moment someone speaks rather than ~500ms later when text comes
 * back. Driving the orb from the transcript instead would make the whole feature
 * feel broken however fast the model is.
 */

export type VoiceState = "idle" | "armed" | "listening" | "thinking" | "speaking";

interface Options {
  /** Called with 16kHz mono PCM when an utterance ends. */
  onUtterance: (pcm: Int16Array) => void | Promise<void>;
  /** Fired the instant speech starts — used to cancel playback for barge-in. */
  onSpeechStart?: () => void;
}

const TARGET_RATE = 16000;

function toInt16(float32: Float32Array): Int16Array {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

export function useVoiceSession({ onUtterance, onSpeechStart }: Options) {
  const [state, setState] = useState<VoiceState>("idle");
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const vadRef = useRef<{ start: () => void; pause: () => void; destroy: () => void } | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  // Callbacks live in refs so re-renders never tear down a live session.
  const onUtteranceRef = useRef(onUtterance);
  const onSpeechStartRef = useRef(onSpeechStart);
  const stateRef = useRef<VoiceState>("idle");

  useEffect(() => {
    onUtteranceRef.current = onUtterance;
    onSpeechStartRef.current = onSpeechStart;
  }, [onUtterance, onSpeechStart]);

  const setPhase = useCallback((next: VoiceState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  /**
   * Stop and restart listening around our own playback.
   *
   * The microphone hears the agent through the speakers, and a transcript of
   * our own reply routes as a perfectly ordinary command — one status answer
   * turned into six turns of the agent interviewing itself. A timing guard
   * cannot fix that: an eight-second reply echoes for eight seconds. The only
   * reliable answer is not to listen while we talk.
   *
   * The cost is voice barge-in during a reply. Replies here are a sentence or
   * two by design, so the deaf window is short, and clicking the orb still
   * stops everything immediately.
   */
  const pauseCapture = useCallback(() => {
    vadRef.current?.pause();
  }, []);

  const resumeCapture = useCallback(() => {
    if (vadRef.current && stateRef.current !== "idle") vadRef.current.start();
  }, []);

  const stop = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    vadRef.current?.destroy();
    vadRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void audioCtxRef.current?.close();
    audioCtxRef.current = null;
    setLevel(0);
    setPhase("idle");
  }, [setPhase]);

  const start = useCallback(async () => {
    if (stateRef.current !== "idle") return;
    setError(null);
    try {
      // Dynamic import: the VAD package pulls onnxruntime-web, which is large
      // and has no business loading on pages that never open a mic.
      const { MicVAD } = await import("@ricky0123/vad-web");

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;

      // Amplitude for the orb, read directly off the analyser.
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);

      const vad = await MicVAD.new({
        // We own the stream so the analyser and the VAD read the same mic, and
        // stop() has one place to release it.
        getStream: async () => stream,
        pauseStream: async () => {},
        resumeStream: async () => stream,
        model: "v5",
        // Assets are served from public/vad, never a CDN: a local-first app
        // must not reach an outside host to hear you.
        baseAssetPath: "/vad/",
        onnxWASMBasePath: "/vad/",
        onSpeechStart: () => {
          onSpeechStartRef.current?.();
          setPhase("listening");
        },
        onSpeechEnd: (audio: Float32Array) => {
          setPhase("thinking");
          // The hook owns the return to "armed" so callers never have to
          // remember it in a finally, and never have to reach back for
          // setPhase from a callback defined before this hook runs.
          void Promise.resolve(onUtteranceRef.current(toInt16(audio))).finally(() => {
            if (stateRef.current === "thinking") setPhase("armed");
          });
        },
        onVADMisfire: () => setPhase("armed"),
      });
      vadRef.current = vad;
      vad.start();
      setPhase("armed");
    } catch (e) {
      const why =
        e instanceof DOMException && e.name === "NotAllowedError"
          ? "Microphone access was blocked. Allow it in your browser's site settings."
          : e instanceof Error
            ? e.message
            : "Could not start the microphone.";
      setError(why);
      stop();
    }
  }, [setPhase, stop]);

  // Release the mic if the component unmounts mid-session.
  useEffect(() => stop, [stop]);

  return {
    state,
    level,
    error,
    start,
    stop,
    pauseCapture,
    resumeCapture,
    /** Set by the console around network calls and playback. */
    setPhase,
    sampleRate: TARGET_RATE,
  };
}
