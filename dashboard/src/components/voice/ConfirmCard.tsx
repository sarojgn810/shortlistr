"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/src/components/ui/Button";
import type { PendingConfirm } from "@/src/lib/api/client";

/**
 * Submit-class tools stop here.
 *
 * The spoken word that confirms is "confirm", never "yes". "Yes" is short,
 * acoustically common, and turns up in ambient conversation — a mishearing
 * would launch an irreversible external action. "Confirm" has to be meant.
 */
export function ConfirmCard({
  pending,
  onConfirm,
  onCancel,
}: {
  pending: PendingConfirm;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="rounded-2xl border border-orange/40 bg-orange/5 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
        <AlertTriangle size={16} className="text-orange" />
        Needs your confirmation
      </div>
      <p className="mb-3 text-sm text-stone">{pending.prompt}</p>
      <div className="flex gap-2">
        <Button onClick={onConfirm} className="flex-1">
          Confirm
        </Button>
        <Button variant="secondary" onClick={onCancel} className="flex-1">
          Cancel
        </Button>
      </div>
      <p className="mt-2 text-xs text-stone">
        Or say <span className="font-semibold text-ink">confirm</span>. Nothing is ever submitted
        for you.
      </p>
    </div>
  );
}
