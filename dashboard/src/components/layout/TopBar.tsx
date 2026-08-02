"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Search, ShieldCheck } from "lucide-react";
import clsx from "clsx";
import { usePipelineSearch, useInitPipelineSearchFromUrl } from "@/src/hooks/usePipelineSearch";
import { useApiStatus } from "@/src/hooks/useApiStatus";

const CRUMB_HREFS: Record<string, string> = {
  Home: "/dashboard",
  Today: "/dashboard",
  Discover: "/inbox",
  Pipeline: "/pipeline",
  Reports: "/reports",
  Resume: "/cv",
  Profile: "/profile",
  Connections: "/connections",
  Settings: "/settings",
  Apply: "/apply",
  Prep: "/prep",
  Tracker: "/pipeline",
};

interface TopBarProps {
  title?: string;
  breadcrumbs?: string[];
}

export default function TopBar({ title = "Dashboard", breadcrumbs = ["Home"] }: TopBarProps) {
  const { online, pendingCount, refreshPendingCount } = useApiStatus();
  const { query, setQuery } = usePipelineSearch();
  useInitPipelineSearchFromUrl();

  // The bar renders on every page, so it fetches its own number. Relying on
  // whichever page happened to set the store left Settings, Profile, Reports and
  // Resume showing "0 pending review", or a stale count carried over from the
  // last page that did populate it.
  useEffect(() => {
    void refreshPendingCount();
  }, [refreshPendingCount]);

  return (
    <header className="flex flex-col justify-between gap-4 px-1 py-6 md:flex-row md:items-center">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-stone">
          <div className="flex items-center gap-2">
            {breadcrumbs.map((crumb, index) => {
              const isLast = index === breadcrumbs.length - 1;
              const href = CRUMB_HREFS[crumb];
              return (
                <div key={index} className="flex items-center gap-1">
                  {isLast || !href ? (
                    <span className={clsx("transition-colors", isLast ? "font-medium text-ink" : "font-normal opacity-40")}>
                      {crumb}
                    </span>
                  ) : (
                    <Link
                      href={href}
                      className="font-normal opacity-40 transition-opacity hover:opacity-70"
                    >
                      {crumb}
                    </Link>
                  )}
                  {!isLast && <span className="opacity-20">›</span>}
                </div>
              );
            })}
          </div>
          <span className="h-1 w-1 rounded-full bg-stone/50" />
          <span className="flex items-center gap-2 rounded-full border border-lime/40 bg-lime/10 px-3 py-1 font-medium text-lime-ink shadow-inner">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-lime shadow-[0_0_8px_#DFFF5E]" />
            {pendingCount} pending review
          </span>
        </div>
        <div className="flex items-center gap-4">
          <h1 className="text-4xl font-normal tracking-tighter text-ink md:text-5xl">{title}</h1>
          <span className="rounded-lg border border-lime/50 bg-black px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-lime">
            {online === false ? "OFFLINE" : "API"}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3 md:gap-4">
        <label className="relative hidden w-72 md:block">
          <Search
            size={18}
            className="pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 text-stone/40"
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              title === "Discover"
                ? "Search jobs…"
                : title === "Pipeline" || title === "Apply"
                  ? "Search pipeline…"
                  : "Search…"
            }
            className="w-full rounded-[24px] border border-stone/5 bg-white py-4 pl-14 pr-6 text-base font-medium text-ink shadow-[0_4px_20px_rgba(0,0,0,0.03)] outline-none transition-all placeholder:text-stone/50 focus:border-lime/40"
          />
        </label>
        <div
          className={clsx(
            "flex h-12 w-12 items-center justify-center rounded-full shadow-md",
            online === false ? "bg-orange/20 text-orange" : "bg-white text-ink"
          )}
          title={online === false ? "API offline" : "API connected"}
        >
          <ShieldCheck size={20} />
        </div>
      </div>
    </header>
  );
}
