"use client";

import { useApiStatus } from "@/src/hooks/useApiStatus";

export function OfflineBanner() {
  const { online } = useApiStatus();

  if (online) return null;

  return (
    <div
      role="alert"
      className="mb-6 rounded-2xl border border-orange/40 bg-orange/10 px-5 py-4 text-base text-ink"
    >
      <strong>Shortlistr is not running.</strong> Open your Start app shortcut (or relaunch
      Shortlistr), then refresh this page. Stats and actions will work again once it is online.
    </div>
  );
}
