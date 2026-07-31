"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Save, X } from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { CityCombobox } from "@/src/components/ui/CityCombobox";
import { useProfile } from "@/src/hooks/useProfile";
import { ApiError } from "@/src/lib/api/client";

// ─── Shared primitives ────────────────────────────────────────────────────────

/**
 * One saved value, label above it.
 *
 * Label left / value flush right reads fine in a narrow card, but these cards
 * now span the window — so "Phone" sat a thousand pixels away from the number
 * it belonged to. Stacking keeps the pair together at any width, and lets the
 * rows tile into `ReadGrid` columns instead of leaving the right side empty.
 */
function Row({ label, value }: { label: string; value?: string | number | null }) {
  const filled = value != null && value !== "" && value !== 0;
  return (
    <div className="min-w-0 border-b border-mist/60 py-3">
      <dt className="text-sm text-stone">{label}</dt>
      <dd className="mt-1 break-words text-base font-medium text-ink">
        {filled ? value : <span className="text-stone/40">—</span>}
      </dd>
    </div>
  );
}

function ReadGrid({ children }: { children: React.ReactNode }) {
  return <dl className="grid gap-x-10 sm:grid-cols-2 xl:grid-cols-3">{children}</dl>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-semibold text-ink">{label}</label>
      {children}
    </div>
  );
}

function TextInput({ value, onChange, type = "text", placeholder }: {
  value: string | number;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full rounded-xl border border-mist bg-white px-3.5 py-2.5 text-base text-ink outline-none transition-colors focus:border-lime/60 placeholder:text-stone/40"
    />
  );
}

function TextArea({ value, onChange, placeholder, rows = 3 }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full rounded-xl border border-mist bg-white px-3.5 py-2.5 text-base text-ink outline-none transition-colors focus:border-lime/60 placeholder:text-stone/40"
    />
  );
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({
  title, editing, onEdit, onCancel, onSave, saving, children,
}: {
  title: string;
  editing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  saving?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card padding="lg" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-bold text-ink">{title}</h2>
        {!editing ? (
          <button type="button" onClick={onEdit}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-bold text-stone transition-colors hover:bg-mist hover:text-ink">
            <Pencil size={14} /> Edit
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onCancel}><X size={13} /> Cancel</Button>
            <Button variant="lime" size="sm" onClick={onSave} isLoading={saving}><Save size={13} /> Save</Button>
          </div>
        )}
      </div>
      {children}
    </Card>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

type Draft = Record<string, string | number | boolean | string[]>;

export default function ProfilePage() {
  const { profile, isSaving, save } = useProfile();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({});

  const startEdit = (section: string) => {
    if (!profile) return;
    setDraft({
      name: profile.name ?? "",
      email: profile.email ?? "",
      phone: profile.phone ?? "",
      location: profile.location ?? "",
      linkedin: profile.linkedin ?? "",
      github: profile.github ?? "",
      years_exp: profile.years_exp ?? 0,
      min_salary_inr_lpa: profile.min_salary_inr_lpa ?? 0,
      min_salary_usd: profile.min_salary_usd ?? 0,
      salary_unlisted: profile.salary_unlisted ?? "include",
      target_titles: (profile.target_titles ?? []).join(", "),
      preferred_locations: profile.preferred_locations ?? [],
      min_fit_score: profile.min_fit_score ?? 60,
      website: profile.website ?? "",
      notice_period: profile.notice_period ?? "",
      current_ctc: profile.current_ctc ?? "",
      expected_ctc: profile.expected_ctc ?? "",
      how_heard: profile.how_heard ?? "",
      work_authorization: profile.work_authorization ?? "",
      preferred_name: profile.preferred_name ?? "",
      cover_letter_snippet: profile.cover_letter_snippet ?? "",
      willing_to_relocate: profile.willing_to_relocate ?? "",
    });
    setEditing(section);
  };

  const cancelEdit = () => { setEditing(null); setDraft({}); };

  const commitEdit = async () => {
    try {
      const updates: Draft = { ...draft };
      if (typeof draft.target_titles === "string") {
        (updates as Record<string, unknown>).target_titles = draft.target_titles
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
      }
      await save(updates as Parameters<typeof save>[0]);
      setEditing(null);
      setDraft({});
      toast.success("Saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed");
    }
  };

  const set = (k: string, v: string | number | boolean | string[]) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <DashboardShell title="Profile" breadcrumbs={["Home", "Profile"]}>
      <div className="w-full space-y-6">

        {/* ── Personal Info ──────────────────────────────────────────── */}
        <Section title="Personal Info"
          editing={editing === "info"}
          onEdit={() => startEdit("info")}
          onCancel={cancelEdit}
          onSave={commitEdit}
          saving={isSaving}
        >
          {editing === "info" ? (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              <Field label="Full name"><TextInput value={String(draft.name ?? "")} onChange={(v) => set("name", v)} /></Field>

              <Field label="Email"><TextInput value={String(draft.email ?? "")} onChange={(v) => set("email", v)} type="email" /></Field>
              <Field label="Phone"><TextInput value={String(draft.phone ?? "")} onChange={(v) => set("phone", v)} /></Field>
              <Field label="Location"><TextInput value={String(draft.location ?? "")} onChange={(v) => set("location", v)} placeholder="City, Country" /></Field>
              <Field label="LinkedIn URL"><TextInput value={String(draft.linkedin ?? "")} onChange={(v) => set("linkedin", v)} /></Field>
              <Field label="GitHub URL"><TextInput value={String(draft.github ?? "")} onChange={(v) => set("github", v)} /></Field>
              <Field label="Years of experience"><TextInput value={Number(draft.years_exp ?? 0)} onChange={(v) => set("years_exp", Number(v))} type="number" /></Field>
            </div>
          ) : (
            <ReadGrid>
              <Row label="Name" value={profile?.name} />
              <Row label="Email" value={profile?.email} />
              <Row label="Phone" value={profile?.phone} />
              <Row label="Location" value={profile?.location} />
              <Row label="LinkedIn" value={profile?.linkedin} />
              <Row label="GitHub" value={profile?.github} />
              <Row label="Experience" value={profile?.years_exp ? `${profile.years_exp} years` : null} />
            </ReadGrid>
          )}
        </Section>

        {/* ── Job Targeting ──────────────────────────────────────────── */}
        <Section title="Job Targeting"
          editing={editing === "targeting"}
          onEdit={() => startEdit("targeting")}
          onCancel={cancelEdit}
          onSave={commitEdit}
          saving={isSaving}
        >
          {editing === "targeting" ? (
            <div className="space-y-4">
              <Field label="Target job titles (comma-separated)">
                <TextInput value={String(draft.target_titles ?? "")} onChange={(v) => set("target_titles", v)} placeholder="Software Engineer, Staff Engineer" />
              </Field>
              <Field label="Preferred locations">
                <CityCombobox
                  selected={Array.isArray(draft.preferred_locations) ? draft.preferred_locations as string[] : []}
                  onChange={(cities) => set("preferred_locations", cities)}
                  placeholder="Type a city name…"
                />
                <p className="mt-1.5 text-sm text-stone">
                  Discovery filters jobs to these cities. Add{" "}
                  <span className="text-ink">Remote (India)</span> (or another
                  country) for remote roles in that region — bare{" "}
                  <span className="text-ink">Remote</span> alone means worldwide.
                  Leave empty for no location restriction.
                </p>
              </Field>
              <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                <Field label="Min salary (INR LPA)"><TextInput value={Number(draft.min_salary_inr_lpa ?? 0)} onChange={(v) => set("min_salary_inr_lpa", Number(v))} type="number" /></Field>
                <Field label="Min salary (USD/yr)"><TextInput value={Number(draft.min_salary_usd ?? 0)} onChange={(v) => set("min_salary_usd", Number(v))} type="number" /></Field>
              </div>
              <Field label="Unlisted salary">
                <div className="flex gap-2">
                  {[["include", "Include"], ["skip", "Skip"]].map(([val, lbl]) => (
                    <button key={val} type="button" onClick={() => set("salary_unlisted", val)}
                      className={`rounded-lg px-4 py-2 text-sm font-bold transition-colors ${draft.salary_unlisted === val ? "bg-ink text-lime" : "border border-mist text-stone hover:border-stone/40"}`}>
                      {lbl}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label={`Min fit score: ${draft.min_fit_score ?? 60}`}>
                <input type="range" min={0} max={100} step={5} value={Number(draft.min_fit_score ?? 60)}
                  onChange={(e) => set("min_fit_score", Number(e.target.value))}
                  className="w-full accent-lime-500" />
              </Field>
            </div>
          ) : (
            <ReadGrid>
              <div className="min-w-0 border-b border-mist/60 py-3 sm:col-span-2 xl:col-span-3">
                <dt className="text-sm text-stone">Titles</dt>
                <dd className="mt-2 flex flex-wrap gap-1.5">
                  {(profile?.target_titles ?? []).length > 0
                    ? profile?.target_titles.map((t, i) => (
                        <span key={`${t}-${i}`} className="rounded-full bg-ink/5 px-3 py-1 text-sm font-medium text-ink">{t}</span>
                      ))
                    : <span className="text-sm text-stone/40">No titles set</span>}
                </dd>
              </div>
              <div className="min-w-0 border-b border-mist/60 py-3 sm:col-span-2 xl:col-span-3">
                <dt className="text-sm text-stone">Preferred locations</dt>
                <dd className="mt-2 flex flex-wrap gap-1.5">
                  {(profile?.preferred_locations ?? []).length > 0
                    ? profile?.preferred_locations.map((loc, i) => (
                        <span key={`${loc}-${i}`} className="rounded-full bg-ink/5 px-3 py-1 text-sm font-medium text-ink">{loc}</span>
                      ))
                    : <span className="text-sm text-stone/40">All locations</span>}
                </dd>
              </div>
              <Row label="Min salary (INR)" value={profile?.min_salary_inr_lpa ? `${profile.min_salary_inr_lpa} LPA` : null} />
              <Row label="Min salary (USD)" value={profile?.min_salary_usd ? `$${profile.min_salary_usd.toLocaleString()}` : null} />
              <Row label="Min fit score" value={profile?.min_fit_score ? `${profile.min_fit_score}` : null} />
            </ReadGrid>
          )}
        </Section>

        {/* ── Application Auto-Fill ──────────────────────────────────── */}
        <Section title="Application Auto-Fill"
          editing={editing === "autofill"}
          onEdit={() => startEdit("autofill")}
          onCancel={cancelEdit}
          onSave={commitEdit}
          saving={isSaving}
        >
          <p className="text-sm leading-relaxed text-stone">
            Used to pre-fill application forms in the browser. Nothing is ever submitted
            automatically — you review and click Submit yourself. Your contact details from
            Personal Info are filled in too.
          </p>
          {editing === "autofill" ? (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              <Field label="Portfolio / website"><TextInput value={String(draft.website ?? "")} onChange={(v) => set("website", v)} placeholder="https://…" /></Field>
              <Field label="Preferred name"><TextInput value={String(draft.preferred_name ?? "")} onChange={(v) => set("preferred_name", v)} placeholder="What you go by" /></Field>
              <Field label="Notice period"><TextInput value={String(draft.notice_period ?? "")} onChange={(v) => set("notice_period", v)} placeholder="30 days / Immediate" /></Field>
              <Field label="Current CTC"><TextInput value={String(draft.current_ctc ?? "")} onChange={(v) => set("current_ctc", v)} placeholder="40 LPA" /></Field>
              <Field label="Expected CTC"><TextInput value={String(draft.expected_ctc ?? "")} onChange={(v) => set("expected_ctc", v)} placeholder="55 LPA" /></Field>
              <Field label="How did you hear about us"><TextInput value={String(draft.how_heard ?? "")} onChange={(v) => set("how_heard", v)} placeholder="LinkedIn" /></Field>
              <Field label="Work authorization">
                <TextInput
                  value={String(draft.work_authorization ?? "")}
                  onChange={(v) => set("work_authorization", v)}
                  placeholder="Authorized to work in India; no sponsorship needed"
                />
              </Field>
              <Field label="Willing to relocate">
                <TextInput
                  value={String(draft.willing_to_relocate ?? "")}
                  onChange={(v) => set("willing_to_relocate", v)}
                  placeholder="Yes / No / Open to discussion"
                />
              </Field>
              <div className="sm:col-span-2 xl:col-span-3">
                <Field label="Cover letter / “Why this role?” snippet">
                  <TextArea
                    value={String(draft.cover_letter_snippet ?? "")}
                    onChange={(v) => set("cover_letter_snippet", v)}
                    placeholder="2–4 sentences apply-assist pastes into cover-letter / motivation textareas"
                    rows={4}
                  />
                </Field>
              </div>
            </div>
          ) : (
            <ReadGrid>
              <Row label="Website" value={profile?.website} />
              <Row label="Preferred name" value={profile?.preferred_name} />
              <Row label="Notice period" value={profile?.notice_period} />
              <Row label="Current CTC" value={profile?.current_ctc} />
              <Row label="Expected CTC" value={profile?.expected_ctc} />
              <Row label="How heard" value={profile?.how_heard} />
              <Row label="Work authorization" value={profile?.work_authorization} />
              <Row label="Willing to relocate" value={profile?.willing_to_relocate} />
              <div className="min-w-0 border-b border-mist/60 py-3 sm:col-span-2 xl:col-span-3">
                <dt className="text-sm text-stone">Cover letter snippet</dt>
                <dd className="mt-1 max-w-3xl whitespace-pre-line break-words text-base font-medium leading-relaxed text-ink">
                  {profile?.cover_letter_snippet || <span className="text-stone/40">—</span>}
                </dd>
              </div>
            </ReadGrid>
          )}
        </Section>

      </div>
    </DashboardShell>
  );
}
