"use client";

import { useEffect, useState } from "react";
import { api } from "@/src/lib/api/client";
import { cn } from "@/src/lib/utils/cn";

interface CvPdfPreviewProps {
  /** Bump to refetch after a regenerate. */
  version: number;
  enabled: boolean;
  className?: string;
}

/**
 * The compiled PDF, shown exactly as an employer will receive it.
 *
 * The HTML preview next to this is a different renderer with its own
 * stylesheet, so it can only ever approximate the LaTeX output — which is why
 * "it looked fine in the preview" was not worth much. This is the file.
 */
export function CvPdfPreview({ version, enabled, className }: CvPdfPreviewProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setUrl(null);
      return;
    }
    let revoked: string | null = null;
    let cancelled = false;
    setError(null);
    api
      .cvPdfObjectUrl()
      .then((objectUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        revoked = objectUrl;
        setUrl(objectUrl);
      })
      .catch(() => !cancelled && setError("Generate your resume to see the PDF."));
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [enabled, version]);

  const shell = cn(
    "flex items-center justify-center rounded-2xl border border-mist bg-mist p-3 text-center text-sm text-stone sm:p-5",
    className
  );

  if (!enabled || error) {
    return (
      <div className={cn(shell, "aspect-[210/297] w-full max-w-[520px] mx-auto")}>
        {error ?? "Generate your resume to see the PDF."}
      </div>
    );
  }

  if (!url) {
    return (
      <div className={cn(shell, "aspect-[210/297] w-full max-w-[520px] mx-auto")}>
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-lime border-t-transparent" />
      </div>
    );
  }

  return (
    <div className={cn("flex justify-center rounded-2xl border border-mist bg-mist p-3 sm:p-5", className)}>
      <iframe
        title="Resume PDF"
        src={`${url}#toolbar=0&navpanes=0&view=FitH`}
        className="h-[min(80vh,720px)] w-full max-w-[520px] border-0 bg-white shadow-lg"
      />
    </div>
  );
}
