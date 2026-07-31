"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { toast } from "sonner";
import {
  Check,
  Copy,
  Download,
  Loader2,
  RefreshCw,
  Sparkles,
  Wand2,
} from "lucide-react";
import {
  api,
  type LinkedInCoverTheme,
  type LinkedInOptimizerState,
  type LinkedInProfile,
  type LinkedInRewriteResult,
  type LinkedInScore,
} from "@/src/lib/api/client";
import { LINKEDIN_TABS, type LinkedInTabId } from "@/src/config/navigation";

const EMPTY_PROFILE: LinkedInProfile = {
  name: "",
  headline: "",
  about: "",
  experience: [],
  skills: [],
  featured: "",
  open_to_work: "",
  location: "",
  contact: "",
};

const DIM_LABELS: Record<string, string> = {
  keyword_match: "Keyword match",
  role_alignment: "Role alignment",
  quantification: "Quantification",
  clarity: "Clarity",
  impact: "Impact",
  completeness: "Completeness",
  consistency: "Consistency",
};

function scoreTone(n: number): string {
  if (n >= 75) return "text-ink bg-lime/60";
  if (n >= 50) return "text-ink bg-mist";
  return "text-orange bg-orange/10";
}

async function copyText(label: string, text: string) {
  if (!text.trim()) {
    toast.error(`Nothing to copy for ${label}`);
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`Copied ${label}`);
  } catch {
    toast.error("Clipboard unavailable");
  }
}

function DiffPanel({
  original,
  suggested,
  rationale,
  mode,
}: {
  original: string;
  suggested: string;
  rationale?: string;
  mode?: string;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-[28px] border border-mist bg-white/70 p-5">
          <p className="mb-2 text-xs font-bold uppercase tracking-widest text-stone/50">
            Before
          </p>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-stone">
            {original.trim() || "— empty —"}
          </pre>
        </div>
        <div className="rounded-[28px] border border-ink/10 bg-white p-5 shadow-sm">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-bold uppercase tracking-widest text-stone/50">
              After
            </p>
            <span className="rounded-full bg-mist px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-stone">
              {mode || "heuristic"}
            </span>
          </div>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink">
            {suggested.trim() || "— run rewrite —"}
          </pre>
        </div>
      </div>
      {rationale ? <p className="text-sm leading-relaxed text-stone">{rationale}</p> : null}
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  return (
    <div
      className={clsx(
        "flex h-28 w-28 flex-col items-center justify-center rounded-full border-4 border-ink/10",
        scoreTone(score)
      )}
    >
      <span className="text-3xl font-bold tracking-tight">{score}</span>
      <span className="text-[10px] font-bold uppercase tracking-widest opacity-70">/ 100</span>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-bold uppercase tracking-widest text-stone/50">
        {label}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-2xl border border-mist bg-sage/50 px-3 py-2 text-sm text-ink outline-none focus:border-ink/30"
      />
    </label>
  );
}

export function LinkedInWorkspace() {
  const [tab, setTab] = useState<LinkedInTabId>("overview");
  const [state, setState] = useState<LinkedInOptimizerState | null>(null);
  const [profile, setProfile] = useState<LinkedInProfile>(EMPTY_PROFILE);
  const [role, setRole] = useState("");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [paste, setPaste] = useState("");
  const [score, setScore] = useState<LinkedInScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [useLlm, setUseLlm] = useState(false);
  const [rewrites, setRewrites] = useState<Record<string, LinkedInRewriteResult>>({});
  const [coverTheme, setCoverTheme] = useState("ink_lime");
  const [coverSubline, setCoverSubline] = useState("Open to opportunities · Reliable systems");
  const [coverSvg, setCoverSvg] = useState("");
  const [themes, setThemes] = useState<LinkedInCoverTheme[]>([]);
  const [importNote, setImportNote] = useState<string | null>(null);
  const [source, setSource] = useState("");

  const applyImported = (out: {
    profile?: LinkedInProfile | null;
    score?: LinkedInScore;
    target_role?: string;
    linkedin_url?: string;
    source?: string;
    import_note?: string;
  }) => {
    if (out.profile) setProfile(out.profile);
    if (out.score) setScore(out.score);
    if (out.target_role) setRole(out.target_role);
    if (out.linkedin_url) setLinkedinUrl(out.linkedin_url);
    if (out.source) setSource(out.source);
    if (out.import_note) setImportNote(out.import_note);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await api.linkedInState();
      setState(s);
      setProfile(s.profile || EMPTY_PROFILE);
      setRole(s.target_role || "");
      setScore(s.score);
      setThemes(s.cover_themes || []);
      setLinkedinUrl(s.linkedin_url || s.profile?.linkedin_url || "");
      setSource(s.source || "");
      setImportNote(s.import_note || null);
      if (s.cover_themes?.[0]) setCoverTheme(s.cover_themes[0].id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load LinkedIn optimizer");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const substantial =
    Boolean(profile.about && profile.about.length > 80) &&
    ((profile.experience || []).some((j) => (j.bullets || []).length > 0) ||
      (profile.skills || []).length >= 5);

  const importFromCv = async () => {
    setBusy(true);
    try {
      const out = await api.linkedInImportCv(role);
      applyImported(out);
      toast.success("Imported & scored from résumé");
      setTab("overview");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "CV import failed");
    } finally {
      setBusy(false);
    }
  };

  const importFromUrl = async () => {
    setBusy(true);
    try {
      const out = await api.linkedInImportUrl(linkedinUrl || undefined, role);
      if (!out.ok) {
        toast.error(out.error || "LinkedIn fetch failed");
        setImportNote(out.error || null);
        if (out.cv_fallback_available) {
          toast.message("Tip: import from résumé — LinkedIn often blocks public reads.");
        }
        return;
      }
      applyImported(out);
      toast.success(out.partial ? "Partial LinkedIn import" : "Imported from LinkedIn URL");
      setTab("overview");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "URL import failed");
    } finally {
      setBusy(false);
    }
  };

  const analyzePaste = async () => {
    if (!paste.trim()) {
      toast.error("Paste your LinkedIn profile text first");
      return;
    }
    setBusy(true);
    try {
      const out = await api.linkedInAnalyze({
        text: paste,
        target_role: role,
        linkedin_url: linkedinUrl || undefined,
      });
      setProfile(out.profile);
      setScore(out.score);
      setRole(out.target_role);
      setSource(out.source || "paste");
      setLinkedinUrl(out.linkedin_url || linkedinUrl);
      setImportNote("Scored from pasted LinkedIn text.");
      toast.success("Profile analyzed");
      setTab("overview");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Analyze failed");
    } finally {
      setBusy(false);
    }
  };

  const saveAndRescore = async (next = profile, nextRole = role) => {
    setBusy(true);
    try {
      const out = await api.linkedInSave(next, nextRole);
      setProfile(out.profile);
      setScore(out.score);
      setRole(out.target_role);
      toast.success("Saved & rescored");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const runRewrite = async (sec: string) => {
    if (!substantial) {
      toast.error("Import real profile content before rewriting");
      return;
    }
    setBusy(true);
    try {
      const out = await api.linkedInRewrite({
        section: sec,
        profile,
        target_role: role,
        use_llm: useLlm,
      });
      setRewrites((r) => ({ ...r, [sec]: out }));
      toast.success(`Rewrote ${sec} (${out.mode})`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Rewrite failed");
    } finally {
      setBusy(false);
    }
  };

  const runRewriteAll = async () => {
    if (!substantial) {
      toast.error("Import real profile content before rewriting");
      return;
    }
    setBusy(true);
    try {
      const out = await api.linkedInRewriteAll({
        profile,
        target_role: role,
        use_llm: useLlm,
      });
      setRewrites(out.sections);
      toast.success("All sections rewritten from your evidence");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Rewrite-all failed");
    } finally {
      setBusy(false);
    }
  };

  const applySuggestion = async (sec: string) => {
    const rw = rewrites[sec];
    if (!rw?.suggested) return;
    const next = { ...profile };
    if (sec === "headline") next.headline = rw.suggested;
    else if (sec === "about") next.about = rw.suggested;
    else if (sec === "skills" && rw.suggested_list) next.skills = rw.suggested_list;
    else if (sec === "skills")
      next.skills = rw.suggested.split(",").map((s) => s.trim()).filter(Boolean);
    else if (sec === "experience" && rw.suggested_structured)
      next.experience = rw.suggested_structured;
    else if (sec === "open_to_work") next.open_to_work = rw.suggested;
    else if (sec === "featured") next.featured = rw.suggested;
    setProfile(next);
    await saveAndRescore(next, role);
  };

  const renderCover = async () => {
    setBusy(true);
    try {
      const out = await api.linkedInCoverRender({
        theme_id: coverTheme,
        name: profile.name || "Your Name",
        headline:
          profile.headline ||
          state?.roles?.find((r) => r.id === role)?.label ||
          "Open to opportunities",
        subline: coverSubline,
      });
      setCoverSvg(out.svg);
      toast.success("Cover rendered");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Cover render failed");
    } finally {
      setBusy(false);
    }
  };

  const downloadCover = () => {
    if (!coverSvg) {
      toast.error("Render a cover first");
      return;
    }
    const blob = new Blob([coverSvg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `linkedin-cover-${coverTheme}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportBundle = useMemo(() => {
    const parts = [
      `Name: ${profile.name}`,
      `Headline:\n${profile.headline}`,
      `\nAbout:\n${profile.about}`,
      `\nExperience:\n${(profile.experience || [])
        .map(
          (j) =>
            `${j.title}\n${j.company}\n${(j.bullets || []).map((b) => `• ${b}`).join("\n")}`
        )
        .join("\n\n")}`,
      `\nSkills:\n${(profile.skills || []).join(", ")}`,
      `\nFeatured:\n${profile.featured}`,
      `\nOpen to work:\n${profile.open_to_work}`,
      `\nLocation: ${profile.location}`,
      `Contact: ${profile.contact}`,
    ];
    return parts.join("\n");
  }, [profile]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-stone">
        <Loader2 className="animate-spin" size={18} /> Loading LinkedIn workspace…
      </div>
    );
  }

  const roles = state?.roles || [];

  return (
    <div className="space-y-6">
      {/* Import gate */}
      <div className="rounded-[32px] border border-mist bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-ink">Import real profile</h2>
            <p className="mt-1 max-w-2xl text-sm text-stone">
              We score and rewrite only what you actually have. LinkedIn public pages are
              often login-walled — résumé import is the reliable path when URL fetch fails.
            </p>
          </div>
          {source ? (
            <span className="rounded-full bg-lime/50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-ink">
              source: {source}
            </span>
          ) : null}
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_auto_auto]">
          <input
            value={linkedinUrl}
            onChange={(e) => setLinkedinUrl(e.target.value)}
            placeholder="https://www.linkedin.com/in/your-handle"
            className="rounded-2xl border border-mist bg-sage/50 px-4 py-2.5 text-sm outline-none focus:border-ink/30"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => void importFromUrl()}
            className="rounded-2xl bg-ink px-4 py-2.5 text-sm font-bold text-lime disabled:opacity-50"
          >
            Analyze URL
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void importFromCv()}
            className="rounded-2xl bg-lime px-4 py-2.5 text-sm font-bold text-ink disabled:opacity-50"
          >
            Import résumé
          </button>
        </div>
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-bold text-stone">
            Or paste LinkedIn text
          </summary>
          <textarea
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            rows={6}
            placeholder={"About\n…\n\nExperience\nTitle\nCompany\n• Bullet…\n\nSkills\n…"}
            className="mt-2 w-full rounded-[24px] border border-mist bg-sage/50 px-4 py-3 text-sm"
          />
          <button
            type="button"
            disabled={busy || !paste.trim()}
            onClick={() => void analyzePaste()}
            className="mt-2 inline-flex items-center gap-2 rounded-2xl bg-mist px-4 py-2 text-sm font-bold disabled:opacity-50"
          >
            <Sparkles size={14} /> Analyze paste
          </button>
        </details>
        {importNote ? <p className="mt-3 text-sm text-stone">{importNote}</p> : null}
        {!substantial ? (
          <p className="mt-3 rounded-2xl bg-orange/10 px-4 py-3 text-sm text-orange">
            No substantial profile loaded yet. Add a LinkedIn URL, import your résumé, or
            paste profile text — then we can score and suggest real optimizations.
          </p>
        ) : null}
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 rounded-[28px] border border-mist bg-white/80 p-4 backdrop-blur">
        <label className="text-xs font-bold uppercase tracking-widest text-stone/50">
          Target role
        </label>
        <select
          className="rounded-2xl border border-mist bg-sage px-3 py-2 text-sm font-medium text-ink"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
        <label className="ml-2 flex items-center gap-2 text-sm text-stone">
          <input
            type="checkbox"
            checked={useLlm}
            onChange={(e) => setUseLlm(e.target.checked)}
            className="rounded border-mist"
          />
          Polish with LLM if available
        </label>
        <div className="ml-auto flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy || !substantial}
            onClick={() => void saveAndRescore()}
            className="inline-flex items-center gap-2 rounded-2xl bg-mist px-4 py-2 text-sm font-bold text-ink disabled:opacity-50"
          >
            <RefreshCw size={14} /> Rescore
          </button>
          <button
            type="button"
            disabled={busy || !substantial}
            onClick={() => void runRewriteAll()}
            className="inline-flex items-center gap-2 rounded-2xl bg-ink px-4 py-2 text-sm font-bold text-lime disabled:opacity-50"
          >
            <Wand2 size={14} /> Rewrite all
          </button>
        </div>
      </div>

      {/* In-page tabs */}
      <div className="flex gap-1 overflow-x-auto rounded-[24px] border border-mist bg-white p-1.5">
        {LINKEDIN_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={clsx(
              "shrink-0 rounded-2xl px-3.5 py-2 text-sm font-bold transition",
              tab === t.id ? "bg-ink text-lime" : "text-stone hover:bg-mist hover:text-ink"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <OverviewPanel score={score} profile={profile} setProfile={setProfile} />
      ) : null}

      {tab === "headline" ? (
        <SectionEditor
          title="Headline"
          hint="Built from your real titles + evidenced stack keywords. Missing search terms are listed — not invented."
          value={profile.headline}
          onChange={(v) => setProfile({ ...profile, headline: v })}
          onRewrite={() => void runRewrite("headline")}
          onApply={() => void applySuggestion("headline")}
          onCopy={() => void copyText("headline", rewrites.headline?.suggested || profile.headline)}
          busy={busy || !substantial}
          rewrite={rewrites.headline}
        />
      ) : null}

      {tab === "about" ? (
        <SectionEditor
          title="About"
          hint="Rewrites your existing summary only. No fake proof points."
          value={profile.about}
          onChange={(v) => setProfile({ ...profile, about: v })}
          rows={12}
          onRewrite={() => void runRewrite("about")}
          onApply={() => void applySuggestion("about")}
          onCopy={() => void copyText("about", rewrites.about?.suggested || profile.about)}
          busy={busy || !substantial}
          rewrite={rewrites.about}
        />
      ) : null}

      {tab === "experience" ? (
        <ExperienceEditor
          profile={profile}
          setProfile={setProfile}
          busy={busy || !substantial}
          rewrite={rewrites.experience}
          onRewrite={() => void runRewrite("experience")}
          onApply={() => void applySuggestion("experience")}
        />
      ) : null}

      {tab === "keywords" ? (
        <KeywordsPanel score={score} profile={profile} setProfile={setProfile} />
      ) : null}

      {tab === "visibility" ? (
        <VisibilityPanel score={score} profile={profile} setProfile={setProfile} />
      ) : null}

      {tab === "cover" ? (
        <CoverPanel
          themes={themes}
          coverTheme={coverTheme}
          setCoverTheme={setCoverTheme}
          coverSubline={coverSubline}
          setCoverSubline={setCoverSubline}
          coverSvg={coverSvg}
          busy={busy}
          onRender={() => void renderCover()}
          onDownload={downloadCover}
          profile={profile}
        />
      ) : null}

      {tab === "preview" ? <PreviewPanel profile={profile} score={score} /> : null}

      {tab === "export" ? (
        <div className="space-y-4 rounded-[32px] border border-mist bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-ink">Export / Copy</h2>
              <p className="mt-1 text-sm text-stone">
                Paste into LinkedIn yourself. We never auto-edit your LinkedIn account.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void copyText("full profile", exportBundle)}
              className="inline-flex items-center gap-2 rounded-2xl bg-ink px-4 py-2 text-sm font-bold text-lime"
            >
              <Copy size={14} /> Copy full profile
            </button>
          </div>
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-[24px] bg-sage/60 p-4 text-sm leading-relaxed text-ink">
            {exportBundle}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function OverviewPanel({
  score,
  profile,
  setProfile,
}: {
  score: LinkedInScore | null;
  profile: LinkedInProfile;
  setProfile: (p: LinkedInProfile) => void;
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="space-y-4 rounded-[32px] border border-mist bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold text-ink">Loaded profile</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" value={profile.name} onChange={(v) => setProfile({ ...profile, name: v })} />
          <Field
            label="Location"
            value={profile.location}
            onChange={(v) => setProfile({ ...profile, location: v })}
          />
        </div>
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-widest text-stone/50">Headline</p>
          <p className="text-sm font-medium text-ink">{profile.headline || "—"}</p>
        </div>
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-widest text-stone/50">
            Experience ({(profile.experience || []).length} roles)
          </p>
          <ul className="space-y-1 text-sm text-stone">
            {(profile.experience || []).slice(0, 5).map((j, i) => (
              <li key={i}>
                <span className="font-bold text-ink">{j.title}</span>
                {j.company ? ` · ${j.company}` : ""} · {(j.bullets || []).length} bullets
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-widest text-stone/50">
            Skills ({(profile.skills || []).length})
          </p>
          <p className="text-sm text-stone">{(profile.skills || []).slice(0, 12).join(", ") || "—"}</p>
        </div>
      </div>
      <div className="space-y-4 rounded-[32px] border border-mist bg-white p-6 shadow-sm">
        <div className="flex items-center gap-4">
          <ScoreRing score={score?.overall ?? 0} />
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-stone/50">
              Searchability
            </p>
            <h3 className="text-lg font-bold text-ink">{score?.role_label || "Target role"}</h3>
            <p className="text-sm text-stone">
              Mode: {score?.mode || "heuristic"} · weak:{" "}
              {(score?.weak_areas || []).join(", ") || "none"}
            </p>
          </div>
        </div>
        <div className="space-y-2">
          {Object.entries(score?.dimensions || {}).map(([k, v]) => (
            <div key={k} className="flex items-center gap-3">
              <span className="w-36 shrink-0 text-xs font-bold uppercase tracking-wide text-stone">
                {DIM_LABELS[k] || k}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-mist">
                <div
                  className={clsx("h-full rounded-full", v >= 60 ? "bg-ink" : "bg-orange")}
                  style={{ width: `${Math.min(100, v)}%` }}
                />
              </div>
              <span className="w-8 text-right text-sm font-bold">{v}</span>
            </div>
          ))}
        </div>
        {score?.checklist?.length ? (
          <ul className="space-y-2 border-t border-mist pt-4">
            {score.checklist.slice(0, 6).map((c) => (
              <li key={c.id} className="text-sm">
                <span className="font-bold text-ink">{c.label}</span>
                <span className="text-stone"> — {c.detail}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function SectionEditor({
  title,
  hint,
  value,
  onChange,
  rows = 4,
  onRewrite,
  onApply,
  onCopy,
  busy,
  rewrite,
}: {
  title: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  onRewrite: () => void;
  onApply: () => void;
  onCopy: () => void;
  busy: boolean;
  rewrite?: LinkedInRewriteResult;
}) {
  return (
    <div className="space-y-4 rounded-[32px] border border-mist bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-ink">{title}</h2>
          <p className="mt-1 text-sm text-stone">{hint}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onRewrite}
            className="inline-flex items-center gap-2 rounded-2xl bg-ink px-3 py-2 text-sm font-bold text-lime disabled:opacity-50"
          >
            <Wand2 size={14} /> Suggest
          </button>
          <button
            type="button"
            disabled={busy || !rewrite?.suggested}
            onClick={onApply}
            className="inline-flex items-center gap-2 rounded-2xl bg-lime px-3 py-2 text-sm font-bold text-ink disabled:opacity-50"
          >
            <Check size={14} /> Apply
          </button>
          <button
            type="button"
            onClick={onCopy}
            className="inline-flex items-center gap-2 rounded-2xl bg-mist px-3 py-2 text-sm font-bold text-ink"
          >
            <Copy size={14} /> Copy
          </button>
        </div>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="w-full rounded-[24px] border border-mist bg-sage/50 px-4 py-3 text-sm leading-relaxed text-ink outline-none focus:border-ink/30"
      />
      {rewrite?.recommended_keywords?.length ? (
        <p className="text-sm text-stone">
          Recommended keywords (add only if true):{" "}
          <span className="font-medium text-ink">{rewrite.recommended_keywords.join(", ")}</span>
        </p>
      ) : null}
      {rewrite ? (
        <DiffPanel
          original={rewrite.original}
          suggested={rewrite.suggested}
          rationale={rewrite.rationale}
          mode={rewrite.mode}
        />
      ) : null}
    </div>
  );
}

function ExperienceEditor({
  profile,
  setProfile,
  busy,
  rewrite,
  onRewrite,
  onApply,
}: {
  profile: LinkedInProfile;
  setProfile: (p: LinkedInProfile) => void;
  busy: boolean;
  rewrite?: LinkedInRewriteResult;
  onRewrite: () => void;
  onApply: () => void;
}) {
  const jobs = profile.experience || [];
  return (
    <div className="space-y-4 rounded-[32px] border border-mist bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-ink">Experience</h2>
          <p className="mt-1 text-sm text-stone">
            Your real employers and bullets only. Suggestions never invent metrics.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onRewrite}
            className="rounded-2xl bg-ink px-3 py-2 text-sm font-bold text-lime disabled:opacity-50"
          >
            Suggest edits
          </button>
          <button
            type="button"
            disabled={busy || !rewrite?.suggested}
            onClick={onApply}
            className="rounded-2xl bg-lime px-3 py-2 text-sm font-bold text-ink disabled:opacity-50"
          >
            Apply
          </button>
        </div>
      </div>
      {jobs.map((job, i) => (
        <div key={i} className="rounded-[24px] border border-mist bg-sage/40 p-4">
          <div className="mb-2 grid gap-2 sm:grid-cols-2">
            <input
              value={job.title}
              onChange={(e) => {
                const next = [...jobs];
                next[i] = { ...job, title: e.target.value };
                setProfile({ ...profile, experience: next });
              }}
              className="rounded-xl border border-mist bg-white px-3 py-2 text-sm font-bold"
            />
            <input
              value={job.company}
              onChange={(e) => {
                const next = [...jobs];
                next[i] = { ...job, company: e.target.value };
                setProfile({ ...profile, experience: next });
              }}
              className="rounded-xl border border-mist bg-white px-3 py-2 text-sm"
            />
          </div>
          <textarea
            value={(job.bullets || []).join("\n")}
            onChange={(e) => {
              const next = [...jobs];
              next[i] = {
                ...job,
                bullets: e.target.value
                  .split("\n")
                  .map((l) => l.replace(/^•\s*/, "").trim())
                  .filter(Boolean),
              };
              setProfile({ ...profile, experience: next });
            }}
            rows={5}
            className="w-full rounded-xl border border-mist bg-white px-3 py-2 text-sm leading-relaxed"
          />
        </div>
      ))}
      {rewrite ? (
        <DiffPanel
          original={rewrite.original}
          suggested={rewrite.suggested}
          rationale={rewrite.rationale}
          mode={rewrite.mode}
        />
      ) : null}
    </div>
  );
}

function KeywordsPanel({
  score,
  profile,
  setProfile,
}: {
  score: LinkedInScore | null;
  profile: LinkedInProfile;
  setProfile: (p: LinkedInProfile) => void;
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-[32px] border border-mist bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold text-ink">Keyword Match</h2>
        <p className="mt-1 text-sm text-stone">
          Found terms come from your imported content. Missing terms are suggestions —
          add them only if accurate.
        </p>
        <div className="mt-4">
          <p className="mb-2 text-xs font-bold uppercase tracking-widest text-stone/50">Found</p>
          <div className="flex flex-wrap gap-2">
            {(score?.found_keywords || []).map((k) => (
              <span key={k} className="rounded-full bg-lime/50 px-3 py-1 text-xs font-bold text-ink">
                {k}
              </span>
            ))}
          </div>
        </div>
        <div className="mt-4">
          <p className="mb-2 text-xs font-bold uppercase tracking-widest text-stone/50">
            Missing (optional)
          </p>
          <div className="flex flex-wrap gap-2">
            {(score?.missing_keywords || []).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  if (profile.skills.map((s) => s.toLowerCase()).includes(k.toLowerCase())) return;
                  setProfile({ ...profile, skills: [...profile.skills, k] });
                  toast.success(`Added “${k}” to skills — only keep if true`);
                }}
                className="rounded-full bg-orange/10 px-3 py-1 text-xs font-bold text-orange hover:bg-orange/20"
              >
                + {k}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="rounded-[32px] border border-mist bg-white p-6 shadow-sm">
        <h2 className="mb-2 text-lg font-bold text-ink">Skills</h2>
        <textarea
          value={(profile.skills || []).join(", ")}
          onChange={(e) =>
            setProfile({
              ...profile,
              skills: e.target.value
                .split(/[,•\n]+/)
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          rows={8}
          className="w-full rounded-[24px] border border-mist bg-sage/50 px-4 py-3 text-sm"
        />
      </div>
    </div>
  );
}

function VisibilityPanel({
  score,
  profile,
  setProfile,
}: {
  score: LinkedInScore | null;
  profile: LinkedInProfile;
  setProfile: (p: LinkedInProfile) => void;
}) {
  const presence = score?.section_presence || {};
  return (
    <div className="space-y-6">
      <div className="rounded-[32px] border border-mist bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold text-ink">Visibility Check</h2>
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {Object.entries(presence).map(([k, ok]) => (
            <li
              key={k}
              className={clsx(
                "flex items-center gap-2 rounded-2xl px-3 py-2 text-sm font-medium",
                ok ? "bg-lime/40 text-ink" : "bg-orange/10 text-orange"
              )}
            >
              {ok ? <Check size={14} /> : <span className="text-xs font-bold">!</span>}
              {k.replace(/_/g, " ")}
            </li>
          ))}
        </ul>
      </div>
      <div className="grid gap-4 rounded-[32px] border border-mist bg-white p-6 shadow-sm lg:grid-cols-2">
        <Field
          label="Location"
          value={profile.location}
          onChange={(v) => setProfile({ ...profile, location: v })}
        />
        <Field
          label="Contact"
          value={profile.contact}
          onChange={(v) => setProfile({ ...profile, contact: v })}
        />
        <label className="block lg:col-span-2">
          <span className="mb-1 block text-xs font-bold uppercase tracking-widest text-stone/50">
            Open to work
          </span>
          <textarea
            value={profile.open_to_work}
            onChange={(e) => setProfile({ ...profile, open_to_work: e.target.value })}
            rows={4}
            className="w-full rounded-[24px] border border-mist bg-sage/50 px-4 py-3 text-sm"
          />
        </label>
      </div>
    </div>
  );
}

function CoverPanel({
  themes,
  coverTheme,
  setCoverTheme,
  coverSubline,
  setCoverSubline,
  coverSvg,
  busy,
  onRender,
  onDownload,
  profile,
}: {
  themes: LinkedInCoverTheme[];
  coverTheme: string;
  setCoverTheme: (id: string) => void;
  coverSubline: string;
  setCoverSubline: (v: string) => void;
  coverSvg: string;
  busy: boolean;
  onRender: () => void;
  onDownload: () => void;
  profile: LinkedInProfile;
}) {
  return (
    <div className="space-y-4 rounded-[32px] border border-mist bg-white p-6 shadow-sm">
      <h2 className="text-xl font-bold text-ink">Cover banner</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {themes.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setCoverTheme(t.id)}
            className={clsx(
              "rounded-[24px] border p-4 text-left transition",
              coverTheme === t.id ? "border-ink ring-2 ring-lime" : "border-mist"
            )}
          >
            <div
              className="mb-3 h-12 rounded-xl"
              style={{
                background: `linear-gradient(90deg, ${t.preview_colors.bg} 70%, ${t.preview_colors.accent})`,
              }}
            />
            <p className="font-bold text-ink">{t.label}</p>
            <p className="text-xs text-stone">{t.description}</p>
          </button>
        ))}
      </div>
      <Field label="Subline" value={coverSubline} onChange={setCoverSubline} />
      <p className="text-sm text-stone">
        Uses “{profile.name || "Your Name"}” · “{(profile.headline || "").slice(0, 60)}”
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onRender}
          className="rounded-2xl bg-ink px-4 py-2 text-sm font-bold text-lime disabled:opacity-50"
        >
          Render preview
        </button>
        <button
          type="button"
          onClick={onDownload}
          className="inline-flex items-center gap-2 rounded-2xl bg-mist px-4 py-2 text-sm font-bold"
        >
          <Download size={14} /> Download SVG
        </button>
      </div>
      {coverSvg ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          alt="LinkedIn cover preview"
          className="w-full rounded-[24px] border border-mist"
          src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(coverSvg)}`}
        />
      ) : null}
    </div>
  );
}

function PreviewPanel({
  profile,
  score,
}: {
  profile: LinkedInProfile;
  score: LinkedInScore | null;
}) {
  return (
    <div className="mx-auto max-w-2xl overflow-hidden rounded-[32px] border border-mist bg-white shadow-sm">
      <div className="h-28 bg-gradient-to-r from-ink via-ink to-stone/40" />
      <div className="relative px-6 pb-8 pt-2">
        <div className="-mt-12 mb-3 flex h-24 w-24 items-center justify-center rounded-full border-4 border-white bg-lime text-2xl font-bold text-ink">
          {(profile.name || "?").slice(0, 1).toUpperCase()}
        </div>
        <h2 className="text-2xl font-bold text-ink">{profile.name || "Your Name"}</h2>
        <p className="text-base text-ink">{profile.headline || "Add a headline"}</p>
        <p className="mt-1 text-sm text-stone">
          {profile.location || "Location"} · Score {score?.overall ?? "—"}
        </p>
        <div className="mt-6 border-t border-mist pt-4">
          <h3 className="text-xs font-bold uppercase tracking-widest text-stone/50">About</h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink">
            {profile.about || "—"}
          </p>
        </div>
        <div className="mt-6 border-t border-mist pt-4">
          <h3 className="text-xs font-bold uppercase tracking-widest text-stone/50">Experience</h3>
          {(profile.experience || []).map((j, i) => (
            <div key={i} className="mt-3">
              <p className="font-bold text-ink">{j.title}</p>
              <p className="text-sm text-stone">{j.company}</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
                {(j.bullets || []).map((b, bi) => (
                  <li key={bi}>{b}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
