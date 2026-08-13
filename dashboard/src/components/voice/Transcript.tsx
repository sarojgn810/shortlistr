"use client";

import { useEffect, useRef } from "react";
import type { Turn } from "@/src/hooks/useVoiceDialogue";

/** The spoken exchange, written down — speech is serial and cannot be skimmed. */
export function Transcript({ turns }: { turns: Turn[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  if (!turns.length) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-stone">
        <p>
          Start a session, then say <span className="font-semibold text-ink">&ldquo;Hey Shortlistr&rdquo;</span>
          <br />
          Try &ldquo;what&rsquo;s my status&rdquo; or &ldquo;scan for jobs&rdquo;.
        </p>
      </div>
    );
  }

  return (
    <div className="custom-scrollbar h-full space-y-3 overflow-y-auto px-1 py-2">
      {turns.map((turn, i) => (
        <div key={i} className={turn.role === "user" ? "text-right" : "text-left"}>
          <span
            className={`inline-block max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
              turn.role === "user" ? "bg-ink text-lime" : "bg-mist text-ink"
            }`}
          >
            {turn.text}
          </span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
