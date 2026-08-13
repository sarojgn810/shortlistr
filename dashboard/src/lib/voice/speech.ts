/**
 * Speaking, with the two Chrome behaviours that make naive TTS silent.
 *
 * **Voices load asynchronously.** `speechSynthesis.getVoices()` returns an empty
 * array until a `voiceschanged` event fires, and `speak()` called before then is
 * silently discarded — no error, no event, nothing. Measured on this machine:
 * 0 voices at page load, 190 a moment later. The first reply is exactly the one
 * that lands in that window, so the bug reads as "voice mode never talks".
 *
 * **The mic is live while we speak.** Barge-in cancels playback when the user
 * talks over the agent, but the microphone also hears the agent through the
 * speakers. Without a settling window the reply cancels itself on its own echo.
 */

export const VOICE_WAIT_MS = 3000;
/** Echo needs ~this long to reach the mic and trip the VAD. */
export const BARGE_IN_GUARD_MS = 600;

type Synth = SpeechSynthesis;

let voicesPromise: Promise<SpeechSynthesisVoice[]> | null = null;

/**
 * Start loading voices and resolve when they arrive.
 *
 * Safe to call repeatedly — the work happens once. Call it early (on mount) so
 * the list is warm before anyone speaks.
 */
export function primeVoices(synth: Synth, timeoutMs = VOICE_WAIT_MS): Promise<SpeechSynthesisVoice[]> {
  if (voicesPromise) return voicesPromise;

  voicesPromise = new Promise<SpeechSynthesisVoice[]>((resolve) => {
    const ready = synth.getVoices();
    if (ready.length) return resolve(ready);

    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve(synth.getVoices());
    };
    synth.addEventListener?.("voiceschanged", finish, { once: true });
    // Resolve regardless: some platforms never fire the event, and speaking
    // with the platform default beats not speaking at all.
    setTimeout(finish, timeoutMs);
  });

  return voicesPromise;
}

/**
 * Full-bodied voices, best first.
 *
 * The platform default is deliberately *not* preferred. On this machine it is
 * "Rishi / en-IN", one of the compact voices, and compact voices are the ones
 * that sound thin and unsteady when read at length — the first thing anyone
 * says about them is that they sound wrong. These names are the full-quality
 * macOS set and are checked ahead of it.
 */
const PREFERRED_VOICES = ["samantha", "alex", "daniel", "karen", "moira", "tessa", "serena", "fiona"];

export function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (!voices.length) return null;
  const english = voices.filter((v) => v.lang?.toLowerCase().startsWith("en"));
  if (!english.length) return voices.find((v) => v.default) ?? voices[0];

  // If the user has downloaded an Enhanced/Premium variant, nothing beats it.
  const premium = english.find((v) => /premium|enhanced/i.test(v.name));
  if (premium) return premium;

  for (const name of PREFERRED_VOICES) {
    const hit = english.find((v) => v.name.toLowerCase().startsWith(name));
    if (hit) return hit;
  }
  return english.find((v) => v.default) ?? english[0];
}

/**
 * Did we just say this ourselves?
 *
 * The microphone hears the agent through the speakers, and a transcript of our
 * own reply is a perfectly valid-looking command. Left unchecked the agent
 * answers itself forever: one status reply became six turns of the agent
 * interviewing itself. Suppressing capture during playback is the main defence;
 * this catches the tail still travelling through the air when it resumes.
 */
export function isEcho(heard: string, spoken: string): boolean {
  const words = (s: string) =>
    s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(Boolean);

  const h = words(heard);
  const said = new Set(words(spoken));
  // Short utterances ("next", "approve") overlap common words by chance, and
  // wrongly dropping a real command is worse than letting one echo through.
  if (h.length < 3 || !said.size) return false;

  const shared = h.filter((w) => said.has(w)).length;
  return shared / h.length >= 0.6;
}

export interface Speaker {
  speak: (text: string) => Promise<void>;
  /** Cancel playback, but not within the guard window — that would be our echo. */
  bargeIn: () => boolean;
  cancel: () => void;
  /** True while audio is playing — capture must stay suppressed until it is false. */
  isSpeaking: () => boolean;
  /** The last thing we said, for the echo backstop. */
  lastSpoken: () => string;
  /**
   * Unlock playback. Must be called **synchronously inside a click handler**.
   *
   * Chrome gates speech synthesis on user activation, and activation is judged
   * from the call stack. Every real reply is spoken about a second after the
   * user stopped talking — an async chain with no gesture in it — so without a
   * priming utterance fired during the click that starts the session, the very
   * first reply can be dropped as silently as the missing-voices case.
   */
  unlock: () => void;
}

export function createSpeaker(
  synth: Synth,
  handlers: { onStart?: () => void; onEnd?: () => void } = {},
  guardMs = BARGE_IN_GUARD_MS,
  now: () => number = () => Date.now(),
): Speaker {
  let startedAt = 0;
  let said = "";

  const cancel = () => {
    startedAt = 0;
    synth.cancel();
    handlers.onEnd?.();
  };

  return {
    isSpeaking: () => synth.speaking,
    lastSpoken: () => said,

    unlock() {
      // A short, silent utterance: enough to satisfy the activation check,
      // inaudible to the user. Speaking "" is ignored by some builds, so send
      // a space at zero volume.
      const primer = new SpeechSynthesisUtterance(" ");
      primer.volume = 0;
      synth.speak(primer);
      void primeVoices(synth);
    },

    async speak(text: string) {
      if (!text) return;
      // Await voices before the first utterance — this is the whole fix.
      await primeVoices(synth);

      said = text;
      const utterance = new SpeechSynthesisUtterance(text);
      const voice = pickVoice(synth.getVoices());
      if (voice) utterance.voice = voice;
      // Natural pace. The slight speed-up this used to carry made the compact
      // voices sound unsteady for no real gain.
      utterance.rate = 1.0;
      utterance.onstart = () => {
        startedAt = now();
        handlers.onStart?.();
      };
      utterance.onend = () => {
        startedAt = 0;
        handlers.onEnd?.();
      };
      utterance.onerror = () => {
        startedAt = 0;
        handlers.onEnd?.();
      };
      synth.speak(utterance);
    },

    bargeIn() {
      if (!synth.speaking) return false;
      // Inside the guard window the "speech" we just heard is our own output
      // coming back through the microphone.
      if (startedAt && now() - startedAt < guardMs) return false;
      cancel();
      return true;
    },

    cancel,
  };
}

/** Test seam — the module-level cache would otherwise leak between cases. */
export function __resetVoiceCache() {
  voicesPromise = null;
}
