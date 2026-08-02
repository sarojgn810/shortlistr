"use client";

import { useEffect } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import AssistantDock from "./AssistantDock";
import { OfflineBanner } from "./OfflineBanner";
import { api } from "@/src/lib/api/client";
import { useApiStatusStore } from "@/src/hooks/useApiStatus";

interface DashboardShellProps {
  children: React.ReactNode;
  title: string;
  breadcrumbs?: string[];
  className?: string;
}

export default function DashboardShell({
  children,
  title,
  breadcrumbs,
  className = "",
}: DashboardShellProps) {
  // Single source of truth for API reachability. Per-page data hooks only set
  // `online` on the pages that mount them (jobs/applications), so pages like
  // tracker, cv, reports and settings used to show a false "API offline"
  // banner. Poll /health here since the shell wraps every page.
  const setOnline = useApiStatusStore((s) => s.setOnline);
  useEffect(() => {
    let active = true;
    const ping = () =>
      api
        .health()
        .then(() => active && setOnline(true))
        .catch(() => active && setOnline(false));
    ping();
    const id = setInterval(ping, 20000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [setOnline]);

  return (
    <main className="flex min-h-screen bg-sage font-sans tracking-tight text-ink">
      <Sidebar />
      <div
        className={`custom-scrollbar h-screen flex-1 overflow-y-auto px-4 pb-28 md:pl-60 md:pr-6 md:py-2 ${className}`}
      >
        <TopBar title={title} breadcrumbs={breadcrumbs} />
        <OfflineBanner />
        {children}
      </div>
      <AssistantDock />
    </main>
  );
}
