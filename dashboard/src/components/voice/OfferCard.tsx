"use client";

import type { Offer } from "@/src/hooks/useVoiceDialogue";

/**
 * What the agent just offered, and what a one-word answer will do.
 *
 * The offer is also how a job gets picked. Speech cannot carry an id, and
 * Whisper mangles company names, so "evaluate" resolves against whatever is
 * shown here rather than against anything the user tried to pronounce.
 */
export function OfferCard({ offer, onChoose }: { offer: Offer; onChoose: (option: string) => void }) {
  return (
    <div className="rounded-2xl border border-mist bg-white p-3">
      <p className="mb-2 text-xs font-bold uppercase tracking-widest text-stone/60">
        Say one of these
      </p>
      <div className="flex flex-wrap gap-2">
        {offer.options.map((option) => (
          <button
            key={option}
            onClick={() => onChoose(option)}
            className="rounded-full bg-mist px-3 py-1.5 text-sm font-medium text-ink transition-all hover:bg-lime active:scale-95"
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}
