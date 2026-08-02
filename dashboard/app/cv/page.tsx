"use client";

import DashboardShell from "@/src/components/layout/DashboardShell";
import { CvWorkspace } from "@/src/components/cv/CvWorkspace";

export default function CvPage() {
  return (
    <DashboardShell title="Resume" breadcrumbs={["Home", "Resume"]}>
      <div className="mb-6 max-w-3xl space-y-2">
        <p className="text-base leading-relaxed text-stone">
          Upload your file or build an ATS-safe PDF with an Shortlistr template. Edit the markdown,
          pick a length, then generate — the compiled PDF is what employers receive.
        </p>
      </div>
      <CvWorkspace />
    </DashboardShell>
  );
}
