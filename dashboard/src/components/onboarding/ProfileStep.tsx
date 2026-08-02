"use client";

import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { ResumeUploadZone } from "@/src/components/cv/ResumeUploadZone";
import { api, ApiError, type CvUploadResult, type ProfileSetup } from "@/src/lib/api/client";
import { ArrowRight, Sparkles } from "lucide-react";

const inputClass =
  "w-full rounded-2xl border border-mist bg-white px-4 py-2.5 text-sm text-ink outline-none focus:border-lime/40 disabled:opacity-50";

const LLM_OPTIONS = [
  { value: "auto", label: "Auto — your key first, then Local AI (recommended)" },
  { value: "gemini", label: "Google Gemini — free tier, no card" },
  { value: "groq", label: "Groq — free tier, fastest" },
  { value: "openai", label: "OpenAI (GPT-4o)" },
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "grok", label: "xAI Grok" },
  { value: "ollama", label: "Ollama — advanced, runs on this computer" },
  { value: "none", label: "None — keyword scoring only" },
] as const;

interface ProfileStepProps {
  initial: ProfileSetup | null;
  loading: boolean;
  onSave: (data: ProfileSetup & { llm_api_key?: string }) => Promise<void>;
  /** Called after a résumé is uploaded here so the parent can carry it to the
   *  Resume step (mark as uploaded, seed extracted markdown + ATS). */
  onResumeUploaded?: (result: CvUploadResult) => void;
}

export function ProfileStep({ initial, loading, onSave, onResumeUploaded }: ProfileStepProps) {
  const [form, setForm] = useState<ProfileSetup>(() => ({
    exists: false,
    name: "",
    email: "",
    phone: "",
    location: "",
    linkedin: "",
    github: "",
    years_exp: 0,
    min_salary_inr_lpa: 0,
    min_salary_usd: 0,
    salary_unlisted: "include",
    target_titles: [],
    preferred_locations: [],
    min_fit_score: 40,
    // "auto", not "none". Onboarding defaulting to "none" wrote provider: none
    // into every fresh profile, and get_llm() returns nothing for "none" — so a
    // user who later added a key or set up Local AI still saw "Basic score" on
    // every card, with nothing on screen explaining why.
    llm_provider: "auto",
    llm_model: "",
    llm_api_key_set: false,
    website: "",
    notice_period: "",
    current_ctc: "",
    expected_ctc: "",
    how_heard: "",
    work_authorization: "",
    preferred_name: "",
    cover_letter_snippet: "",
    willing_to_relocate: "",
    ...initial,
  }));
  const [titlesText, setTitlesText] = useState(
    () => (initial?.target_titles || []).join(", ")
  );
  const [locationsText, setLocationsText] = useState(
    () => (initial?.preferred_locations || []).join(", ")
  );
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [autofilled, setAutofilled] = useState<string[]>([]);

  const set = <K extends keyof ProfileSetup>(key: K, value: ProfileSetup[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Upload a résumé and pre-fill the form from whatever we could extract.
  const handleResumeAutofill = async (file: File) => {
    try {
      const res = await api.uploadCv(file);
      const p = res.profile || {};
      const filled: string[] = [];
      setForm((f) => {
        const next = { ...f };
        if (p.name) { next.name = p.name; filled.push("name"); }
        if (p.email) { next.email = p.email; filled.push("email"); }
        if (p.phone) { next.phone = p.phone; filled.push("phone"); }
        if (p.location) { next.location = p.location; filled.push("location"); }
        if (p.linkedin) { next.linkedin = p.linkedin; filled.push("LinkedIn"); }
        if (p.github) { next.github = p.github; filled.push("GitHub"); }
        if (typeof p.years_exp === "number" && p.years_exp > 0) {
          next.years_exp = p.years_exp;
          filled.push("experience");
        }
        return next;
      });
      if (p.preferred_locations?.length) {
        // Seed only if empty so we never clobber locations the user typed.
        setLocationsText((cur) => (cur.trim() ? cur : p.preferred_locations!.join(", ")));
        filled.push("preferred locations");
      }
      if (p.target_titles?.length) {
        // Only seed titles if the user hasn't typed any yet — don't clobber.
        setTitlesText((cur) => (cur.trim() ? cur : p.target_titles!.join(", ")));
        filled.push("target titles");
      }
      setAutofilled(filled);
      onResumeUploaded?.(res);
      if (filled.length) {
        const targeting = res.applied_target_titles?.length
          ? ` Targeting updated to ${res.applied_target_titles.slice(0, 3).join(", ")}.`
          : "";
        toast.success(`Filled ${filled.length} field(s) from your résumé — review below.${targeting}`);
      } else {
        toast.message("Résumé uploaded — couldn't auto-detect fields, please fill them in.");
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed — is the API running?");
      throw e;
    }
  };

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const titles = titlesText
        .split(/[,;\n]/)
        .map((t) => t.trim())
        .filter(Boolean);
      const locations = locationsText
        .split(/[,;\n]/)
        .map((t) => t.trim())
        .filter(Boolean);
      await onSave({
        ...form,
        target_titles: titles,
        preferred_locations: locations,
        llm_api_key: apiKey || undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card padding="lg" className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-ink">About you</h2>
        <p className="mt-1 text-base text-stone">
          Name, targets, and optional LLM key — saved to{" "}
          <code className="text-ink">config/profile.yml</code> and{" "}
          <code className="text-ink">.env</code> on your machine.
        </p>
      </div>

      {/* Résumé auto-fill — extract details so the first job scan is targeted. */}
      <div className="rounded-2xl border border-lime/40 bg-lime/5 p-4 space-y-3">
        <div className="flex items-start gap-2">
          <Sparkles size={18} className="mt-0.5 shrink-0 text-lime-ink" />
          <div>
            <h3 className="font-bold text-ink">Have a résumé? Auto-fill from it</h3>
            <p className="text-base text-stone">
              Upload your résumé and we&apos;ll pre-fill your details and target titles —
              so the first job scan matches you instead of showing generic roles. We also
              keep it as your uploaded résumé for the next step. Everything is editable below.
            </p>
          </div>
        </div>
        <ResumeUploadZone disabled={loading} onUpload={handleResumeAutofill} />
        {autofilled.length > 0 && (
          <p className="text-sm font-semibold text-lime-ink">
            Auto-filled: {autofilled.join(", ")}. Review and adjust anything below.
          </p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name *" required>
          <input
            className={inputClass}
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            disabled={loading}
            placeholder="Your Name"
          />
        </Field>
        <Field label="Email *" required>
          <input
            type="email"
            className={inputClass}
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
            disabled={loading}
            placeholder="you@example.com"
          />
        </Field>
        <Field label="Phone">
          <input
            className={inputClass}
            value={form.phone}
            onChange={(e) => set("phone", e.target.value)}
            disabled={loading}
            placeholder="+1 555 0100"
          />
        </Field>
        <Field label="City / country">
          <input
            className={inputClass}
            value={form.location}
            onChange={(e) => set("location", e.target.value)}
            disabled={loading}
            placeholder="City, Country"
          />
        </Field>
        <Field label="LinkedIn">
          <input
            className={inputClass}
            value={form.linkedin}
            onChange={(e) => set("linkedin", e.target.value)}
            disabled={loading}
            placeholder="https://linkedin.com/in/you"
          />
        </Field>
        <Field label="GitHub">
          <input
            className={inputClass}
            value={form.github}
            onChange={(e) => set("github", e.target.value)}
            disabled={loading}
            placeholder="https://github.com/you"
          />
        </Field>
        <Field label="Years of experience">
          <input
            type="number"
            min={0}
            className={inputClass}
            value={form.years_exp || ""}
            onChange={(e) => set("years_exp", parseInt(e.target.value, 10) || 0)}
            disabled={loading}
          />
        </Field>
      </div>

      <Field label="Target job titles * (comma-separated)">
        <textarea
          className={`${inputClass} min-h-[72px]`}
          value={titlesText}
          onChange={(e) => setTitlesText(e.target.value)}
          disabled={loading}
          placeholder="Software Engineer, Product Manager"
        />
      </Field>

      <Field label="Search locations (comma-separated)">
        <textarea
          className={`${inputClass} min-h-[60px]`}
          value={locationsText}
          onChange={(e) => setLocationsText(e.target.value)}
          disabled={loading}
          placeholder="Remote, Berlin, San Francisco"
        />
        <span className="text-sm font-normal text-stone">
          Cities or &quot;Remote&quot;. The scan targets these locations.
          Example: <span className="font-mono">Bangalore, Remote</span>
        </span>
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Min salary (INR LPA, 0 = off)">
          <input
            type="number"
            min={0}
            className={inputClass}
            value={form.min_salary_inr_lpa || ""}
            onChange={(e) => set("min_salary_inr_lpa", parseInt(e.target.value, 10) || 0)}
            disabled={loading}
          />
        </Field>
        <Field label="Min salary (USD/year, 0 = off)">
          <input
            type="number"
            min={0}
            className={inputClass}
            value={form.min_salary_usd || ""}
            onChange={(e) => set("min_salary_usd", parseInt(e.target.value, 10) || 0)}
            disabled={loading}
          />
        </Field>
      </div>

      <div className="rounded-2xl border border-mist bg-white p-4 space-y-4">
        <div>
          <h3 className="font-bold text-ink">Application answers</h3>
          <p className="text-base text-stone">
            Apply-assist auto-fills these common ATS questions. Stored locally in{" "}
            <code className="text-ink">config/profile.yml</code> (gitignored).
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Personal website / portfolio">
            <input
              className={inputClass}
              value={form.website}
              onChange={(e) => set("website", e.target.value)}
              disabled={loading}
              placeholder="https://yoursite.dev"
            />
          </Field>
          <Field label="Notice period">
            <input
              className={inputClass}
              value={form.notice_period}
              onChange={(e) => set("notice_period", e.target.value)}
              disabled={loading}
              placeholder="30 days / Immediate"
            />
          </Field>
          <Field label="Current CTC">
            <input
              className={inputClass}
              value={form.current_ctc}
              onChange={(e) => set("current_ctc", e.target.value)}
              disabled={loading}
              placeholder="e.g. 40 LPA (fixed + variable)"
            />
          </Field>
          <Field label="Expected CTC">
            <input
              className={inputClass}
              value={form.expected_ctc}
              onChange={(e) => set("expected_ctc", e.target.value)}
              disabled={loading}
              placeholder="e.g. 55 LPA"
            />
          </Field>
          <Field label="How did you hear about this job?">
            <input
              className={inputClass}
              value={form.how_heard}
              onChange={(e) => set("how_heard", e.target.value)}
              disabled={loading}
              placeholder="Company website / LinkedIn / Referral"
            />
          </Field>
          <Field label="Preferred name">
            <input
              className={inputClass}
              value={form.preferred_name}
              onChange={(e) => set("preferred_name", e.target.value)}
              disabled={loading}
              placeholder="What you go by (if different)"
            />
          </Field>
          <Field label="Work authorization">
            <input
              className={inputClass}
              value={form.work_authorization}
              onChange={(e) => set("work_authorization", e.target.value)}
              disabled={loading}
              placeholder="Authorized to work in India; no sponsorship needed"
            />
          </Field>
          <Field label="Willing to relocate">
            <input
              className={inputClass}
              value={form.willing_to_relocate}
              onChange={(e) => set("willing_to_relocate", e.target.value)}
              disabled={loading}
              placeholder="Yes / No / Open to discussion"
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Cover letter / “Why this role?” snippet">
              <textarea
                className={inputClass}
                value={form.cover_letter_snippet}
                onChange={(e) => set("cover_letter_snippet", e.target.value)}
                disabled={loading}
                rows={3}
                placeholder="2–4 sentences pasted into motivation / cover-letter textareas"
              />
            </Field>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-mist bg-sage/20 p-4 space-y-4">
        <h3 className="font-bold text-ink">LLM (optional)</h3>
        <p className="text-base text-stone">
          Full A–G job scoring needs a provider <em>and</em> an API key. Without both,
          template mode still works.
        </p>
        {form.llm_api_key_set && form.llm_provider === "none" && (
          <div className="rounded-xl border border-orange/30 bg-orange/10 px-3.5 py-2.5 text-base text-ink space-y-2">
            <p>
              An API key is already saved on this machine, but no provider is selected —
              so LLM scoring is off.
              {initial?.suggested_provider
                ? ` Your key looks like ${initial.suggested_provider} — click below to use it, or pick manually.`
                : " Pick your provider below to turn it on."}
            </p>
            {initial?.suggested_provider && (
              <button
                type="button"
                onClick={() => set("llm_provider", initial.suggested_provider!)}
                className="rounded-lg bg-lime px-3 py-1 text-sm font-bold text-black hover:bg-lime/80"
              >
                Use {initial.suggested_provider}
              </button>
            )}
          </div>
        )}
        <Field label="Provider">
          <select
            className={inputClass}
            value={form.llm_provider}
            onChange={(e) => set("llm_provider", e.target.value)}
            disabled={loading}
          >
            {LLM_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        {form.llm_provider !== "none" && form.llm_provider !== "ollama" && form.llm_provider !== "auto" && (
          <>
            <Field label="Model (optional)">
              <input
                className={inputClass}
                value={form.llm_model}
                onChange={(e) => set("llm_model", e.target.value)}
                disabled={loading}
                placeholder={form.llm_provider === "openai" ? "gpt-4o" : "default"}
              />
            </Field>
            <Field
              label={
                form.llm_api_key_set
                  ? "API key (leave blank to keep existing)"
                  : "API key (stored in .env only)"
              }
            >
              <input
                type="password"
                className={inputClass}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                disabled={loading}
                autoComplete="off"
              />
            </Field>
          </>
        )}
      </div>

      <Button
        variant="lime"
        onClick={handleSubmit}
        isLoading={saving}
        disabled={loading || !form.name.trim() || !form.email.trim() || !titlesText.trim()}
      >
        Save and continue
        <ArrowRight size={18} />
      </Button>
    </Card>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-semibold text-ink">
        {label}
        {required ? " *" : ""}
      </span>
      {children}
    </label>
  );
}
