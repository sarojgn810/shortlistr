"use client";

import DashboardShell from "@/src/components/layout/DashboardShell";
import { CvWorkspace } from "@/src/components/cv/CvWorkspace";

export default function CvPage() {
  return (
    <DashboardShell title="Resume" breadcrumbs={["Home", "Resume"]}>
      <p className="mb-6 text-base leading-relaxed text-stone">
        View, edit, and download your resume. Pick an ATS-friendly template and regenerate anytime.
      </p>
      <CvWorkspace />
    </DashboardShell>
  );
}
