"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { AtsScoreCard } from "@/src/components/cv/AtsScoreCard";
import { CvHtmlPreview } from "@/src/components/cv/CvHtmlPreview";
import { CvWorkspace } from "@/src/components/cv/CvWorkspace";
import { ResumeUploadZone } from "@/src/components/cv/ResumeUploadZone";
import { SetupChecksCard } from "@/src/components/onboarding/SetupChecksCard";
import { ProfileStep } from "@/src/components/onboarding/ProfileStep";
import { WelcomeOverview } from "@/src/components/onboarding/WelcomeOverview";
import { isPlaceholderCv } from "@/src/lib/cv/placeholder";
import { api, ApiError, type AtsScore, type AutomationSettings, type CvTemplate, type ProfileSetup, type SetupStatus } from "@/src/lib/api/client";
import { ArrowRight, CheckCircle2, FileText } from "lucide-react";

const STEPS = ["Welcome", "Profile", "Resume", "Template", "Review", "Done"] as const;
const WELCOME_SEEN_KEY = "autojob_onboarding_welcome_seen";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [cvMarkdown, setCvMarkdown] = useState("");
  const [templates, setTemplates] = useState<CvTemplate[]>([]);
  const [templateId, setTemplateId] = useState("awesome-inspired");
  const [ats, setAts] = useState<AtsScore | null>(null);
  const [scanned, setScanned] = useState(false);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [loadingCv, setLoadingCv] = useState(true);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [profile, setProfile] = useState<ProfileSetup | null>(null);
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const [showPaste, setShowPaste] = useState(false);
  const [hasUploadedPdf, setHasUploadedPdf] = useState(false);
  const [automation, setAutomation] = useState<AutomationSettings>({
    scan_enabled: true,
    scan_interval_hours: 72,
    auto_evaluate: true,
    auto_evaluate_min_score: 4.0,
    auto_approve_score: 0,
    last_scan_at: null,
  });

  useEffect(() => {
    (async () => {
      try {
        const [{ templates: tpls }, cvContent] = await Promise.all([
          api.listCvTemplates(),
          api.getCvContent().catch(() => ({ markdown: "" })),
        ]);
        setTemplates(tpls);
        if (cvContent.markdown?.trim()) {
          setCvMarkdown(cvContent.markdown);
          const status = await api.getCvStatus();
          setAts(status.ats);
          setScanned(true);
          setHasUploadedPdf(Boolean(status.has_uploaded_pdf));
          setTemplateId(status.cv_settings?.template_id || "awesome-inspired");
        }
        const auto = await api.getAutomation().catch(() => null);
        if (auto) setAutomation((a) => ({ ...a, ...auto }));
        const [profileData, setup] = await Promise.all([
          api.getProfile().catch(() => null),
          api.setupStatus().catch(() => null),
        ]);
        if (profileData) setProfile(profileData);
        if (setup) {
          setSetupStatus(setup);
          if (setup.onboarding_complete) {
            router.replace("/dashboard");
            return;
          }
        }
        // Resume mid-wizard only after they've seen the welcome once.
        const welcomeSeen =
          typeof window !== "undefined" && localStorage.getItem(WELCOME_SEEN_KEY) === "1";
        if (welcomeSeen && profileData?.exists && profileData.name && profileData.email) {
          setStep(2);
        } else if (welcomeSeen) {
          setStep(1);
        }
      } catch {
        /* offline */
      } finally {
        setLoadingCv(false);
        setLoadingProfile(false);
      }
    })();
  }, [router]);

  useEffect(() => {
    if (step !== 3) return;
    let cancelled = false;
    (async () => {
      setPreviewLoading(true);
      try {
        const res = await api.previewCv(templateId, cvMarkdown);
        if (!cancelled) setPreviewHtml(res.html);
      } catch {
        if (!cancelled) setPreviewHtml(null);
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [step, templateId, cvMarkdown]);

  const continueFromWelcome = () => {
    try {
      localStorage.setItem(WELCOME_SEEN_KEY, "1");
    } catch {
      /* private mode */
    }
    if (profile?.exists && profile.name && profile.email) {
      setStep(2);
    } else {
      setStep(1);
    }
  };

  const scanResume = async () => {
    if (isPlaceholderCv(cvMarkdown)) {
      toast.error("Replace the template text with your real resume before continuing.");
      return;
    }
    setScanning(true);
    try {
      const res = await api.saveCv(cvMarkdown);
      setAts(res.ats);
      setScanned(true);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not scan resume");
    } finally {
      setScanning(false);
    }
  };

  const uploadResume = async (file: File) => {
    try {
      const res = await api.uploadCv(file);
      setCvMarkdown(res.markdown);
      setAts(res.ats);
      setScanned(true);
      setShowPaste(true);
      if (res.is_placeholder) {
        toast.message("Extracted text looks thin — review and edit below.");
      } else {
        const targeting = res.applied_target_titles?.length
          ? ` Targeting updated to ${res.applied_target_titles.slice(0, 3).join(", ")}.`
          : "";
        toast.success(`Resume extracted — review the text, then continue.${targeting}`);
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed — is the API running?");
      throw e;
    }
  };

  const pickTemplateAndContinue = async () => {
    if (isPlaceholderCv(cvMarkdown)) {
      toast.error("Paste your real resume first — the preview still shows placeholder text.");
      return;
    }
    setGenerating(true);
    try {
      const res = await api.generateCv(templateId, cvMarkdown);
      setAts(res.ats as AtsScore);
      setStep(4);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Generate failed");
    } finally {
      setGenerating(false);
    }
  };

  const saveProfile = async (data: ProfileSetup & { llm_api_key?: string }) => {
    try {
      const saved = await api.saveProfile(data);
      setProfile(saved);
      const setup = await api.setupStatus();
      setSetupStatus(setup);
      toast.success("Profile saved");
      setStep(2);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save profile");
      throw e;
    }
  };

  const finishOnboarding = async () => {
    if (isPlaceholderCv(cvMarkdown)) {
      toast.error("Update your resume with real content before finishing setup.");
      setStep(2);
      setScanned(false);
      return;
    }
    try {
      await api.setAutomation({ ...automation, onboarding_complete: true });
      if (automation.scan_enabled) {
        await api.runScheduledScan(false, true);
        toast.message("First job scan queued — check inbox soon");
      }
      setStep(5);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save settings");
    }
  };

  return (
    <DashboardShell title="Get started" breadcrumbs={["Home", "Setup"]}>
      <div className="w-full space-y-8">
        <div className="flex flex-wrap gap-2">
          {STEPS.map((label, i) => {
            // Steps past Profile are locked until a profile is saved.
            const locked = i > 1 && !profile?.exists;
            return (
              <button
                key={label}
                type="button"
                disabled={locked}
                title={locked ? "Save your profile first" : undefined}
                onClick={() => !locked && setStep(i)}
                className={`rounded-full px-4 py-2 text-sm font-bold transition-colors ${
                  locked ? "cursor-not-allowed bg-white text-stone/30" : "hover:opacity-80"
                } ${
                  i === step ? "bg-lime text-ink" : i < step ? "bg-mist text-stone" : "bg-white text-stone/50"
                }`}
              >
                {i + 1}. {label}
              </button>
            );
          })}
        </div>

        {step === 0 && <WelcomeOverview onContinue={continueFromWelcome} />}

        {step === 1 && (
          <ProfileStep
            initial={profile}
            loading={loadingProfile}
            onSave={saveProfile}
            onResumeUploaded={(res) => {
              setCvMarkdown(res.markdown);
              setAts(res.ats);
              setScanned(true);
              setShowPaste(true);
              setHasUploadedPdf(Boolean(res.pdf_path));
            }}
          />
        )}

        {step === 2 && (
          <div className="space-y-6">
            {scanned && ats && hasUploadedPdf ? (
              <Card padding="lg" className="space-y-4">
                <h2 className="text-xl font-bold text-ink">Your resume</h2>
                <div className="flex items-center gap-4 rounded-2xl border border-lime/30 bg-lime/10 px-5 py-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-lime/30">
                    <CheckCircle2 size={24} className="text-lime-ink" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-ink">Uploaded PDF ready</p>
                    <p className="text-base text-stone">
                      ATS readiness: <strong>{ats.content_score ?? ats.ats_readiness ?? ats.score}%</strong> — this resume will be sent to employers.
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => api.downloadCvFile("uploaded").catch((e) => toast.error(e.message))}
                  >
                    <ArrowRight size={14} />
                    Download
                  </Button>
                </div>
                <AtsScoreCard
                  ats={ats}
                  onImprove={() => setScanned(false)}
                  onContinue={() => setStep(3)}
                  continueLabel="Pick a template"
                />
                <details className="text-base">
                  <summary className="cursor-pointer font-semibold text-stone">Replace resume or edit text</summary>
                  <div className="mt-3 space-y-3">
                    <ResumeUploadZone disabled={loadingCv} onUpload={uploadResume} />
                    <textarea
                      value={cvMarkdown}
                      onChange={(e) => setCvMarkdown(e.target.value)}
                      rows={8}
                      className="w-full rounded-2xl border border-mist bg-sage/20 p-4 font-mono text-sm leading-relaxed text-ink outline-none focus:border-lime/40"
                    />
                    <Button variant="secondary" size="sm" onClick={scanResume} isLoading={scanning}>
                      Re-scan after edits
                    </Button>
                  </div>
                </details>
              </Card>
            ) : (
              <Card padding="lg" className="space-y-4">
                <h2 className="text-xl font-bold text-ink">
                  {scanned && ats ? "Your resume" : "Add your resume"}
                </h2>
                <p className="text-base text-stone">
                  Upload your PDF or Word file to replace the starter resume, or edit the extracted text below.
                </p>
                {!scanned ? (
                  <>
                    <ResumeUploadZone disabled={loadingCv} onUpload={uploadResume} />
                    <button
                      type="button"
                      onClick={() => setShowPaste((v) => !v)}
                      className="text-sm font-semibold text-stone underline hover:text-ink"
                    >
                      {showPaste ? "Hide paste option" : "Or paste markdown instead"}
                    </button>
                    {showPaste && (
                      <>
                        <textarea
                          value={cvMarkdown}
                          onChange={(e) => setCvMarkdown(e.target.value)}
                          rows={12}
                          disabled={loadingCv}
                          className="w-full rounded-2xl border border-mist bg-sage/20 p-4 font-mono text-sm leading-relaxed text-ink outline-none focus:border-lime/40"
                        />
                        <Button variant="lime" onClick={scanResume} isLoading={scanning}>
                          Scan pasted resume
                        </Button>
                      </>
                    )}
                  </>
                ) : ats ? (
                  <>
                    <ResumeUploadZone disabled={loadingCv} onUpload={uploadResume} />
                    <details className="text-base">
                      <summary className="cursor-pointer font-semibold text-stone">Edit extracted text</summary>
                      <textarea
                        value={cvMarkdown}
                        onChange={(e) => setCvMarkdown(e.target.value)}
                        rows={10}
                        className="mt-2 w-full rounded-2xl border border-mist bg-sage/20 p-4 font-mono text-sm leading-relaxed text-ink outline-none focus:border-lime/40"
                      />
                      <Button variant="secondary" size="sm" className="mt-2" onClick={scanResume} isLoading={scanning}>
                        Re-scan after edits
                      </Button>
                    </details>
                    <AtsScoreCard
                      ats={ats}
                      onImprove={() => setScanned(false)}
                      onContinue={() => setStep(3)}
                      continueLabel="Pick a template"
                    />
                  </>
                ) : null}
              </Card>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card padding="lg" className="space-y-4">
              <h2 className="text-xl font-bold text-ink">Choose a look</h2>
              <p className="text-base text-stone">
                {hasUploadedPdf
                  ? "Use your uploaded resume as-is, or pick an ATS-safe template."
                  : "ATS-safe templates — live A4 preview on the right."}
              </p>
              {hasUploadedPdf && (
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await api.setResumeSource("uploaded");
                      toast.success("Using your uploaded PDF");
                      setStep(4);
                    } catch (e) {
                      toast.error(e instanceof ApiError ? e.message : "Could not set resume source");
                    }
                  }}
                  className="flex w-full items-center gap-3 rounded-xl border-2 border-lime bg-lime/10 p-4 text-left transition hover:bg-lime/20"
                >
                  <FileText size={24} className="shrink-0 text-lime-ink" />
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-ink">Use my uploaded PDF</p>
                    <p className="text-sm text-stone">Your original resume will be sent to employers as-is.</p>
                  </div>
                  <ArrowRight size={18} className="shrink-0 text-lime-ink" />
                </button>
              )}
              {hasUploadedPdf && (
                <p className="text-sm font-semibold text-stone">Or reformat with a template</p>
              )}
              <div className="grid gap-2">
                {templates.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTemplateId(t.id)}
                    className={`rounded-xl border p-3 text-left transition ${
                      templateId === t.id ? "border-lime bg-lime/10" : "border-mist bg-white hover:border-stone/30"
                    }`}
                  >
                    <p className="font-bold text-ink">{t.name}</p>
                    <p className="text-sm text-stone">{t.description}</p>
                  </button>
                ))}
              </div>
              <Button variant="lime" onClick={pickTemplateAndContinue} isLoading={generating}>
                Build final resume
                <ArrowRight size={18} />
              </Button>
            </Card>
            <CvHtmlPreview html={previewHtml} loading={previewLoading} />
          </div>
        )}

        {step === 4 && (
          <div className="space-y-6">
            <SetupChecksCard status={setupStatus} />
            {ats && <AtsScoreCard ats={ats} compact />}
            <Card padding="lg" className="space-y-4">
              <h2 className="text-xl font-bold text-ink">Review your resume</h2>
              <p className="text-base text-stone">Edit, regenerate, or download. You can change this anytime from Resume.</p>
              <CvWorkspace
                embedded
                initialTab="preview"
                initialMarkdown={cvMarkdown}
                initialTemplateId={templateId}
              />
            </Card>
            <Card padding="lg" className="space-y-4">
              <h3 className="font-bold text-ink">Auto-find jobs</h3>
              <label className="flex items-center gap-3 text-sm font-semibold text-ink">
                <input
                  type="checkbox"
                  checked={automation.scan_enabled}
                  onChange={(e) => setAutomation((a) => ({ ...a, scan_enabled: e.target.checked }))}
                  className="h-4 w-4 rounded border-mist"
                />
                Scan job boards on a schedule (never auto-applies)
              </label>
              <Button variant="lime" onClick={finishOnboarding}>
                Finish
                <ArrowRight size={18} />
              </Button>
            </Card>
          </div>
        )}

        {step === 5 && (
          <Card padding="lg" className="space-y-4 text-center">
            <CheckCircle2 className="mx-auto text-lime-ink" size={48} />
            <h2 className="text-xl font-bold text-ink">You&apos;re set</h2>
            {ats && (
              <p className="text-base text-stone">
                ATS readiness score: <strong>{ats.content_score ?? ats.job_match_percent ?? ats.score}%</strong> —
                structured for applicant tracking systems.
              </p>
            )}
            <p className="mx-auto max-w-lg text-base text-stone">
              Next: open <strong className="text-ink">Discover</strong> to scan jobs, evaluate fits, approve
              good ones, then use <strong className="text-ink">Prep</strong> before you apply.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Link href="/inbox">
                <Button variant="lime">Go to Discover</Button>
              </Link>
              <Link href="/connections">
                <Button variant="secondary">Add Apify (more jobs)</Button>
              </Link>
              <Link href="/connections">
                <Button variant="secondary">Set up Local AI</Button>
              </Link>
              <Link href="/cv">
                <Button variant="secondary">Resume</Button>
              </Link>
            </div>
            <p className="pt-2 text-sm text-stone">
              Manage these anytime from the sidebar —{" "}
              <Link href="/profile" className="font-bold text-ink underline">Profile</Link>,{" "}
              <Link href="/connections" className="font-bold text-ink underline">Connections</Link>, and{" "}
              <Link href="/cv" className="font-bold text-ink underline">Resume</Link>.
            </p>
          </Card>
        )}
      </div>
    </DashboardShell>
  );
}
