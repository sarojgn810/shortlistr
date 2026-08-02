"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Button } from "@/src/components/ui/Button";
import { api, ApiError } from "@/src/lib/api/client";
import { resolveApplyChannel } from "@/src/lib/applyChannel";

export default function ApplyRunnerPage() {
  const router = useRouter();
  const [queue, setQueue] = useState<string[]>([]);
  const [idx, setIdx] = useState(0);
  const [job, setJob] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Ask for approved rows specifically. Filtering an "evaluated" page down to
    // the approved ones meant the queue only ever saw approvals inside the
    // newest 100 rows.
    api.listJobs("approved").then((rows) => {
      const approved = rows.map((j) => String(j.id));
      setQueue(approved);
      if (!approved.length) setDone(true);
      setLoading(false);
    }).catch(() => {
      setDone(true);
      setLoading(false);
    });
  }, []);

  const [coverBody, setCoverBody] = useState("");
  const currentId = queue[idx];
  const channel = resolveApplyChannel(
    job
      ? {
          apply_channel: job.apply_channel as string | undefined,
          url: job.url as string | undefined,
          source: job.source as string | undefined,
        }
      : null
  );

  useEffect(() => {
    if (!currentId) return;
    setCoverBody("");
    api.getJob(currentId).then((j) => {
      setJob(j);
      if (j?.apply_channel === "email") {
        api
          .getPrep(currentId)
          .then((b) => setCoverBody(b.cover_letter?.body || ""))
          .catch(() => undefined);
      }
    }).catch(() => setJob(null));
  }, [currentId]);

  const advance = () => {
    if (idx + 1 >= queue.length) {
      setDone(true);
    } else {
      setIdx(idx + 1);
    }
  };

  const prefill = async () => {
    setBusy(true);
    const t = toast.message("Opening browser to pre-fill — up to 2 minutes…");
    try {
      await api.applyAssist(currentId, false);
      toast.dismiss(t);
      toast.success("Pre-filled — review & click Submit in the browser");
    } catch (e) {
      toast.dismiss(t);
      toast.error(e instanceof ApiError ? e.message : "Pre-fill failed");
    } finally {
      setBusy(false);
    }
  };

  const submitted = async () => {
    try {
      await api.markSubmitted(currentId);
      toast.success("Recorded as applied");
    } catch {
      /* non-fatal — still advance */
    }
    advance();
  };

  const sendEmail = async () => {
    setBusy(true);
    try {
      await api.sendApplication(currentId, coverBody, true);
      toast.success("Email sent — recorded as applied");
      advance();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DashboardShell title="Apply" breadcrumbs={["Home", "Apply"]}>
      <div className="w-full max-w-3xl">
        {loading ? (
          <div className="rounded-[28px] border border-mist bg-white p-8 text-center">
            <p className="text-base text-stone">Loading approved jobs…</p>
          </div>
        ) : done ? (
          <div className="rounded-[28px] border border-mist bg-white p-8 text-center">
            <p className="text-lg font-bold text-ink">All done</p>
            <p className="mt-2 text-base text-stone">
              {queue.length
                ? "You've worked through the batch."
                : "No approved jobs in the queue. Approve jobs from the inbox first — only approved jobs appear here."}
            </p>
            <div className="mt-4 flex justify-center gap-2">
              <Button variant="lime" onClick={() => router.push("/pipeline")}>
                View pipeline
              </Button>
              <Button variant="ghost" onClick={() => router.push("/inbox")}>
                Back to inbox
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-[28px] border border-mist bg-white p-6">
            <p className="text-sm font-bold text-stone">
              {idx + 1} of {queue.length}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <h2 className="text-xl font-bold text-ink">{(job?.title as string) || "Role"}</h2>
              <span className="rounded-full bg-mist px-2.5 py-1 text-xs font-bold uppercase tracking-widest text-stone">
                {channel === "email"
                  ? "Email"
                  : channel === "form"
                    ? "Form"
                    : channel === "link"
                      ? "Apply on site"
                      : "Manual"}
              </span>
            </div>
            <p className="text-base text-stone">{(job?.company as string) || "Company"}</p>

            {channel === "email" ? (
              <>
                <p className="mt-3 text-base text-stone">
                  Review the personalised cover letter, then send it (with your résumé) to{" "}
                  <span className="font-mono text-ink">{(job?.company_email as string) || "the company"}</span>.
                  Nothing is sent until you click Send.
                </p>
                <textarea
                  value={coverBody}
                  onChange={(e) => setCoverBody(e.target.value)}
                  rows={12}
                  className="mt-3 w-full rounded-2xl border border-mist bg-sage/20 p-4 text-base leading-relaxed text-ink outline-none focus:border-lime/40"
                />
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button variant="lime" isLoading={busy} onClick={sendEmail} disabled={!coverBody.trim()}>
                    Send email →
                  </Button>
                  <Button variant="ghost" onClick={advance}>
                    Skip
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="mt-3 text-base text-stone">
                  {channel === "link"
                    ? "This posting is on a job board (LinkedIn, Naukri and similar) — it has no form to pre-fill. Open it and apply on the site, then mark it here."
                    : "Prefill opens a browser and fills what it can — you still review, attach your CV if needed, and click Submit yourself. Nothing is submitted automatically."}
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {channel !== "link" && (
                    <Button variant="lime" isLoading={busy} onClick={prefill}>
                      Prefill form
                    </Button>
                  )}
                  {typeof job?.url === "string" && (
                    <a
                      href={job.url as string}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Button variant={channel === "link" ? "lime" : "secondary"}>
                        Open posting ↗
                      </Button>
                    </a>
                  )}
                  <Button variant="secondary" onClick={submitted} disabled={busy}>
                    I submitted it →
                  </Button>
                  <Button variant="ghost" onClick={advance} disabled={busy}>
                    Skip
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </DashboardShell>
  );
}
