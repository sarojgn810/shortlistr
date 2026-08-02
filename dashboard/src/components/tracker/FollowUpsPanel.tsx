"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Inbox, Check, RotateCcw } from "lucide-react";
import { Badge } from "@/src/components/ui/Badge";
import { Button } from "@/src/components/ui/Button";
import { useFollowUps } from "@/src/hooks/useFollowUps";
import type { FollowUp } from "@/src/lib/api/client";

/** Applications your mailbox says are waiting on you.
 *
 * These usually have no job row at all — you applied through the employer's own
 * site and the tracker board, which is built on pipeline JOIN jobs, has nothing
 * to show. That is the whole reason this panel exists rather than another column.
 */

const KIND_LABEL: Record<string, string> = {
  application_update: "Needs your reply",
  invite_to_apply: "They asked for you",
};

function relativeDate(iso: string): string {
  if (!iso) return "";
  // SQLite writes "YYYY-MM-DD HH:MM:SS" in UTC; Date needs the T and the Z or
  // it parses as local time and everything looks hours off.
  const parsed = new Date(iso.includes("T") ? iso : `${iso.replace(" ", "T")}Z`);
  if (Number.isNaN(parsed.getTime())) return "";
  const days = Math.floor((Date.now() - parsed.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  return parsed.toLocaleDateString();
}

function FollowUpRow({
  item,
  onResolve,
  onReopen,
}: {
  item: FollowUp;
  onResolve: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const resolved = Boolean(item.resolved_at);

  const act = async (fn: (id: number) => Promise<void>, failure: string) => {
    setBusy(true);
    try {
      await fn(item.id);
    } catch {
      toast.error(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      className={`flex items-start justify-between gap-3 rounded-xl border border-mist bg-white p-4 ${
        resolved ? "opacity-60" : ""
      }`}
    >
      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <p className="text-base font-bold leading-tight text-ink">
            {item.company || "Unknown company"}
          </p>
          <Badge variant={item.kind === "application_update" ? "orange" : "lime"}>
            {KIND_LABEL[item.kind] ?? item.kind}
          </Badge>
          {item.role ? <span className="text-sm text-stone">{item.role}</span> : null}
        </div>
        <p className="line-clamp-2 text-sm text-stone">{item.subject}</p>
        <p className="mt-1 text-xs text-stone/70">
          from your inbox · {relativeDate(item.created_at)}
        </p>
      </div>
      {resolved ? (
        <Button
          variant="ghost"
          size="sm"
          isLoading={busy}
          onClick={() => act(onReopen, "Could not reopen")}
          aria-label={`Reopen follow-up for ${item.company}`}
        >
          <RotateCcw className="mr-1 h-4 w-4" /> Reopen
        </Button>
      ) : (
        <Button
          variant="secondary"
          size="sm"
          isLoading={busy}
          onClick={() => act(onResolve, "Could not mark done")}
          aria-label={`Mark follow-up for ${item.company} done`}
        >
          <Check className="mr-1 h-4 w-4" /> Done
        </Button>
      )}
    </li>
  );
}

export default function FollowUpsPanel() {
  const [showResolved, setShowResolved] = useState(false);
  const { followUps, openCount, isLoading, error, resolve, reopen } =
    useFollowUps(showResolved);

  // Nothing waiting and nothing to un-hide: stay out of the way entirely rather
  // than occupy the top of the page with an empty state.
  if (!isLoading && !error && followUps.length === 0 && !showResolved) return null;

  return (
    <section className="mb-6" aria-labelledby="follow-ups-heading">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2
          id="follow-ups-heading"
          className="flex items-center gap-2 text-lg font-bold text-ink"
        >
          <Inbox className="h-5 w-5 text-orange" />
          Waiting on you
          {openCount > 0 ? <Badge variant="orange">{openCount}</Badge> : null}
        </h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowResolved((v) => !v)}
        >
          {showResolved ? "Hide done" : "Show done"}
        </Button>
      </div>

      <p className="mb-3 text-sm text-stone">
        Applications your inbox says need a reply — including ones you made outside
        Shortlistr, which the board below cannot show.
      </p>

      {isLoading ? (
        <p className="text-sm text-stone">Loading…</p>
      ) : error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : followUps.length === 0 ? (
        <p className="rounded-xl border border-mist bg-white p-4 text-sm text-stone">
          Nothing waiting on you.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {followUps.map((item) => (
            <FollowUpRow
              key={item.id}
              item={item}
              onResolve={resolve}
              onReopen={reopen}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
