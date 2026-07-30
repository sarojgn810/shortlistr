"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Eye, FileText, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { Modal } from "@/src/components/ui/Modal";
import { AtsScoreCard } from "@/src/components/cv/AtsScoreCard";
import { CvHtmlPreview } from "@/src/components/cv/CvHtmlPreview";
import { CvPdfPreview } from "@/src/components/cv/CvPdfPreview";
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

  const loadPreview = useCallback(
    async (tpl: string, md?: string) => {
      setPreviewLoading(true);
      try {
        const content = (md ?? markdown).trim();
        const res = await api.previewCv(
          tpl,
          content || undefined,
          !content
        );
        setPreviewHtml(res.html);
      } catch {
        setPreviewHtml(null);
      } finally {
        setPreviewLoading(false);
      }
    },
    [markdown]
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
  }, [tab, templateId, loadPreview]);

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

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await api.generateCv(templateId, markdown, pageTarget);
      const newAts = res.ats as AtsScore;
      setAts(newAts);
      onGenerated?.(newAts);
      if (res.fitted) {
        toast.success(`Resume generated — ${res.pages} page${res.pages === 1 ? "" : "s"}`);
      } else {
        // Saying "done" when the requested page count was not met is how a
        // user finds out at the worst possible moment. Say what happened.
        toast.warning(
          `Could not fit ${res.page_target} page${res.page_target === 1 ? "" : "s"} — ` +
            `generated ${res.pages}. Trim a role or a few bullets in Edit.`
        );
      }
      const arts = await api.getCvArtifacts();
      setArtifacts(arts);
      setPdfVersion((v) => v + 1);
      await loadPreview(templateId);
      setTab("preview");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Generate failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Delete your saved resume? You can paste a new one anytime.")) return;
    try {
      await api.deleteCv();
      setMarkdown("");
      setPreviewHtml(null);
      setAts(null);
      setArtifacts(null);
      toast.message("Resume cleared");
      setTab("edit");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Delete failed");
    }
  };

  const openTemplatePreview = async (id: string) => {
    try {
      const res = await api.previewCv(id, markdown.trim() || undefined, !markdown.trim());
      setPreviewModal(res.html);
    } catch {
      toast.error("Preview failed");
    }
  };

  const tabs: { id: Tab; label: string; icon: typeof Eye }[] = [
    { id: "preview", label: "Preview", icon: Eye },
    { id: "edit", label: "Edit", icon: Pencil },
    { id: "templates", label: "Templates", icon: FileText },
  ];

  return (
    <div className={embedded ? "space-y-4" : "space-y-6"}>
      {!embedded && hasUploaded && (
        <Card padding="lg" className="space-y-3">
          <p className="text-sm font-bold text-stone">
            Resume sent to employers
          </p>
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
              <p className="mt-1 text-base text-stone">Your original file, sent as-is.</p>
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
                <Pencil size={16} className="mr-1.5 inline" />
                Generated template
              </p>
              <p className="mt-1 text-base text-stone">ATS-formatted from the template below.</p>
            </button>
          </div>
          {resumeSource === "uploaded" && (
            <div className="flex items-center gap-3 rounded-xl bg-lime/10 px-4 py-2.5">
              <FileText size={18} className="shrink-0 text-lime-ink" />
              <p className="flex-1 text-base text-ink">
                Employers receive your uploaded PDF. The template preview below is for reference only.
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
              <CvHtmlPreview html={previewHtml} loading={loading || previewLoading} />
            )}
            <p className="mt-2 text-center text-base text-stone">
              {showPdf
                ? artifacts?.has_pdf
                  ? `A4 · ${artifacts.page_count || "?"} page${
                      artifacts.page_count === 1 ? "" : "s"
                    }${artifacts.density ? ` · ${artifacts.density} spacing` : ""} — the exact file employers get`
                  : "Regenerate to compile the PDF"
                : "Approximate — a separate renderer, useful for comparing templates quickly"}
            </p>
          </div>
          <Card padding="lg" className="space-y-4 lg:col-span-2">
            <h3 className="font-bold text-ink">Your final resume</h3>
            <p className="text-base text-stone">
              Template: <strong>{templates.find((t) => t.id === templateId)?.name ?? templateId}</strong>
            </p>

            <div className="space-y-2">
              <p className="text-sm font-bold text-stone">Length</p>
              <div className="flex flex-wrap gap-2">
                {PAGE_TARGETS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    title={t.hint}
                    onClick={() => setPageTarget(t.id)}
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
                {PAGE_TARGETS.find((t) => t.id === pageTarget)?.hint}. Nothing is ever cut — if it
                will not fit, you are told instead.
              </p>
            </div>

            {!latexEngine && (
              <p className="rounded-xl bg-orange/10 px-3 py-2 text-sm text-ink">
                No LaTeX engine found, so PDFs are rendered by Chromium and will not match the
                template exactly. Install one with <code>brew install tectonic</code>.
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={() => setTab("edit")}>
                <Pencil size={14} />
                Edit
              </Button>
              <Button variant="lime" size="sm" onClick={handleGenerate} isLoading={generating}>
                Regenerate
              </Button>
            </div>
            {!hasUploaded && (
              <div className="space-y-2 border-t border-mist pt-4">
                <p className="text-sm text-stone">
                  Upload a PDF on the Resume page to use your own file instead of a generated template.
                </p>
              </div>
            )}
            <div className="space-y-2 border-t border-mist pt-4">
              <p className="text-sm font-bold text-stone">Download template</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!artifacts?.has_md}
                  onClick={() => api.downloadCvFile("md").catch((e) => toast.error(e.message))}
                >
                  <Download size={14} />
                  Markdown
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!artifacts?.has_tex}
                  onClick={() => api.downloadCvFile("tex").catch((e) => toast.error(e.message))}
                >
                  <Download size={14} />
                  LaTeX
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!artifacts?.has_pdf}
                  onClick={() => api.downloadCvFile("pdf").catch((e) => toast.error(e.message))}
                >
                  <Download size={14} />
                  PDF
                </Button>
              </div>
              {!artifacts?.has_pdf && (
                <p className="text-sm text-stone">Click Regenerate to compile the PDF.</p>
              )}
              <p className="text-sm text-stone">
                The LaTeX file is self-contained — it compiles on Overleaf as-is.
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
            Plain markdown — used for job matching, cover letters, and PDF export.
          </p>
          <textarea
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
            rows={20}
            disabled={loading}
            className="w-full rounded-2xl border border-mist bg-sage/20 p-4 font-mono text-sm leading-relaxed text-ink outline-none focus:border-lime/40"
          />
          <div className="flex flex-wrap gap-3">
            <Button variant="lime" onClick={handleSave} isLoading={saving}>
              Save
            </Button>
            <Button variant="secondary" onClick={() => setTab("preview")}>
              Cancel
            </Button>
          </div>
          {ats && <AtsScoreCard ats={ats} compact />}
        </Card>
      )}

      {tab === "templates" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            {templates.map((t) => (
              <div
                key={t.id}
                className={`rounded-2xl border p-4 transition ${
                  templateId === t.id ? "border-lime bg-lime/10" : "border-mist bg-white"
                }`}
              >
                <button type="button" className="w-full text-left" onClick={() => setTemplateId(t.id)}>
                  <p className="font-bold text-ink">{t.name}</p>
                  <p className="mt-1 text-sm text-stone">{t.description}</p>
                </button>
                <div className="mt-3 flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => openTemplatePreview(t.id)}>
                    <Eye size={14} />
                    View
                  </Button>
                  {templateId === t.id && (
                    <Button variant="lime" size="sm" onClick={handleGenerate} isLoading={generating}>
                      Use this
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <CvHtmlPreview
            html={previewHtml}
            loading={previewLoading}
            emptyMessage="Pick a template to see your resume."
          />
        </div>
      )}

      <Modal
        isOpen={!!previewModal}
        onClose={() => setPreviewModal(null)}
        title="Template preview"
        size="xl"
      >
        {previewModal && <CvHtmlPreview html={previewModal} className="h-[70vh]" />}
      </Modal>
    </div>
  );
}
