"use client";

import { useEffect, useState } from "react";
import { cn } from "@/src/lib/utils/cn";

interface CvHtmlPreviewProps {
  html: string | null;
  loading?: boolean;
  className?: string;
  emptyMessage?: string;
  /** Hint from page target: auto/2 allow a taller scrollable frame. */
  allowMultiPage?: boolean;
}

/** A4 aspect ratio: 210 × 297 mm */
const A4_CLASS = "aspect-[210/297] w-full max-w-[560px]";

export function CvHtmlPreview({
  html,
  loading = false,
  className,
  emptyMessage = "Select a template to preview your resume.",
  allowMultiPage = true,
}: CvHtmlPreviewProps) {
  const [pages, setPages] = useState(1);

  useEffect(() => {
    setPages(1);
    if (!html || !allowMultiPage) return;
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (
        data &&
        typeof data === "object" &&
        data.type === "cv-preview-pages" &&
        typeof data.pages === "number" &&
        data.pages >= 1
      ) {
        setPages(Math.min(4, Math.max(1, Math.round(data.pages))));
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [html, allowMultiPage]);

  if (loading) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-2xl border border-mist bg-mist p-6",
          A4_CLASS,
          "mx-auto max-h-[min(80vh,720px)]",
          className
        )}
      >
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-lime border-t-transparent" />
      </div>
    );
  }

  if (!html) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-2xl border border-dashed border-mist bg-mist/50 p-8 text-center text-sm text-stone",
          A4_CLASS,
          "mx-auto max-h-[min(80vh,720px)]",
          className
        )}
      >
        {emptyMessage}
      </div>
    );
  }

  const multi = allowMultiPage && pages > 1;
  // iframe height follows reported page count so page 2 is visible without
  // clipping; max height keeps the dashboard usable on short screens.
  const frameClass = multi
    ? "w-full max-w-[560px] overflow-auto border-0 bg-transparent shadow-lg"
    : cn(A4_CLASS, "max-h-[min(80vh,720px)] border-0 bg-transparent shadow-lg");
  const frameStyle = multi
    ? {
        height: `min(${Math.round(pages * 72)}vh, ${pages * 640}px)`,
        maxHeight: "min(92vh, 1400px)",
      }
    : undefined;

  return (
    <div
      className={cn(
        "flex justify-center rounded-2xl border border-mist bg-mist p-3 sm:p-5",
        className
      )}
    >
      <iframe
        title="Resume preview (A4)"
        srcDoc={html}
        style={frameStyle}
        className={frameClass}
        // allow-scripts only. The preview measures itself and may postMessage
        // page count to the parent; it never reaches storage or the network.
        sandbox="allow-scripts"
      />
    </div>
  );
}
