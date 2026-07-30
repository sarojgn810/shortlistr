"use client";

import { useParams, useRouter } from "next/navigation";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { PrepDetailPanel } from "@/src/components/prep/PrepDetailPanel";
import { Button } from "@/src/components/ui/Button";

export default function PrepJobPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = String(params.jobId || "");

  return (
    <DashboardShell title="Application prep" breadcrumbs={["Home", "Prep", jobId.slice(0, 8)]}>
      <div className="mb-6">
        <Button variant="ghost" onClick={() => router.push("/prep")}>
          ← All prep
        </Button>
      </div>
      {jobId ? <PrepDetailPanel jobId={jobId} showActions /> : null}
    </DashboardShell>
  );
}
