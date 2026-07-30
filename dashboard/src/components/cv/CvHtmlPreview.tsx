"use client";

import { cn } from "@/src/lib/utils/cn";

interface CvHtmlPreviewProps {
  html: string | null;
  loading?: boolean;
  className?: string;
  emptyMessage?: string;
}

/** A4 aspect ratio: 210 × 297 mm */
const A4_CLASS = "aspect-[210/297] w-full max-w-[520px]";

export function CvHtmlPreview({
  html,
  loading = false,
  className,
  emptyMessage = "Select a template to preview your resume.",
}: CvHtmlPreviewProps) {
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
        className={cn(
          A4_CLASS,
          "max-h-[min(80vh,720px)] border-0 bg-transparent shadow-lg"
        )}
        // allow-scripts only. The preview runs one script that measures and
        // shrinks its own content to fit the sheet; it never reaches the parent
        // document, storage or the network. Granting allow-same-origin as well
        // let the frame remove its own sandbox, which is what Chrome warns about
        // ("An iframe which has both allow-scripts and allow-same-origin ... can
        // escape its sandboxing") once per render.
        sandbox="allow-scripts"
      />
    </div>
  );
}
