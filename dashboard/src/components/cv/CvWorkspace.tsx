"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Check,
  Download,
  Eye,
  FileText,
  Pencil,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { Modal } from "@/src/components/ui/Modal";
import { AtsScoreCard } from "@/src/components/cv/AtsScoreCard";
import { CvHtmlPreview } from "@/src/components/cv/CvHtmlPreview";
import { CvPdfPreview } from "@/src/components/cv/CvPdfPreview";
import { ResumeUploadZone } from "@/src/components/cv/ResumeUploadZone";
import {
  api,
  ApiError,
  type AtsScore,
  type CvArtifacts,
  type CvTemplate,
  type PageTarget,
} from "@/src/lib/api/client";

type Tab = "preview" | "edit" | "templates";

const PAGE_TARGETS: { id: PageTarget; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "One page if it fits, otherwise two" },
  { id: "1", label: "1 page", hint: "Tighten the layout until it holds one page" },
  { id: "2", label: "2 pages", hint: "Give a long career room to breathe" },
];

interface CvWorkspaceProps {
  /** When true, hide page chrome extras (used inside onboarding). */
  embedded?: boolean;
  initialTab?: Tab;
  /** Seed from parent (onboarding) so preview uses latest edits before API round-trip. */
  initialMarkdown?: string;
  initialTemplateId?: string;
  onGenerated?: (ats: AtsScore) => void;
}

export function CvWorkspace({
  embedded = false,
  initialTab = "preview",
  initialMarkdown = "",
  initialTemplateId = "ats-single",
  onGenerated,
}: CvWorkspaceProps) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [markdown, setMarkdown] = useState(initialMarkdown);
  const [templates, setTemplates] = useState<CvTemplate[]>([]);
  const [templateId, setTemplateId] = useState(initialTemplateId);
  const [ats, setAts] = useState<AtsScore | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<CvArtifacts | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [previewModal, setPreviewModal] = useState<string | null>(null);
  const [resumeSource, setResumeSource] = useState<"uploaded" | "generated">("uploaded");
  const [hasUploaded, setHasUploaded] = useState(false);
  const [pageTarget, setPageTarget] = useState<PageTarget>("auto");
  const [latexEngine, setLatexEngine] = useState<string>("");
  const [showPdf, setShowPdf] = useState(true);
  const [pdfVersion, setPdfVersion] = useState(0);
  const [showUpload, setShowUpload] = useState(false);

  const activeTemplate = useMemo(
    () => templates.find((t) => t.id === templateId) || null,
    [templates, templateId]
  );

  const sortedTemplates = useMemo(() => {
    const rec = templates.filter((t) => t.recommended);
    const rest = templates.filter((t) => !t.recommended);
    return [...rec, ...rest];
  }, [templates]);

  const loadPreview = useCallback(
    async (tpl: string, md?: string) => {
      setPreviewLoading(true);
      try {
        const content = (md ?? markdown).trim();
        // Prefer one page only when the user explicitly chose "1 page"; otherwise
        // keep readable type and let lengthy CVs flow onto page 2 in the preview.
        const preferSingle = pageTarget === "1";
        const res = await api.previewCv(tpl, content || undefined, !content, preferSingle);
        setPreviewHtml(res.html);
      } catch {
        setPreviewHtml(null);
      } finally {
        setPreviewLoading(false);
      }
    },
    [markdown, pageTarget]
  );

  useEffect(() => {
    if (initialMarkdown) setMarkdown(initialMarkdown);
  }, [initialMarkdown]);

  useEffect(() => {
    if (initialTemplateId) setTemplateId(initialTemplateId);
  }, [initialTemplateId]);

  useEffect(() => {
    if (initialMarkdown?.trim()) {
      loadPreview(initialTemplateId || templateId, initialMarkdown);
    }
  }, [initialMarkdown, initialTemplateId, loadPreview, templateId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [{ templates: tpls }, content, status, arts] = await Promise.all([
        api.listCvTemplates(),
        api.getCvContent(),
        api.getCvStatus(),
        api.getCvArtifacts(),
      ]);
      setTemplates(tpls);
      setMarkdown(content.markdown || "");
      setTemplateId(status.cv_settings?.template_id || "ats-single");
      setAts(status.ats);
      setArtifacts(arts);
      setResumeSource(status.cv_settings?.resume_source || "uploaded");
      setHasUploaded(Boolean(status.has_uploaded_pdf));
      setPageTarget(status.cv_settings?.page_target || "auto");
      setLatexEngine(status.latex_engine || "");
      setPdfVersion((v) => v + 1);
      if (content.markdown?.trim()) {
        await loadPreview(status.cv_settings?.template_id || "ats-single", content.markdown);
      }
    } catch {
      toast.error("Could not load resume — is the API running?");
    } finally {
      setLoading(false);
    }
  }, [loadPreview]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (tab === "preview" || tab === "templates") {
      loadPreview(templateId);
    }
  }, [tab, templateId, pageTarget, loadPreview]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.saveCv(markdown);
      setAts(res.ats);
      toast.success("Resume saved");
      setTab("preview");
      await loadPreview(templateId);
      const arts = await api.getCvArtifacts();
      setArtifacts(arts);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleGenerate = async (tpl?: string) => {
    const id = tpl || templateId;
    setGenerating(true);
    try {
      if (tpl && tpl !== templateId) setTemplateId(tpl);
      const res = await api.generateCv(id, markdown, pageTarget);
      const newAts = res.ats as AtsScore;
      setAts(newAts);
      onGenerated?.(newAts);
      if (res.fitted) {
        toast.success(`PDF ready — ${res.pages} page${res.pages === 1 ? "" : "s"}`);
      } else {
        toast.warning(
          `Could not fit ${res.page_target} page${res.page_target === 1 ? "" : "s"} — ` +
            `generated ${res.pages}. Trim a role or a few bullets in Edit.`
        );
      }
      const arts = await api.getCvArtifacts();
      setArtifacts(arts);
      setPdfVersion((v) => v + 1);
      await loadPreview(id);
      setTab("preview");
      setShowPdf(true);
      if (resumeSource !== "generated") {
        setResumeSource("generated");
        await api.setResumeSource("generated").catch(() => undefined);
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Generate failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Delete your saved resume? You can paste or upload a new one anytime.")) return;
    try {
      await api.deleteCv();
      setMarkdown("");
      setPreviewHtml(null);
      setAts(null);
      setArtifacts(null);
      setHasUploaded(false);
      toast.message("Resume cleared");
      setTab("edit");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Delete failed");
    }
  };

  const handleUpload = async (file: File) => {
    try {
      const out = await api.uploadCv(file);
      toast.success("Resume uploaded");
      setHasUploaded(true);
      setResumeSource("uploaded");
      if (out.markdown) setMarkdown(out.markdown);
      if (out.ats) setAts(out.ats);
      setShowUpload(false);
      await refresh();
      setTab("preview");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed");
      throw e;
    }
  };

  const openTemplatePreview = async (id: string) => {
    try {
      const preferSingle = pageTarget === "1";
      const res = await api.previewCv(
        id,
        markdown.trim() || undefined,
        !markdown.trim(),
        preferSingle
      );
      setPreviewModal(res.html);
    } catch {
      toast.error("Preview failed");
    }
  };

  const tabs: { id: Tab; label: string; icon: typeof Eye }[] = [
    { id: "preview", label: "Preview", icon: Eye },
    { id: "edit", label: "Edit", icon: Pencil },
    { id: "templates", label: "Templates", icon: Sparkles },
  ];

  return (
    <div className={embedded ? "space-y-4" : "space-y-6"}>
      {!embedded && (
        <Card padding="lg" className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-bold uppercase tracking-widest text-stone">
                What employers receive
              </p>
              <p className="mt-1 text-base text-stone">
                Choose your original PDF or a Shortlistr template compiled for ATS parsers.
              </p>
            </div>
            <Button variant="secondary" size="sm" onClick={() => setShowUpload((v) => !v)}>
              <Upload size={14} />
              {showUpload ? "Hide upload" : "Upload resume"}
            </Button>
          </div>

          {showUpload && (
            <ResumeUploadZone onUpload={handleUpload} />
          )}

          {hasUploaded ? (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={async () => {
                  setResumeSource("uploaded");
                  await api.setResumeSource("uploaded").catch((e) => toast.error(e.message));
                }}
                className={`flex-1 rounded-xl border-2 p-3 text-left transition ${
                  resumeSource === "uploaded"
                    ? "border-lime bg-lime/10"
                    : "border-mist bg-white hover:border-stone/30"
                }`}
              >
                <p className="font-bold text-ink">
                  <FileText size={16} className="mr-1.5 inline" />
                  My uploaded PDF
                </p>
                <p className="mt-1 text-sm text-stone">Your original file, sent as-is.</p>
              </button>
              <button
                type="button"
                onClick={async () => {
                  setResumeSource("generated");
                  await api.setResumeSource("generated").catch((e) => toast.error(e.message));
                }}
                className={`flex-1 rounded-xl border-2 p-3 text-left transition ${
                  resumeSource === "generated"
                    ? "border-lime bg-lime/10"
                    : "border-mist bg-white hover:border-stone/30"
                }`}
              >
                <p className="font-bold text-ink">
                  <Sparkles size={16} className="mr-1.5 inline" />
                  Shortlistr template
                </p>
                <p className="mt-1 text-sm text-stone">ATS-formatted PDF from the design below.</p>
              </button>
            </div>
          ) : (
            <p className="rounded-xl bg-sage/40 px-4 py-3 text-sm text-ink">
              No uploaded PDF yet — employers get the Shortlistr template PDF after you click{" "}
              <strong>Generate PDF</strong>. Upload anytime to keep your original file as an option.
            </p>
          )}

          {resumeSource === "uploaded" && hasUploaded && (
            <div className="flex items-center gap-3 rounded-xl bg-lime/10 px-4 py-2.5">
              <FileText size={18} className="shrink-0 text-lime-ink" />
              <p className="flex-1 text-sm text-ink">
                Employers receive your uploaded PDF. Template preview below is for editing and ATS scoring.
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => api.downloadCvFile("uploaded").catch((e) => toast.error(e.message))}
              >
                <Download size={14} />
                Download
              </Button>
            </div>
          )}
        </Card>
      )}

      {!embedded && ats && (
        <AtsScoreCard ats={ats} onImprove={() => setTab("edit")} compact />
      )}

      <div className="flex flex-wrap gap-2">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-base font-bold transition ${
              tab === id ? "bg-lime text-ink" : "bg-white text-stone hover:bg-mist/50"
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
        {!embedded && (
          <Button variant="ghost" size="sm" onClick={() => refresh()} disabled={loading} className="ml-auto">
            <RefreshCw size={16} />
            Refresh
          </Button>
        )}
      </div>

      {tab === "preview" && (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <div className="mb-3 flex items-center justify-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => setShowPdf(true)}
                className={`rounded-full px-3 py-1 font-bold transition ${
                  showPdf ? "bg-ink text-white" : "text-stone hover:bg-mist/60"
                }`}
              >
                Compiled PDF
              </button>
              <button
                type="button"
                onClick={() => setShowPdf(false)}
                className={`rounded-full px-3 py-1 font-bold transition ${
                  !showPdf ? "bg-ink text-white" : "text-stone hover:bg-mist/60"
                }`}
              >
                Quick preview
              </button>
            </div>
            {showPdf ? (
              <CvPdfPreview version={pdfVersion} enabled={Boolean(artifacts?.has_pdf)} />
            ) : (
              <CvHtmlPreview
                html={previewHtml}
                loading={loading || previewLoading}
                allowMultiPage={pageTarget !== "1"}
              />
            )}
            <p className="mt-2 text-center text-sm text-stone">
              {showPdf
                ? artifacts?.has_pdf
                  ? `A4 · ${artifacts.page_count || "?"} page${
                      artifacts.page_count === 1 ? "" : "s"
                    }${artifacts.density ? ` · ${artifacts.density} spacing` : ""} — the file employers get`
                  : "Generate PDF to compile with your chosen Shortlistr template"
                : pageTarget === "1"
                  ? "Trying to fit one page — long CVs still open onto page 2 if type would get too small"
                  : "Long resumes open onto page 2 in this preview · PDF uses your Length setting"}
            </p>
          </div>
          <Card padding="lg" className="space-y-4 lg:col-span-2">
            <div>
              <h3 className="font-bold text-ink">Build PDF</h3>
              <p className="mt-1 text-sm text-stone">
                {activeTemplate?.name || "Shortlistr Classic"}
                {activeTemplate?.recommended ? " · recommended" : ""}
              </p>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-bold text-stone">Length</p>
              <div className="flex flex-wrap gap-2">
                {PAGE_TARGETS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    title={t.hint}
                    onClick={() => {
                      setPageTarget(t.id);
                    }}
                    className={`rounded-full border-2 px-3.5 py-2 text-sm font-bold transition ${
                      pageTarget === t.id
                        ? "border-lime bg-lime/10 text-ink"
                        : "border-mist bg-white text-stone hover:border-stone/30"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <p className="text-sm text-stone">
                Nothing is ever cut — if it will not fit, you are told instead.
              </p>
            </div>

            {!latexEngine && (
              <p className="rounded-xl bg-orange/10 px-3 py-2 text-sm text-ink">
                No LaTeX engine found — PDFs fall back to Chromium and may not match the template.
                Install with <code className="font-mono">brew install tectonic</code> (Connections also covers this).
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button variant="lime" size="sm" onClick={() => void handleGenerate()} isLoading={generating}>
                Generate PDF
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setTab("edit")}>
                <Pencil size={14} />
                Edit text
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setTab("templates")}>
                Change template
              </Button>
            </div>

            <div className="space-y-2 border-t border-mist pt-4">
              <p className="text-sm font-bold text-stone">Download</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!artifacts?.has_pdf}
                  onClick={() => api.downloadCvFile("pdf").catch((e) => toast.error(e.message))}
                >
                  <Download size={14} />
                  PDF
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!artifacts?.has_md}
                  onClick={() => api.downloadCvFile("md").catch((e) => toast.error(e.message))}
                >
                  Markdown
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!artifacts?.has_tex}
                  onClick={() => api.downloadCvFile("tex").catch((e) => toast.error(e.message))}
                >
                  LaTeX
                </Button>
              </div>
              <p className="text-sm text-stone">
                LaTeX is self-contained — drop it into Overleaf as-is.
              </p>
            </div>
            {!embedded && (
              <Button variant="danger" size="sm" onClick={handleDelete}>
                <Trash2 size={14} />
                Delete resume
              </Button>
            )}
          </Card>
        </div>
      )}

      {tab === "edit" && (
        <Card padding="lg" className="space-y-4">
          <p className="text-base text-stone">
            Plain markdown — used for job matching, cover letters, and Shortlistr PDF export.
          </p>
          <textarea
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
            rows={20}
            disabled={loading}
            className="w-full rounded-2xl border border-mist bg-sage/20 p-4 font-mono text-sm leading-relaxed text-ink outline-none focus:border-lime/40"
            placeholder={"# Your Name\n\n**Role title**\n\n## Professional Summary\n…"}
          />
          <div className="flex flex-wrap gap-3">
            <Button variant="lime" onClick={handleSave} isLoading={saving}>
              Save
            </Button>
            <Button variant="secondary" onClick={() => void handleGenerate()} isLoading={generating}>
              Save & generate PDF
            </Button>
            <Button variant="ghost" onClick={() => setTab("preview")}>
              Cancel
            </Button>
          </div>
          {ats && <AtsScoreCard ats={ats} compact />}
        </Card>
      )}

      {tab === "templates" && (
        <div className="flex flex-col gap-5 lg:grid lg:grid-cols-5 lg:items-start lg:gap-6">
          {/* Preview first in the DOM so mobile users see it above the list;
              sticky on desktop so browsing the last templates never scrolls it away. */}
          <div className="order-1 lg:order-2 lg:col-span-3">
            <div
              id="cv-template-preview"
              className="sticky top-3 z-10 space-y-3 rounded-2xl border border-mist bg-sage/30 p-3 sm:p-4 lg:top-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-bold text-ink">
                    Live preview · {activeTemplate?.name || "Template"}
                  </p>
                  <p className="text-xs text-stone">
                    {activeTemplate?.recommended ? "Recommended · " : ""}
                    {activeTemplate?.description || "Select a design on the left"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openTemplatePreview(templateId)}
                    disabled={!templateId}
                  >
                    <Eye size={14} />
                    Enlarge
                  </Button>
                  <Button
                    variant="lime"
                    size="sm"
                    onClick={() => void handleGenerate(templateId)}
                    isLoading={generating}
                    disabled={!templateId}
                  >
                    Use & generate
                  </Button>
                </div>
              </div>
              <CvHtmlPreview
                html={previewHtml}
                loading={previewLoading}
                allowMultiPage={pageTarget !== "1"}
                emptyMessage="Pick a Shortlistr template to preview your resume."
              />
              {activeTemplate?.ats_notes && (
                <p className="text-xs text-stone">{activeTemplate.ats_notes}</p>
              )}
            </div>
          </div>

          <div className="order-2 space-y-3 lg:order-1 lg:col-span-2">
            <p className="text-sm text-stone">
              All designs are single-column and ATS-safe. Scroll the list — the preview stays put.
            </p>
            <div className="max-h-[min(58vh,560px)] space-y-2 overflow-y-auto overscroll-contain rounded-2xl border border-mist bg-white/60 p-2 lg:max-h-[min(72vh,780px)]">
              {sortedTemplates.map((t) => {
                const selected = templateId === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    className={`w-full rounded-xl border px-3 py-2.5 text-left transition ${
                      selected
                        ? "border-lime bg-lime/10 ring-1 ring-lime/30"
                        : "border-transparent bg-white hover:border-mist hover:bg-mist/40"
                    }`}
                    onClick={() => {
                      setTemplateId(t.id);
                      void loadPreview(t.id);
                      // On small screens the preview sits above; nudge into view after pick.
                      if (typeof window !== "undefined" && window.innerWidth < 1024) {
                        document
                          .getElementById("cv-template-preview")
                          ?.scrollIntoView({ behavior: "smooth", block: "start" });
                      }
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <p className="min-w-0 flex-1 truncate font-bold text-ink">{t.name}</p>
                      {t.recommended && (
                        <span className="shrink-0 rounded-full bg-ink px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                          Rec
                        </span>
                      )}
                      {selected && <Check size={16} className="shrink-0 text-lime-ink" />}
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-stone">{t.description}</p>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <Modal
        isOpen={!!previewModal}
        onClose={() => setPreviewModal(null)}
        title="Template preview"
        size="xl"
      >
        <CvHtmlPreview
          html={previewModal}
          loading={false}
          allowMultiPage={pageTarget !== "1"}
        />
      </Modal>
    </div>
  );
}
