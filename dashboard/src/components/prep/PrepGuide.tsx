"use client";

import type { ReactNode } from "react";

function renderInline(text: string): ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

/** Minimal, dependency-free renderer for the interview-prep markdown guide. */
export function PrepGuide({ markdown }: { markdown: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="my-2 list-disc space-y-1.5 pl-5 text-base text-ink">
          {bullets.map((li, i) => (
            <li key={i}>{renderInline(li)}</li>
          ))}
        </ul>
      );
      bullets = [];
    }
  };

  for (const raw of markdown.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flush();
      continue;
    }
    if (line.startsWith("### ")) {
      flush();
      blocks.push(
        <h5 key={`h5-${blocks.length}`} className="mt-3 mb-1 text-base font-bold text-ink">
          {line.slice(4)}
        </h5>
      );
    } else if (line.startsWith("## ")) {
      flush();
      blocks.push(
        <h4 key={`h4-${blocks.length}`} className="mt-4 mb-1.5 text-sm font-bold text-stone">
          {line.slice(3)}
        </h4>
      );
    } else if (line.startsWith("# ")) {
      flush();
      blocks.push(
        <h3 key={`h3-${blocks.length}`} className="mt-4 mb-2 text-lg font-bold text-ink">
          {line.slice(2)}
        </h3>
      );
    } else {
      const m = line.match(/^[-*]\s+(.*)$/);
      if (m) {
        bullets.push(m[1]);
      } else {
        flush();
        blocks.push(
          <p key={`p-${blocks.length}`} className="my-1.5 text-base leading-relaxed text-ink">
            {renderInline(line)}
          </p>
        );
      }
    }
  }
  flush();

  return <div className="max-h-[600px] overflow-y-auto pr-2">{blocks}</div>;
}
