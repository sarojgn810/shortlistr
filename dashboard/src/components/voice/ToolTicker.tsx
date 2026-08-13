"use client";

import { Wrench } from "lucide-react";

/** What the agent actually ran. Spoken answers hide their work; this shows it. */
export function ToolTicker({ tools }: { tools: string[] }) {
  if (!tools.length) return null;

  return (
    <div className="rounded-2xl border border-mist bg-white p-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-stone/60">
        <Wrench size={12} /> Recent actions
      </p>
      <ul className="space-y-1">
        {tools.map((tool, i) => (
          <li
            key={`${tool}-${i}`}
            className={`truncate font-mono text-xs ${i === 0 ? "text-ink" : "text-stone/70"}`}
          >
            {tool.replace(/^shortlistr\./, "")}
          </li>
        ))}
      </ul>
    </div>
  );
}
