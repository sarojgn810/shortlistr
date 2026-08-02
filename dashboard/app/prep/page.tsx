"use client";

import { Suspense } from "react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import PrepIndexClient from "./PrepIndexClient";

export default function PrepPage() {
  return (
    <Suspense
      fallback={
        <DashboardShell title="Prep" breadcrumbs={["Home", "Prep"]}>
          <p className="text-base text-stone">Loading prep…</p>
        </DashboardShell>
      }
    >
      <PrepIndexClient />
    </Suspense>
  );
}
