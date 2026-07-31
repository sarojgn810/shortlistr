"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Linkedin, Mail, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/src/components/ui/Button";
import { api, ApiError } from "@/src/lib/api/client";
import type { ReachOut, ReachOutContact } from "@/src/types/job";

interface ReachOutSectionProps {
  jobId: string;
  reachOut: ReachOut;
  onUpdated?: () => void;
}

export function ReachOutSection({ jobId, reachOut, onUpdated }: ReachOutSectionProps) {
  const [userContacts, setUserContacts] = useState<ReachOutContact[]>(() =>
    (reachOut.contacts || []).filter((c) => c.source === "user")
  );
  const [outreach, setOutreach] = useState(reachOut.outreach_draft || "");
  const [savingContacts, setSavingContacts] = useState(false);
  const [savingOutreach, setSavingOutreach] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    title: "",
    email: "",
    linkedin_url: "",
  });

  useEffect(() => {
    setUserContacts((reachOut.contacts || []).filter((c) => c.source === "user"));
    setOutreach(reachOut.outreach_draft || "");
  }, [reachOut]);

  const jdContacts = (reachOut.contacts || []).filter((c) => c.source !== "user");
  // Show JD + current user list (user may have added since last save load)
  const shown = [
    ...jdContacts,
    ...userContacts.filter(
      (u) =>
        !jdContacts.some(
          (j) =>
            (j.email && u.email && j.email.toLowerCase() === u.email.toLowerCase()) ||
            (j.linkedin_url &&
              u.linkedin_url &&
              j.linkedin_url.replace(/\/$/, "").toLowerCase() ===
                u.linkedin_url.replace(/\/$/, "").toLowerCase())
        )
    ),
  ];

  const handleAdd = () => {
    if (!draft.name.trim() && !draft.email.trim() && !draft.linkedin_url.trim()) {
      toast.error("Add a name, email, or LinkedIn URL");
      return;
    }
    const next: ReachOutContact = {
      id: `user-${Date.now()}`,
      name: draft.name.trim(),
      title: draft.title.trim(),
      email: draft.email.trim(),
      linkedin_url: draft.linkedin_url.trim(),
      note: "Added by you.",
      source: "user",
    };
    setUserContacts((prev) => [...prev, next]);
    setDraft({ name: "", title: "", email: "", linkedin_url: "" });
  };

  const handleRemove = (id: string) => {
    setUserContacts((prev) => prev.filter((c) => c.id !== id));
  };

  const handleSaveContacts = async () => {
    setSavingContacts(true);
    try {
      await api.savePrepReachOutContacts(jobId, userContacts);
      toast.success("Contacts saved");
      onUpdated?.();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save contacts");
    } finally {
      setSavingContacts(false);
    }
  };

  const handleSaveOutreach = async () => {
    setSavingOutreach(true);
    try {
      await api.savePrepOutreachDraft(jobId, outreach);
      toast.success("Outreach draft saved");
      onUpdated?.();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save outreach");
    } finally {
      setSavingOutreach(false);
    }
  };

  const copyOutreach = async () => {
    try {
      await navigator.clipboard.writeText(outreach);
      toast.success("Copied — paste into LinkedIn or email yourself");
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <div className="rounded-2xl border border-mist bg-white p-5">
      <h3 className="text-lg font-bold text-ink">Reach out</h3>
      <p className="mt-1 text-sm text-stone">
        {reachOut.disclaimer ||
          "Contacts from the job description, plus LinkedIn searches you open yourself."}
      </p>

      {shown.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {shown.map((c) => (
            <li
              key={c.id}
              className="rounded-xl border border-mist bg-sage/20 px-3 py-3 text-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-ink">
                    {c.name || c.email || "Contact"}
                    {c.title ? (
                      <span className="ml-2 font-normal text-stone">{c.title}</span>
                    ) : null}
                  </p>
                  {c.note ? <p className="mt-0.5 text-xs text-stone">{c.note}</p> : null}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {c.email ? (
                      <a
                        href={`mailto:${c.email}`}
                        className="inline-flex items-center gap-1 rounded-lg border border-mist bg-white px-2 py-1 text-xs font-semibold text-ink hover:bg-sage/40"
                      >
                        <Mail size={12} /> {c.email}
                      </a>
                    ) : null}
                    {c.linkedin_url ? (
                      <a
                        href={c.linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-lg border border-mist bg-white px-2 py-1 text-xs font-semibold text-ink hover:bg-sage/40"
                      >
                        <Linkedin size={12} /> LinkedIn
                      </a>
                    ) : c.name ? (
                      <a
                        href={`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(c.name)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-lg border border-mist bg-white px-2 py-1 text-xs font-semibold text-ink hover:bg-sage/40"
                      >
                        <Linkedin size={12} /> Find on LinkedIn
                      </a>
                    ) : null}
                  </div>
                </div>
                {c.source === "user" ? (
                  <button
                    type="button"
                    onClick={() => handleRemove(c.id)}
                    className="rounded-lg p-1.5 text-stone hover:bg-orange/10 hover:text-ink"
                    aria-label="Remove contact"
                  >
                    <Trash2 size={14} />
                  </button>
                ) : (
                  <span className="shrink-0 rounded bg-mist/60 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-ink/50">
                    JD
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-stone">
          No contact details in this posting yet. Use the LinkedIn searches below, or add someone
          you found.
        </p>
      )}

      {(reachOut.searches || []).length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-stone">
            Open on LinkedIn
          </p>
          <div className="flex flex-wrap gap-2">
            {reachOut.searches.map((s) => (
              <a
                key={s.url}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-xl border border-mist bg-sage/30 px-3 py-2 text-xs font-semibold text-ink hover:bg-sage/50"
              >
                {s.label} <ExternalLink size={12} />
              </a>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5 space-y-2 rounded-xl border border-dashed border-mist p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-stone">Add a contact</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <input
            value={draft.name}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            placeholder="Name"
            className="rounded-xl border border-mist bg-sage/20 px-3 py-2 text-sm text-ink outline-none focus:border-lime/40"
          />
          <input
            value={draft.title}
            onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
            placeholder="Title (optional)"
            className="rounded-xl border border-mist bg-sage/20 px-3 py-2 text-sm text-ink outline-none focus:border-lime/40"
          />
          <input
            value={draft.email}
            onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
            placeholder="Email"
            className="rounded-xl border border-mist bg-sage/20 px-3 py-2 text-sm text-ink outline-none focus:border-lime/40"
          />
          <input
            value={draft.linkedin_url}
            onChange={(e) => setDraft((d) => ({ ...d, linkedin_url: e.target.value }))}
            placeholder="https://linkedin.com/in/…"
            className="rounded-xl border border-mist bg-sage/20 px-3 py-2 text-sm text-ink outline-none focus:border-lime/40"
          />
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button variant="secondary" size="sm" onClick={handleAdd}>
            <Plus size={14} /> Add
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSaveContacts}
            isLoading={savingContacts}
          >
            Save contacts
          </Button>
        </div>
      </div>

      <div className="mt-5">
        <p className="mb-2 text-sm font-bold text-ink">Outreach draft</p>
        <p className="mb-2 text-xs text-stone">
          Copy into LinkedIn or email yourself — never auto-sent.
        </p>
        <textarea
          value={outreach}
          onChange={(e) => setOutreach(e.target.value)}
          rows={6}
          className="w-full rounded-2xl border border-mist bg-sage/20 p-4 text-sm leading-relaxed text-ink outline-none focus:border-lime/40"
        />
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={copyOutreach}>
            Copy
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSaveOutreach}
            isLoading={savingOutreach}
          >
            Save draft
          </Button>
        </div>
      </div>
    </div>
  );
}
