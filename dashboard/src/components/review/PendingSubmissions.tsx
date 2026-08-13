"use client";

import { useEffect, useState } from "react";
import { Send, Undo2 } from "lucide-react";
import type { PendingSubmission } from "@/src/lib/api/client";

/**
 * Applications about to go out, and the chance to stop them.
 *
 * The countdown is the undo window made visible. A delay the user cannot see is
 * not a safeguard — it is just latency they will assume is a bug.
 */
export function PendingSubmissions({
  pending,
  onCancel,
}: {
  pending: PendingSubmission[];
  onCancel: (jobId: string) => void;
}) {
  // Tick locally so the number moves every second rather than only when the
  // list is refetched.
  const [, force] = useState(0);
  useEffect(() => {
    if (!pending.length) return;
    const id = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [pending.length]);

  if (!pending.length) return null;

  const now = Date.now() / 1000;

  return (
    <div className="space-y-2 rounded-2xl border border-orange/40 bg-orange/5 p-4">
      <p className="flex items-center gap-1.5 text-sm font-bold text-ink">
        <Send size={14} className="text-orange" />
        {pending.length === 1 ? "Sending shortly" : `Sending ${pending.length} shortly`}
      </p>
      {pending.map((item) => {
        const left = Math.max(0, Math.ceil(item.submit_after - now));
        return (
          <div key={item.job_id} className="flex items-center justify-between gap-3">
            <span className="truncate text-sm text-stone">
              {left > 0 ? `Goes out in ${left}s` : "Sending now…"}
            </span>
            <button
              onClick={() => onCancel(item.job_id)}
              disabled={left === 0}
              className="flex shrink-0 items-center gap-1 rounded-full bg-white px-3 py-1.5 text-sm font-semibold text-ink transition-all active:scale-95 disabled:opacity-40"
            >
              <Undo2 size={13} /> Cancel
            </button>
          </div>
        );
      })}
    </div>
  );
}
