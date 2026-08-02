"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { NAV_GROUPS, NAV_SYSTEM, type NavItem } from "@/src/config/navigation";


function isNavActive(pathname: string | null, item: NavItem): boolean {
  if (!pathname) return false;
  if (pathname === item.href) return true;
  if (item.exact) return false;
  return item.href !== "/" && pathname.startsWith(item.href + "/");
}

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const isActive = isNavActive(pathname, item);
  return (
    <Link href={item.href}>
      <div
        className={clsx(
          "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-base font-medium transition-all duration-200 active:scale-95",
          isActive
            ? "bg-ink text-lime"
            : "text-stone hover:bg-mist hover:text-ink"
        )}
      >
        <item.icon size={18} strokeWidth={isActive ? 2.5 : 1.75} className="shrink-0" />
        <span className="leading-none">{item.label}</span>
      </div>
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop left sidebar */}
      <aside className="fixed left-0 top-0 z-50 hidden h-screen w-56 flex-col border-r border-mist bg-white md:flex">
        {/* Logo */}
        <div className="flex items-center gap-2.5 border-b border-mist px-4 py-4">
          {/* The square icon, not the wordmark: the wordmark is 2:1 and needs
              ~160px to stay legible, which is most of a 224px sidebar. The icon
              is drawn to work small. */}
          <Image
            src="/icon-mark.png"
            alt=""
            width={28}
            height={28}
            priority
            className="h-7 w-7 shrink-0"
          />
          <span className="text-base font-bold tracking-tight text-ink">shortlistr</span>
        </div>

        {/* Nav groups */}
        <nav className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="mb-1.5 px-3 text-xs font-bold uppercase tracking-widest text-stone/50">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink key={item.href} item={item} pathname={pathname} />
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* System — pinned to bottom */}
        <div className="border-t border-mist px-3 py-3">
          <p className="mb-1.5 px-3 text-xs font-bold uppercase tracking-widest text-stone/50">
            System
          </p>
          <div className="space-y-0.5">
            {NAV_SYSTEM.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} />
            ))}
          </div>
          <a
            href="https://www.sarojnayak.com"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 block px-3 text-[11px] text-stone/40 transition-colors hover:text-stone"
          >
            sarojnayak.com
          </a>
        </div>
      </aside>

      {/* Mobile bottom bar — horizontally scrollable so items stay tappable
          instead of being crushed once the nav grows past ~6 entries. */}
      <nav className="fixed bottom-0 left-0 z-50 flex w-full snap-x flex-row items-center gap-1 overflow-x-auto border-t border-mist/50 bg-white/90 px-2 py-3 backdrop-blur-md md:hidden">
        {[...NAV_GROUPS.flatMap((g) => g.items), ...NAV_SYSTEM].map((item) => {
          const isActive = isNavActive(pathname, item);
          return (
            <Link key={item.href} href={item.href} className="shrink-0 snap-start">
              <div
                className={clsx(
                  "flex w-16 flex-col items-center gap-1 rounded-xl p-2 transition-all",
                  isActive ? "text-ink" : "text-stone/40"
                )}
              >
                <item.icon size={22} strokeWidth={isActive ? 2.5 : 1.75} />
                <span className="text-[11px] font-bold uppercase tracking-wide">
                  {item.label}
                </span>
              </div>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
