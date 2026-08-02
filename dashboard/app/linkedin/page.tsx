"use client";

import DashboardShell from "@/src/components/layout/DashboardShell";
import { LinkedInWorkspace } from "@/src/components/linkedin/LinkedInWorkspace";

export default function LinkedInOptimizerPage() {
  return (
    <DashboardShell title="LinkedIn" breadcrumbs={["Home", "LinkedIn"]}>
      <p className="mb-6 max-w-3xl text-base leading-relaxed text-stone">
        Optimize your LinkedIn from real résumé / profile content — score gaps,
        rewrite section by section, then copy into LinkedIn yourself. No invented
        employers or metrics.
      </p>
      <LinkedInWorkspace />
    </DashboardShell>
  );
}
