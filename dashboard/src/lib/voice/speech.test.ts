import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  BARGE_IN_GUARD_MS,
  __resetVoiceCache,
  createSpeaker,
  isEcho,
  pickVoice,
  primeVoices,
} from "./speech";

/** A Chrome-shaped SpeechSynthesis whose voice list arrives late, as Chrome's does. */
function fakeSynth({ voicesAfterMs = 0 }: { voicesAfterMs?: number } = {}) {
  const voices = [
    { name: "Rishi", lang: "en-IN", default: true },
    { name: "Aaron", lang: "en-US", default: false },
    { name: "Amelie", lang: "fr-FR", default: false },
  ] as SpeechSynthesisVoice[];

  let loaded = voicesAfterMs === 0;
  const listeners: Record<string, (() => void)[]> = {};
  const spoken: { text: string; voice: string | undefined }[] = [];

  if (voicesAfterMs > 0) {
    setTimeout(() => {
      loaded = true;
      listeners.voiceschanged?.forEach((fn) => fn());
    }, voicesAfterMs);
  }

  const synth = {
    speaking: false,
    getVoices: () => (loaded ? voices : []),
    addEventListener: (type: string, fn: () => void) => {
      (listeners[type] ||= []).push(fn);
    },
    speak: (u: SpeechSynthesisUtterance) => {
      synth.speaking = true;
      spoken.push({ text: u.text, voice: u.voice?.name });
      u.onstart?.(null as never);
    },
    cancel: () => {
      synth.speaking = false;
    },
    spoken,
  };
  return synth as unknown as SpeechSynthesis & { spoken: typeof spoken };
}

beforeEach(() => {
  __resetVoiceCache();
  vi.stubGlobal(
    "SpeechSynthesisUtterance",
    class {
      text: string;
      voice: SpeechSynthesisVoice | null = null;
      rate = 1;
      onstart: ((e: unknown) => void) | null = null;
      onend: ((e: unknown) => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      constructor(text: string) {
        this.text = text;
      }
    },
  );
});

describe("primeVoices", () => {
  it("waits for voiceschanged rather than reading an empty list", async () => {
    const synth = fakeSynth({ voicesAfterMs: 20 });
    expect(synth.getVoices()).toHaveLength(0);

    const voices = await primeVoices(synth);

    expect(voices).toHaveLength(3);
  });

  it("resolves even when the event never fires", async () => {
    const listenerless = {
      getVoices: () => [],
      addEventListener: () => {},
      speak: () => {},
      cancel: () => {},
      speaking: false,
    } as unknown as SpeechSynthesis;

    // Speaking with the platform default beats never speaking.
    await expect(primeVoices(listenerless, 10)).resolves.toEqual([]);
  });
});

describe("speak", () => {
  it("does not drop the first utterance while voices are still loading", async () => {
    // The reported bug: nothing was ever heard, because the first reply landed
    // in the window where Chrome reports zero voices and silently discards it.
    const synth = fakeSynth({ voicesAfterMs: 20 });
    const speaker = createSpeaker(synth);

    await speaker.speak("You've got 7 approved.");

    expect(synth.spoken).toHaveLength(1);
    expect(synth.spoken[0].text).toBe("You've got 7 approved.");
  });

  it("picks an English voice", async () => {
    const synth = fakeSynth();
    await createSpeaker(synth).speak("hello");

    expect(synth.spoken[0].voice).toBe("Rishi");
  });

  it("ignores empty text", async () => {
    const synth = fakeSynth();
    await createSpeaker(synth).speak("");

    expect(synth.spoken).toHaveLength(0);
  });
});

describe("unlock", () => {
  it("speaks a silent primer so Chrome grants activation", () => {
    // Chrome judges user activation from the call stack. Real replies are
    // spoken ~1s after the user stops talking, with no gesture in scope, so
    // the session-start click has to prime the engine or the first reply is
    // dropped as silently as the missing-voices case.
    const synth = fakeSynth();
    createSpeaker(synth).unlock();

    expect(synth.spoken).toHaveLength(1);
    expect(synth.spoken[0].text).toBe(" ");
  });

  it("is inaudible", () => {
    const synth = fakeSynth();
    const spoken: SpeechSynthesisUtterance[] = [];
    (synth as unknown as { speak: (u: SpeechSynthesisUtterance) => void }).speak = (u) => {
      spoken.push(u);
    };

    createSpeaker(synth).unlock();

    expect(spoken[0].volume).toBe(0);
  });
});

describe("bargeIn", () => {
  it("ignores the agent's own echo arriving back through the mic", async () => {
    let clock = 1000;
    const synth = fakeSynth();
    const speaker = createSpeaker(synth, {}, BARGE_IN_GUARD_MS, () => clock);

    await speaker.speak("a long spoken answer");
    clock += 100; // echo reaches the mic and trips the VAD

    expect(speaker.bargeIn()).toBe(false);
    expect(synth.speaking).toBe(true);
  });

  it("stops for a real interruption once the guard has passed", async () => {
    let clock = 1000;
    const synth = fakeSynth();
    const speaker = createSpeaker(synth, {}, BARGE_IN_GUARD_MS, () => clock);

    await speaker.speak("a long spoken answer");
    clock += BARGE_IN_GUARD_MS + 50;

    expect(speaker.bargeIn()).toBe(true);
    expect(synth.speaking).toBe(false);
  });

  it("is a no-op when nothing is playing", () => {
    const speaker = createSpeaker(fakeSynth());
    expect(speaker.bargeIn()).toBe(false);
  });
});

describe("pickVoice", () => {
  /** The English voices actually present on the machine this was reported on. */
  const macOsVoices = [
    { name: "Rishi", lang: "en-IN", default: true },
    { name: "Daniel (English (United Kingdom))", lang: "en-GB", default: false },
    { name: "Karen", lang: "en-AU", default: false },
    { name: "Moira", lang: "en-IE", default: false },
    { name: "Samantha", lang: "en-US", default: false },
    { name: "Tessa", lang: "en-ZA", default: false },
  ] as SpeechSynthesisVoice[];

  it("does not pick the compact system default", () => {
    // Rishi is the platform default here and is one of the compact voices —
    // reported as sounding thin and unsteady. Preferring `default` is what
    // selected it.
    expect(pickVoice(macOsVoices)?.name).toBe("Samantha");
  });

  it("prefers a downloaded Enhanced voice over everything", () => {
    const withPremium = [
      ...macOsVoices,
      { name: "Ava (Premium)", lang: "en-US", default: false },
    ] as SpeechSynthesisVoice[];

    expect(pickVoice(withPremium)?.name).toBe("Ava (Premium)");
  });

  it("falls back to the default English voice when no preferred name exists", () => {
    const obscure = [
      { name: "Zarvox", lang: "en-US", default: false },
      { name: "Trinoids", lang: "en-US", default: true },
    ] as SpeechSynthesisVoice[];

    expect(pickVoice(obscure)?.name).toBe("Trinoids");
  });

  it("falls back to a non-English voice rather than nothing", () => {
    const only = [{ name: "Amelie", lang: "fr-FR", default: true }] as SpeechSynthesisVoice[];
    expect(pickVoice(only)?.name).toBe("Amelie");
  });

  it("returns null for an empty list", () => {
    expect(pickVoice([])).toBeNull();
  });
});

describe("isEcho", () => {
  it("catches the agent hearing its own reply", () => {
    // Straight from the logs: the agent transcribed its own status answer and
    // routed it as a command, then answered that, six turns deep.
    const spoken = "You've got 257 evaluated, 6 approved, 46 waiting to be evaluated and 2 submitted.";
    const heard = "You've got 257 evaluated, 6 approved, 46 waiting to be evaluated and 2 submitted.";

    expect(isEcho(heard, spoken)).toBe(true);
  });

  it("catches a partial echo with transcription drift", () => {
    const spoken = "Stripe are hiring a Senior Site Reliability Engineer in Bangalore.";
    const heard = "Stripe are hiring a senior site reliability engineer in Bangalore";

    expect(isEcho(heard, spoken)).toBe(true);
  });

  it("lets a genuine command through", () => {
    const spoken = "You've got 257 evaluated, 6 approved and 2 submitted.";
    expect(isEcho("open my tracker please now", spoken)).toBe(false);
  });

  it("does not judge short commands", () => {
    // "next" and "approve" collide with common words by chance, and dropping a
    // real command is worse than letting one echo through.
    const spoken = "Approve this one, or shall I skip it?";
    expect(isEcho("approve", spoken)).toBe(false);
    expect(isEcho("skip it", spoken)).toBe(false);
  });

  it("is inert before anything has been said", () => {
    expect(isEcho("what's my status", "")).toBe(false);
  });
});
