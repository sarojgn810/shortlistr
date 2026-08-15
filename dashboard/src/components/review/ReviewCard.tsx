"use client";

import { Check, X, ExternalLink, MapPin, Send } from "lucide-react";
import { OutreachPanel } from "@/src/components/review/OutreachPanel";
import type { ReviewItem } from "@/src/lib/api/client";

/**
 * One job, with the reason it ranks where it does.
 *
 * The score is shown as the fraction it came from — "9 of 10 requirements" —
 * because a bare 4.4 is what made the old pile unreadable. The unmet ones are
 * listed by name: they are the decision, and later they are what the cover
 * letter has to answer.
 */
export function ReviewCard({
  item,
  onApprove,
  onApproveAndSend,
  onSkip,
  busy,
}: {
  item: ReviewItem;
  onApprove: () => void;
  onApproveAndSend: () => void;
  onSkip: () => void;
  busy: boolean;
}) {
  return (
    <article className="rounded-2xl border border-mist bg-white p-6">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-xl font-bold text-ink">{item.title || "Untitled role"}</h2>
          <p className="mt-0.5 flex items-center gap-3 text-base text-stone">
            <span className="font-semibold text-ink">{item.company || "Unknown company"}</span>
            {item.location && (
              <span className="flex items-center gap-1 truncate">
                <MapPin size={13} /> {item.location}
              </span>
            )}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-3xl font-bold leading-none text-ink">{item.score.toFixed(1)}</div>
          <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-stone">
            {item.met} of {item.total} met
          </div>
        </div>
      </header>

      {item.unmet.length > 0 ? (
        <div className="mb-4 rounded-xl border border-orange/30 bg-orange/5 p-3">
          <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-stone/70">
            {item.unmet.length === 1 ? "Gap" : `${item.unmet.length} gaps`}
          </p>
          <ul className="space-y-1">
            {item.unmet.slice(0, 4).map((gap, i) => (
              <li key={i} className="text-sm leading-snug text-ink">
                · {gap}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mb-4 rounded-xl border border-lime/40 bg-lime/10 p-3 text-sm font-semibold text-ink">
          Every stated requirement is answered by your CV.
        </p>
      )}

      {item.summary && <p className="mb-5 text-base leading-relaxed text-stone">{item.summary}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={onApprove}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-full bg-ink px-5 py-2.5 text-base font-semibold text-lime transition-all active:scale-95 disabled:opacity-50"
        >
          <Check size={16} /> Approve
        </button>
        {/* Approving and sending are separate buttons on purpose. Approval is
            the human decision; sending is what follows it. Merging them would
            make every approval irreversible by default. */}
        <button
          onClick={onApproveAndSend}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-full border border-ink/20 px-5 py-2.5 text-base font-semibold text-ink transition-all hover:bg-mist active:scale-95 disabled:opacity-50"
        >
          <Send size={15} /> Approve &amp; send
        </button>
        <button
          onClick={onSkip}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-full bg-mist px-5 py-2.5 text-base font-semibold text-stone transition-all hover:text-ink active:scale-95 disabled:opacity-50"
        >
          <X size={16} /> Skip
        </button>
        {item.url && (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto flex items-center gap-1 text-sm font-semibold text-stone underline hover:text-ink"
          >
            Open posting <ExternalLink size={13} />
          </a>
        )}
      </div>

      <div className="mt-4 border-t border-mist pt-4">
        <OutreachPanel jobId={item.job_id} />
      </div>
    </article>
  );
}
