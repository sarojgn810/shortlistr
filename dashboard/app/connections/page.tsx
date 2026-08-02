"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Brain, Globe, Mail, MessageSquare, Server, ChevronDown, ChevronUp,
  CheckCircle2, XCircle, AlertCircle, ExternalLink,
  Pencil, Save, X, Plus, Trash2, Download, Upload, HelpCircle, Radar,
} from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import PortalsFingerprintPanel from "@/src/components/connections/PortalsFingerprintPanel";
import { Card } from "@/src/components/ui/Card";
import { Button } from "@/src/components/ui/Button";
import { useProfile } from "@/src/hooks/useProfile";
import { useSetupStatus } from "@/src/hooks/useSetupStatus";
import {
  api,
  ApiError,
  type ConnectionsSetup,
  type McpServerConfig,
} from "@/src/lib/api/client";

// ─── Status chip ──────────────────────────────────────────────────────────────

type StatusKind = "active" | "missing" | "optional" | "unknown";

function StatusChip({ kind, label }: { kind: StatusKind; label: string }) {
  const cls =
    kind === "active"   ? "bg-lime/20 text-lime-ink" :
    kind === "missing"  ? "bg-orange/15 text-orange" :
    kind === "optional" ? "bg-mist text-stone" :
                          "bg-mist/60 text-stone/60";
  const Icon =
    kind === "active"  ? CheckCircle2 :
    kind === "missing" ? XCircle :
                         AlertCircle;
  return (
    <span className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold ${cls}`}>
      <Icon size={13} />
      {label}
    </span>
  );
}

/** What is connected, before eleven sections of detail.
 *
 * Every section looked equally important and nothing said which of them the app
 * actually needs, so finding out whether scoring was on meant scrolling and
 * reading. Two of these change what Shortlistr can do; the rest are additions.
 * Each unconnected row says what that costs rather than just showing a gap.
 */
function SetupSummary({
  items,
}: {
  items: { label: string; done: boolean; essential: boolean; missing: string }[];
}) {
  const essentials = items.filter((i) => i.essential);
  const allEssential = essentials.every((i) => i.done);
  return (
    <Card padding="lg" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-ink">
          {allEssential ? "You're set up" : "Two free keys turn everything on"}
        </h2>
        <span className="text-sm font-bold text-stone">
          {items.filter((i) => i.done).length} of {items.length} connected
        </span>
      </div>
      {!allEssential && (
        <p className="text-base leading-relaxed text-stone">
          Shortlistr finds jobs with your profile alone. Neither of the two
          recommended keys asks for a card, and both have daily limits that suit
          one person&apos;s job search.
        </p>
      )}
      <ul className="grid gap-2.5 sm:grid-cols-2">
        {items.map((i) => (
          <li
            key={i.label}
            className={`rounded-xl border p-3 ${
              i.done ? "border-lime/40 bg-lime/5" : "border-mist bg-white"
            }`}
          >
            <div className="flex items-center gap-2">
              {i.done ? (
                <CheckCircle2 size={15} className="shrink-0 text-lime-ink" />
              ) : (
                <AlertCircle size={15} className="shrink-0 text-stone/60" />
              )}
              <span className="text-sm font-bold text-ink">{i.label}</span>
              {i.essential && !i.done && (
                <span className="rounded-full bg-lime/20 px-2 py-0.5 text-[11px] font-bold text-lime-ink">
                  Recommended
                </span>
              )}
            </div>
            {!i.done && (
              <p className="mt-1 pl-[23px] text-xs leading-relaxed text-stone">{i.missing}</p>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}


function ConnectorSection({
  icon: Icon,
  title,
  subtitle,
  children,
  defaultOpen = true,
}: {
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card padding="lg" className="space-y-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ink/5">
            <Icon size={19} className="text-ink" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-ink">{title}</h2>
            {subtitle && <p className="mt-1 text-sm leading-relaxed text-stone">{subtitle}</p>}
          </div>
        </div>
        {open ? <ChevronUp size={18} className="mt-1 shrink-0 text-stone" /> : <ChevronDown size={18} className="mt-1 shrink-0 text-stone" />}
      </button>
      {open && children}
    </Card>
  );
}

function ConnectorRow({
  name, note, kind, label, children,
}: {
  name: string;
  note?: string;
  kind: StatusKind;
  label: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="space-y-4 rounded-2xl border border-mist/60 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-[15rem] flex-1">
          <p className="text-base font-bold text-ink">{name}</p>
          {note && <p className="mt-1 text-sm leading-relaxed text-stone">{note}</p>}
        </div>
        <StatusChip kind={kind} label={label} />
      </div>
      {children}
    </div>
  );
}

function Field({
  label, children, hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-semibold text-ink">{label}</label>
      {children}
      {hint && <div className="text-sm leading-relaxed text-stone">{hint}</div>}
    </div>
  );
}

function HelpDetails({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="rounded-xl border border-mist/80 bg-mist/30 px-4 py-3">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-bold text-ink">
        <HelpCircle size={15} className="shrink-0 text-stone" />
        {title}
      </summary>
      <div className="mt-2.5 space-y-2 text-sm leading-relaxed text-stone">{children}</div>
    </details>
  );
}

/** What to paste into the engine's "Sites to search".
 *
 * Google retired "Search the entire web" for new Programmable Search Engines on
 * 20 January 2026 — a new engine must name up to 50 domains instead. These are
 * the hosts prep/research.py already filters results down to, so naming them
 * costs nothing.
 *
 * Two of Google's documented forms are used, and mixing them up is what
 * produces "invalid format":
 *   - "*.example.com" is Entire domain, and only works on a registrable domain
 *   - "sub.example.com/*" is Entire site, which is how a single subdomain is
 *     named without claiming the parent
 *
 * Nothing here may be a public suffix. github.io is one — it hands a domain to
 * every user exactly like blogspot.com — so it is absent despite the learning
 * filter accepting it; those pages still arrive via github.com.
 */
const CSE_SITES = [
  "*.kubernetes.io",
  "*.prometheus.io",
  "*.grafana.com",
  "*.opentelemetry.io",
  "*.terraform.io",
  "*.hashicorp.com",
  "*.github.com",
  "*.sre.google",
  "*.martinfowler.com",
  "*.highscalability.com",
  "*.arxiv.org",
  "*.coursera.org",
  "*.edx.org",
  "*.udacity.com",
  "*.pluralsight.com",
  "*.oreilly.com",
  "*.manning.com",
  "*.interviewing.io",
  "*.educative.io",
  "*.glassdoor.com",
  "*.levels.fyi",
  "*.teamblind.com",
  "*.reddit.com",
  "*.medium.com",
  "*.dev.to",
  "*.stackoverflow.com",
  "*.pragmaticengineer.com",
  "*.ycombinator.com",
  "aws.amazon.com/*",
  "cloud.google.com/*",
  "learn.microsoft.com/*",
  "docs.docker.com/*",
] as const;

const inputCls =
  "w-full rounded-xl border border-mist bg-white px-3.5 py-2.5 text-base text-ink outline-none focus:border-lime/60 placeholder:text-stone/40";

/** Forms sit in a readable column instead of stretching across a wide screen. */
const formCls = "max-w-3xl space-y-4";
/** An account pair (address + password) reads as one unit on a wide screen. */
const pairCls = "grid gap-4 sm:grid-cols-2";

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ConnectionsPage() {
  const { profile, isSaving: llmSaving, save } = useProfile();
  const { status, refetch: refetchStatus } = useSetupStatus();

  const [conn, setConn] = useState<ConnectionsSetup | null>(null);
  const [connLoading, setConnLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const [editingLlm, setEditingLlm] = useState(false);
  const [llmDraft, setLlmDraft] = useState({ provider: "", model: "", api_key: "" });

  const [liEmail, setLiEmail] = useState("");
  const [liPassword, setLiPassword] = useState("");
  const [nkEmail, setNkEmail] = useState("");
  const [nkPassword, setNkPassword] = useState("");
  const [gmailSender, setGmailSender] = useState("");
  const [gmailPassword, setGmailPassword] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [apifyToken, setApifyToken] = useState("");
  const [apifyEnabled, setApifyEnabled] = useState(false);
  const [pageReaderEnabled, setPageReaderEnabled] = useState(false);
  const [emailVerifyKey, setEmailVerifyKey] = useState("");
  const [emailVerifyProvider, setEmailVerifyProvider] = useState("hunter");
  const [serperKey, setSerperKey] = useState("");
  const [googleCseKey, setGoogleCseKey] = useState("");
  const [searchTest, setSearchTest] = useState<{ ok: boolean; message: string } | null>(null);
  const [testingSearch, setTestingSearch] = useState(false);
  const [googleCseCx, setGoogleCseCx] = useState("");

  // "Saved" is not "working": a key can be an OAuth client ID, belong to a
  // project without the API enabled, or be restricted to other APIs. One real
  // query tells the difference in a second instead of hours later.
  const runSearchTest = async () => {
    setTestingSearch(true);
    setSearchTest(null);
    try {
      const res = await api.testSearch();
      setSearchTest({ ok: res.ok, message: res.message });
    } catch (e) {
      setSearchTest({
        ok: false,
        message: e instanceof ApiError ? e.message : "Could not reach the API",
      });
    } finally {
      setTestingSearch(false);
    }
  };
  const [githubToken, setGithubToken] = useState("");
  const [mcpDraft, setMcpDraft] = useState<McpServerConfig[]>([]);
  const credsInputRef = useRef<HTMLInputElement>(null);

  const [localAiModel, setLocalAiModel] = useState("");
  const [showLocalGuide, setShowLocalGuide] = useState(true);

  const llmStatus = status?.llm;

  const applyConn = useCallback((data: ConnectionsSetup) => {
    setConn(data);
    setLiEmail(data.linkedin.email);
    setNkEmail(data.naukri.email);
    setGmailSender(data.gmail.sender || profile?.email || "");
    setMcpDraft(data.mcp_servers.map((s) => ({ ...s, args: [...(s.args || [])] })));
    setLiPassword("");
    setNkPassword("");
    setGmailPassword("");
    setTelegramToken("");
    setApifyToken("");
    setApifyEnabled(Boolean(data.apify?.enabled));
    setPageReaderEnabled(Boolean(data.page_reader?.enabled));
    setEmailVerifyKey("");
    setEmailVerifyProvider(data.email_verify?.provider || "hunter");
    setSerperKey("");
    setGoogleCseKey("");
    setGoogleCseCx("");
    setGithubToken("");
    const rec = data.local_ai?.capability?.recommended_model || data.local_ai?.model || "";
    if (rec) setLocalAiModel((cur) => cur || rec);
  }, [profile?.email]);

  const loadConnections = useCallback(async () => {
    setConnLoading(true);
    try {
      applyConn(await api.getConnections());
    } catch {
      toast.error("Could not load connections — is the API running?");
    } finally {
      setConnLoading(false);
    }
  }, [applyConn]);

  useEffect(() => {
    void loadConnections();
  }, [loadConnections]);

  // Poll while Local AI is installing / downloading.
  useEffect(() => {
    const phase = conn?.local_ai?.phase;
    if (!phase || !["installing", "pulling", "starting"].includes(phase)) return;
    const id = window.setInterval(() => {
      void api.getLocalAi().then((local_ai) => {
        setConn((c) => (c ? { ...c, local_ai } : c));
        if (local_ai.ready) {
          void refetchStatus();
          toast.success("Local AI is ready — jobs will use on-device scoring");
        }
      }).catch(() => {});
    }, 3000);
    return () => window.clearInterval(id);
  }, [conn?.local_ai?.phase, refetchStatus]);

  const saveConn = async (key: string, body: Parameters<typeof api.saveConnections>[0]) => {
    setSavingKey(key);
    try {
      applyConn(await api.saveConnections(body));
      toast.success("Saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setSavingKey(null);
    }
  };

  const startLlmEdit = () => {
    const provider = profile?.llm_provider || llmStatus?.provider || "auto";
    let model = profile?.llm_model || llmStatus?.model || "";
    // Don't seed an Ollama tag into a cloud provider draft.
    if (
      ["groq", "openai", "anthropic", "gemini", "grok"].includes(provider) &&
      (model.includes(":") || !model)
    ) {
      model = provider === "groq" ? "llama-3.3-70b-versatile" : "";
    }
    if ((provider === "ollama" || provider === "auto") && !model) {
      model = "qwen2.5:0.5b";
    }
    setLlmDraft({
      provider,
      model,
      api_key: "",
    });
    setEditingLlm(true);
  };

  const saveLlm = async () => {
    try {
      let model = llmDraft.model.trim();
      const provider = llmDraft.provider;
      if (
        ["groq", "openai", "anthropic", "gemini", "grok"].includes(provider) &&
        (model.includes(":") || !model)
      ) {
        model = provider === "groq" ? "llama-3.3-70b-versatile" : "";
      }
      await save({
        llm_provider: provider,
        llm_model: model,
        ...(llmDraft.api_key ? { llm_api_key: llmDraft.api_key } : {}),
      });
      await refetchStatus();
      setEditingLlm(false);
      toast.success("AI connection saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed");
    }
  };

  const installPlaywright = async () => {
    setSavingKey("playwright");
    const pending = toast.message("Installing browser — one to two minutes…");
    try {
      const result = await api.installPlaywright();
      setConn((c) => (c ? { ...c, playwright: result.playwright } : c));
      await refetchStatus();
      toast.dismiss(pending);
      toast.success("Browser installed — form filling is ready");
    } catch (e) {
      toast.dismiss(pending);
      toast.error(e instanceof ApiError ? e.message : "Install failed");
    } finally {
      setSavingKey(null);
    }
  };

  const setupLocalAi = async () => {
    setSavingKey("local-ai");
    try {
      const result = await api.ensureLocalAi(true, localAiModel || undefined);
      setConn((c) => (c ? { ...c, local_ai: result.local_ai } : c));
      toast.message(result.local_ai.message || "Setting up Local AI…");
      await refetchStatus();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Local AI setup failed");
    } finally {
      setSavingKey(null);
    }
  };

  const onCredsFile = async (file: File | null) => {
    if (!file) return;
    setSavingKey("gmail-creds");
    try {
      applyConn(await api.uploadGmailCredentials(file));
      toast.success("File uploaded — next, click Connect Gmail");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setSavingKey(null);
      if (credsInputRef.current) credsInputRef.current.value = "";
    }
  };

  const connectGmail = async () => {
    setSavingKey("gmail-connect");
    const pending = toast.message("A browser window will open — sign in with Google…");
    try {
      applyConn(await api.connectGmail());
      toast.dismiss(pending);
      toast.success("Gmail connected");
    } catch (e) {
      toast.dismiss(pending);
      toast.error(e instanceof ApiError ? e.message : "Could not connect Gmail");
    } finally {
      setSavingKey(null);
    }
  };

  const llmKind: StatusKind =
    llmStatus?.available ? "active" :
    profile?.llm_api_key_set ? "missing" :
    "missing";
  const llmLabel =
    llmStatus?.available ? "Ready" :
    llmStatus?.mode === "template" ? "Using basic mode" :
    "Not set up";

  const playwright = conn?.playwright.installed ?? !!status?.checks?.playwright;

  return (
    <DashboardShell title="Connections" breadcrumbs={["Home", "Connections"]}>
      <div className="w-full space-y-6">
        <SetupSummary
          items={[
            {
              label: "AI scoring",
              done: Boolean(llmStatus?.api_key_set || conn?.local_ai?.ready),
              essential: true,
              missing: "Every job shows “Basic score” — keyword matching, no A–G analysis",
            },
            {
              label: "Web search",
              done: Boolean(conn?.google_cse?.ready),
              essential: true,
              missing: "Interview research and the prep reading list stay empty",
            },
            {
              label: "Extra job boards",
              done: Boolean(conn?.apify?.ready),
              essential: false,
              missing: "LinkedIn, Naukri and Indeed are not searched",
            },
            {
              label: "Email",
              done: Boolean(conn?.gmail?.app_password_set || conn?.gmail?.token_present),
              essential: false,
              missing: "Job-alert emails are not imported",
            },
          ]}
        />

        {/* ── 1. AI ───────────────────────────────────────────────────── */}
        <ConnectorSection
          icon={Brain}
          title="AI helper"
          subtitle="Recommended: a free Google Gemini key (aistudio.google.com/apikey — no card, ~1,500 requests/day on gemini-2.0-flash). Auto uses your key first and falls back to Local AI only if you have set it up. Without either, scoring stays keyword-only."
        >
          {(() => {
            const la = conn?.local_ai;
            const cap = la?.capability;
            const busy = !!la && ["installing", "pulling", "starting"].includes(la.phase);
            const laKind: StatusKind = la?.ready ? "active" : busy ? "optional" : "missing";
            const laLabel = la?.ready ? "Ready" : busy ? "Setting up…" : la?.error ? "Needs attention" : "Not set up";
            const models = cap?.models || [];
            const guide = cap?.guide || [];
            const selected = localAiModel || cap?.recommended_model || la?.model || "";
            return (
              <ConnectorRow
                name="Local AI on this computer (advanced)"
                note={
                  "Runs offline with no account, but the models a laptop can run are much " +
                  "weaker at scoring than a free cloud key — expect thinner A–G analysis, and " +
                  "on smaller machines a fallback to basic scoring. Prefer a Gemini key unless " +
                  "you specifically need offline. " +
                  (cap?.system?.summary || la?.message || "")
                }
                kind={laKind}
                label={laLabel}
              >
                <div className="space-y-4">
                  {cap?.system && (
                    <div className="rounded-xl bg-sage/30 px-3 py-2 text-sm text-stone">
                      <p className="font-bold text-ink">Your computer</p>
                      <p className="mt-0.5">{cap.system.summary}</p>
                      {cap.system.tier_label && (
                        <p className="mt-1 text-stone/80">{cap.system.tier_label}</p>
                      )}
                    </div>
                  )}

                  {!la?.ready && models.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-bold text-ink">Choose a model for this machine</p>
                      <div className="space-y-2">
                        {models.map((m) => {
                          const disabled = m.fit === "heavy";
                          const active = selected === m.id;
                          return (
                            <label
                              key={m.id}
                              className={`flex cursor-pointer gap-3 rounded-xl border px-3 py-2.5 text-sm ${
                                active ? "border-lime bg-lime/10" : "border-mist bg-white"
                              } ${disabled ? "opacity-60" : ""}`}
                            >
                              <input
                                type="radio"
                                name="local-ai-model"
                                className="mt-1"
                                checked={active}
                                disabled={disabled || busy}
                                onChange={() => setLocalAiModel(m.id)}
                              />
                              <span className="min-w-0 flex-1">
                                <span className="flex flex-wrap items-center gap-2 font-bold text-ink">
                                  {m.name}
                                  {m.recommended && (
                                    <span className="rounded-md bg-lime/30 px-1.5 py-0.5 text-xs font-bold text-ink">
                                      Best for you
                                    </span>
                                  )}
                                </span>
                                <span className="mt-0.5 block text-stone">
                                  {m.fit_label} · ~{m.download_mb} MB · {m.quality}
                                </span>
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {guide.length > 0 && (
                    <div className="space-y-2">
                      <button
                        type="button"
                        className="flex items-center gap-1 text-sm font-bold text-ink underline"
                        onClick={() => setShowLocalGuide((v) => !v)}
                      >
                        {showLocalGuide ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        Step-by-step guide
                      </button>
                      {showLocalGuide && (
                        <ol className="space-y-2 rounded-xl border border-mist bg-white px-4 py-3 text-sm text-stone">
                          {guide.map((step, i) => (
                            <li key={step.title} className="flex gap-2">
                              <span className="font-bold text-ink">{i + 1}.</span>
                              <span>
                                <span className="font-bold text-ink">{step.title}</span>
                                <span className="mt-0.5 block">{step.body}</span>
                              </span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>
                  )}

                  {la?.ready ? (
                    <p className="text-sm text-stone">
                      Ready{la.model ? ` · ${la.model}` : ""}. Shortlistr will use it for scoring and cover letters.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm text-stone">
                        {busy
                          ? "Downloading in the background — leave this page open. Takes a few minutes the first time."
                          : "One click — no terminal. We install the helper and download the model you picked."}
                      </p>
                      {la?.error && <p className="text-sm text-orange">{la.error}</p>}
                      <Button
                        variant="lime"
                        size="sm"
                        onClick={setupLocalAi}
                        isLoading={savingKey === "local-ai" || busy}
                      >
                        <Download size={13} />
                        {busy ? "Setting up…" : `Install ${selected || "recommended model"}`}
                      </Button>
                    </div>
                  )}
                </div>
              </ConnectorRow>
            );
          })()}

          <ConnectorRow
            name={
              llmStatus?.provider && llmStatus.provider !== "none"
                ? `Mode · ${llmStatus.provider}${
                    llmStatus.resolved_provider && llmStatus.resolved_provider !== llmStatus.provider
                      ? ` → ${llmStatus.resolved_provider}`
                      : ""
                  }${llmStatus.model ? ` · ${llmStatus.model}` : ""}`
                : "Scoring mode"
            }
            note="Auto = your API key first, then Local AI if it is set up, then keyword-only scoring. Pick a provider directly to pin it."
            kind={llmKind}
            label={llmLabel}
          >
            {!editingLlm ? (
              <Button variant="secondary" size="sm" onClick={startLlmEdit}>
                <Pencil size={13} /> Change
              </Button>
            ) : (
              <div className={formCls}>
                <Field label="Which AI do you want to use?">
                  <select
                    value={llmDraft.provider}
                    onChange={(e) => {
                      const provider = e.target.value;
                      setLlmDraft((d) => {
                        let model = d.model;
                        if (
                          ["groq", "openai", "anthropic", "gemini", "grok"].includes(provider) &&
                          (model.includes(":") || !model)
                        ) {
                          model = provider === "groq" ? "llama-3.3-70b-versatile" : "";
                        }
                        if ((provider === "ollama" || provider === "auto") && model && !model.includes(":")) {
                          model = "qwen2.5:0.5b";
                        }
                        return { ...d, provider, model };
                      });
                    }}
                    className={inputCls}
                  >
                    <option value="auto">Auto — your key first, then Local AI (recommended)</option>
                    <option value="gemini">Google Gemini — free tier, no card</option>
                    <option value="groq">Groq — free tier, fastest</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="grok">xAI Grok</option>
                    <option value="ollama">Ollama — advanced, runs on this computer</option>
                    <option value="none">None — basic scoring only</option>
                  </select>
                </Field>
                {llmDraft.provider !== "none" && llmDraft.provider !== "ollama" && llmDraft.provider !== "auto" && (
                  <div className={pairCls}>
                    <Field label="Model name (optional)" hint="Leave blank to use the default for that provider.">
                      <input value={llmDraft.model} onChange={(e) => setLlmDraft({ ...llmDraft, model: e.target.value })}
                        placeholder="e.g. llama-3.3-70b-versatile"
                        className={inputCls} />
                    </Field>
                    <Field label="API key" hint="Paste the key from the provider’s website. We store it in your computer’s password vault — not in any shared file.">
                      <input type="password" value={llmDraft.api_key} onChange={(e) => setLlmDraft({ ...llmDraft, api_key: e.target.value })}
                        placeholder="Paste your key here"
                        className={inputCls} autoComplete="off" />
                    </Field>
                  </div>
                )}
                {(llmDraft.provider === "ollama" || llmDraft.provider === "auto") && (
                  <p className="text-sm text-stone">
                    Use <strong className="font-bold text-ink">Set up Local AI</strong> above — no API key needed.
                  </p>
                )}
                <div className="flex gap-2">
                  <Button variant="lime" size="sm" onClick={saveLlm} isLoading={llmSaving}><Save size={13} /> Save</Button>
                  <Button variant="ghost" size="sm" onClick={() => setEditingLlm(false)}><X size={13} /> Cancel</Button>
                </div>
              </div>
            )}
          </ConnectorRow>
        </ConnectorSection>

        {/* ── Web search: free, and three features depend on it ─────── */}
        <ConnectorSection
          icon={Globe}
          title="Web search (recommended)"
          subtitle="One free key, three features. Takes about two minutes."
        >
          <ConnectorRow
            name="Google Custom Search — recommended"
            note="Free, no card, ~100 queries/day. Unlocks three things at once: the interview-prep reading list, the 'how this company interviews' section, and web job search. Without it those stay empty — the free DuckDuckGo fallback is usually blocked by a bot challenge. Prefer this over Serper, which is paid."
            kind={conn?.google_cse?.ready ? "active" : "optional"}
            label={conn?.google_cse?.ready ? "Ready" : "Recommended · free"}
          >
            <div className={formCls}>
              <ol className="list-decimal space-y-1.5 pl-4 text-xs leading-relaxed text-stone">
                <li>
                  Create a search engine at{" "}
                  <a
                    href="https://programmablesearchengine.google.com/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold text-ink underline"
                  >
                    Programmable Search Engine
                  </a>
                  {" "}. Give it any name, then paste the site list below into
                  “Sites to search”.
                  <div className="mt-1.5 rounded-lg border border-mist bg-mist/30 p-2">
                    <p className="text-[11px] leading-relaxed text-stone">
                      Google removed “Search the entire web” for new engines on
                      20 Jan 2026 — every new engine must name up to 50 domains.
                      These are the sites Shortlistr actually searches, so
                      naming them is no loss.{" "}
                      <strong className="text-ink">
                        Paste one line at a time and press Add
                      </strong>{" "}
                      — the box takes a single pattern, and pasting the whole
                      list at once gives “invalid format”. Fewer is fine; you
                      can add the rest later.
                    </p>
                    <textarea
                      readOnly
                      onFocus={(e) => e.currentTarget.select()}
                      className="mt-1.5 h-28 w-full resize-y rounded-md border border-mist bg-white p-2 font-mono text-[11px] text-ink"
                      value={CSE_SITES.join("\n")}
                    />
                  </div>
                </li>
                <li>
                  Copy the <span className="font-semibold text-ink">Search engine ID</span> (CX)
                  from the engine’s Overview. If you landed on a “Code” page
                  instead, it is the <code className="font-mono text-ink">cx=</code>{" "}
                  value inside that snippet — e.g.{" "}
                  <code className="font-mono text-ink">cx=522b7c8d34cb642b5</code>{" "}
                  means the ID is{" "}
                  <code className="font-mono text-ink">522b7c8d34cb642b5</code>.
                  Ignore the rest of the snippet; that is for embedding a search
                  box on a website.
                </li>
                <li>
                  <span className="font-semibold text-ink">Separately</span>,
                  create an API key at{" "}
                  <a
                    href="https://console.cloud.google.com/apis/credentials"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold text-ink underline"
                  >
                    Google Cloud → Credentials
                  </a>
                  {" "}and enable the{" "}
                  <a
                    href="https://console.cloud.google.com/apis/library/customsearch.googleapis.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold text-ink underline"
                  >
                    Custom Search API
                  </a>
                  . This is a different console from the one above — the search
                  engine page never shows an API key, which is why it looks like
                  it is missing. Enable the API first, then create the key.
                </li>
              </ol>
              <Field label="API key">
                <input
                  type="password"
                  value={googleCseKey}
                  onChange={(e) => setGoogleCseKey(e.target.value)}
                  placeholder={
                    conn?.google_cse?.api_key_set ? "•••••••• (leave blank to keep)" : "AIza…"
                  }
                  className={inputCls}
                  autoComplete="off"
                />
              </Field>
              <Field label="Search engine ID (CX)">
                <input
                  type="text"
                  value={googleCseCx}
                  onChange={(e) => setGoogleCseCx(e.target.value)}
                  placeholder={
                    conn?.google_cse?.cx_set ? "•••••••• (leave blank to keep)" : "e.g. a1b2c3d4e5f6g7h8i"
                  }
                  className={inputCls}
                  autoComplete="off"
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="lime"
                  size="sm"
                  isLoading={savingKey === "google-cse"}
                  onClick={() =>
                    saveConn("google-cse", {
                      ...(googleCseKey ? { google_cse_api_key: googleCseKey } : {}),
                      ...(googleCseCx ? { google_cse_cx: googleCseCx } : {}),
                    })
                  }
                >
                  <Save size={13} /> Save
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  isLoading={testingSearch}
                  onClick={runSearchTest}
                >
                  Test it
                </Button>
              </div>
              {searchTest && (
                <div
                  className={`rounded-xl border p-3 text-sm leading-relaxed ${
                    searchTest.ok
                      ? "border-lime/40 bg-lime/10 text-ink"
                      : "border-orange/40 bg-orange/10 text-ink"
                  }`}
                >
                  {searchTest.message}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {(conn?.google_cse?.api_key_set || conn?.google_cse?.cx_set) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      saveConn("google-cse-clear", {
                        google_cse_api_key: "",
                        google_cse_cx: "",
                      })
                    }
                  >
                    Remove
                  </Button>
                )}
              </div>
            </div>
          </ConnectorRow>
        </ConnectorSection>

        {/* ── 2. Job boards (Apify) ───────────────────────────────────── */}
        <ConnectorSection
          icon={Radar}
          title="More job boards (recommended)"
          subtitle="LinkedIn, Naukri, Indeed via Apify. Free $5 credit is enough for personal searching."
          defaultOpen
        >
          <ConnectorRow
            name="Apify job search"
            note="Finds roles free boards miss — especially Naukri and LinkedIn. Uses a little of Apify’s free credit each scan."
            kind={conn?.apify?.ready ? "active" : conn?.apify?.token_set ? "optional" : "missing"}
            label={
              conn?.apify?.ready ? "Ready" :
              conn?.apify?.token_set ? "Token saved — turn on below" :
              "Not set up"
            }
          >
            <div className={formCls}>
              <HelpDetails title="How do I get a free Apify token?">
                <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm text-stone">
                  <li>
                    Open{" "}
                    <a
                      href="https://console.apify.com/sign-up"
                      target="_blank"
                      rel="noreferrer"
                      className="font-bold text-ink underline"
                    >
                      console.apify.com/sign-up
                    </a>{" "}
                    and create a free account ($5 credit included).
                  </li>
                  <li>
                    Go to{" "}
                    <a
                      href="https://console.apify.com/account/integrations"
                      target="_blank"
                      rel="noreferrer"
                      className="font-bold text-ink underline"
                    >
                      Account → Integrations
                    </a>{" "}
                    and copy your API token.
                  </li>
                  <li>Paste it below, turn on “Use Apify on each scan”, and Save.</li>
                </ol>
              </HelpDetails>
              <Field
                label="Apify API token"
                hint={
                  conn?.apify?.token_set
                    ? "A token is already saved. Leave blank to keep it, or paste a new one to replace it."
                    : "Stored only on this computer — not in any shared file."
                }
              >
                <input
                  type="password"
                  value={apifyToken}
                  onChange={(e) => setApifyToken(e.target.value)}
                  placeholder={conn?.apify?.token_set ? "•••••••• (already saved)" : "Paste your Apify token"}
                  className={inputCls}
                  disabled={connLoading}
                  autoComplete="off"
                />
              </Field>
              <label className="flex cursor-pointer items-start gap-3 text-sm text-ink">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4"
                  checked={apifyEnabled}
                  onChange={(e) => setApifyEnabled(e.target.checked)}
                  disabled={connLoading}
                />
                <span>
                  <span className="font-bold">Use Apify on each scan</span>
                  <span className="mt-0.5 block text-stone">
                    Turns on Naukri, LinkedIn, and Indeed actors. Keep other free sources too — Apify fills the gaps.
                  </span>
                </span>
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="lime"
                  size="sm"
                  isLoading={savingKey === "apify"}
                  onClick={() =>
                    saveConn("apify", {
                      apify_enabled: apifyEnabled,
                      ...(apifyToken ? { apify_token: apifyToken } : {}),
                    })
                  }
                >
                  <Save size={13} /> Save
                </Button>
                {conn?.apify?.token_set && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      saveConn("apify-clear", { apify_token: "", apify_enabled: false })
                    }
                  >
                    Remove token
                  </Button>
                )}
                <a
                  href="https://console.apify.com/account/integrations"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 self-center text-sm font-bold text-ink underline"
                >
                  Open Apify <ExternalLink size={13} />
                </a>
              </div>
            </div>
          </ConnectorRow>
        </ConnectorSection>

        {/* ── Page reader (optional scrape boost) ─────────────────────── */}
        <ConnectorSection
          icon={Radar}
          title="Page reader (optional)"
          subtitle="Recover empty or blocked careers pages before Playwright. No API key, no extra install."
          defaultOpen={false}
        >
          <ConnectorRow
            name="Careers / JD page boost"
            note={
              conn?.page_reader?.hint ||
              "When plain HTTP returns an empty JavaScript shell, fetch a readable snapshot first."
            }
            kind={conn?.page_reader?.enabled ? "active" : "optional"}
            label={conn?.page_reader?.enabled ? "On" : "Off"}
          >
            <div className="space-y-3">
              <HelpDetails title="What does this do?">
                <ol className="list-decimal space-y-1 pl-4 text-sm text-stone">
                  <li>
                    Shortlistr’s normal path is HTTP, then Playwright for hard pages.
                  </li>
                  <li>
                    With this on, thin SPA shells and some blocked responses get an
                    extra readable snapshot first — faster and lighter than opening a
                    browser for every careers URL.
                  </li>
                  <li>
                    Nothing to install. Toggle and Save. Or set{" "}
                    <code className="text-ink">SHORTLISTR_PAGE_READER=1</code> for a
                    one-shot env enable.
                  </li>
                </ol>
              </HelpDetails>
              <label className="flex items-start gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={pageReaderEnabled}
                  onChange={(e) => setPageReaderEnabled(e.target.checked)}
                />
                <span>
                  <span className="font-bold">Use page reader on fetch</span>
                  <span className="mt-0.5 block text-stone">
                    When a careers URL returns an empty JavaScript shell (or 403), try
                    a readable snapshot before Playwright.
                  </span>
                </span>
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="lime"
                  size="sm"
                  disabled={savingKey === "page-reader"}
                  isLoading={savingKey === "page-reader"}
                  onClick={() =>
                    saveConn("page-reader", { page_reader_enabled: pageReaderEnabled })
                  }
                >
                  <Save size={13} /> Save
                </Button>
              </div>
            </div>
          </ConnectorRow>
        </ConnectorSection>

        {/* ── Company watchlist (ATS fingerprint) ─────────────────────── */}
        <ConnectorSection
          icon={Radar}
          title="Company watchlist"
          subtitle="Grow portals.yml from careers URLs — Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Recruitee."
          defaultOpen={false}
        >
          <PortalsFingerprintPanel />
        </ConnectorSection>

        {/* ── Email verify (optional, Reach out) ──────────────────────── */}
        <ConnectorSection
          icon={Mail}
          title="Contact resolution (optional)"
          subtitle="Prep → Resolve contact. SERP + email verify unlock higher hit rates — never auto-send."
          defaultOpen={false}
        >
          <ConnectorRow
            name="Hunter / NeverBounce key"
            note="Without a key we only suggest first.last@company.com patterns. With a key, Prep can mark which look deliverable."
            kind={conn?.email_verify?.api_key_set ? "active" : "optional"}
            label={conn?.email_verify?.api_key_set ? "Key saved" : "Optional"}
          >
            <div className={formCls}>
              <Field label="Provider">
                <select
                  value={emailVerifyProvider}
                  onChange={(e) => setEmailVerifyProvider(e.target.value)}
                  className={inputCls}
                >
                  <option value="hunter">Hunter.io</option>
                  <option value="neverbounce">NeverBounce</option>
                </select>
              </Field>
              <Field label="API key" hint="Stored in your password vault — never in profile.yml.">
                <input
                  type="password"
                  value={emailVerifyKey}
                  onChange={(e) => setEmailVerifyKey(e.target.value)}
                  placeholder={conn?.email_verify?.api_key_set ? "•••••••• (leave blank to keep)" : "Paste key"}
                  className={inputCls}
                  autoComplete="off"
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="lime"
                  size="sm"
                  isLoading={savingKey === "email-verify"}
                  onClick={() =>
                    saveConn("email-verify", {
                      email_verify_provider: emailVerifyProvider,
                      ...(emailVerifyKey ? { email_verify_api_key: emailVerifyKey } : {}),
                    })
                  }
                >
                  <Save size={13} /> Save
                </Button>
                {conn?.email_verify?.api_key_set && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      saveConn("email-verify-clear", { email_verify_api_key: "" })
                    }
                  >
                    Remove key
                  </Button>
                )}
              </div>
            </div>
          </ConnectorRow>


          <ConnectorRow
            name="Serper.dev (SERP)"
            note="Paid Google snippets. Optional — prefer Google Custom Search (free) or DuckDuckGo for interview prep."
            kind={conn?.serper?.api_key_set ? "active" : "optional"}
            label={conn?.serper?.api_key_set ? "Key saved" : "Optional"}
          >
            <div className={formCls}>
              <Field label="Serper API key">
                <input
                  type="password"
                  value={serperKey}
                  onChange={(e) => setSerperKey(e.target.value)}
                  placeholder={conn?.serper?.api_key_set ? "•••••••• (leave blank to keep)" : "Paste key"}
                  className={inputCls}
                  autoComplete="off"
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="lime"
                  size="sm"
                  isLoading={savingKey === "serper"}
                  onClick={() =>
                    saveConn("serper", {
                      ...(serperKey ? { serper_api_key: serperKey } : {}),
                    })
                  }
                >
                  <Save size={13} /> Save
                </Button>
                {conn?.serper?.api_key_set && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => saveConn("serper-clear", { serper_api_key: "" })}
                  >
                    Remove key
                  </Button>
                )}
              </div>
            </div>
          </ConnectorRow>

          <ConnectorRow
            name="GitHub token"
            note="Raises rate limits for public commit-email mining. Classic PAT with public_repo read is enough."
            kind={conn?.github?.token_set ? "active" : "optional"}
            label={conn?.github?.token_set ? "Token saved" : "Optional"}
          >
            <div className={formCls}>
              <Field label="GitHub personal access token">
                <input
                  type="password"
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  placeholder={conn?.github?.token_set ? "•••••••• (leave blank to keep)" : "ghp_…"}
                  className={inputCls}
                  autoComplete="off"
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="lime"
                  size="sm"
                  isLoading={savingKey === "github"}
                  onClick={() =>
                    saveConn("github", {
                      ...(githubToken ? { github_token: githubToken } : {}),
                    })
                  }
                >
                  <Save size={13} /> Save
                </Button>
                {conn?.github?.token_set && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => saveConn("github-clear", { github_token: "" })}
                  >
                    Remove token
                  </Button>
                )}
              </div>
            </div>
          </ConnectorRow>
        </ConnectorSection>

        {/* ── 3. Browser ──────────────────────────────────────────────── */}
        <ConnectorSection
          icon={Globe}
          title="Job site logins (optional)"
          subtitle="Only needed for apply-assist to fill LinkedIn or Naukri forms. You still click Submit. Stored in your OS keychain, never in the repo."
          defaultOpen={false}
        >
          <div className="space-y-3">
            <ConnectorRow
              name="Browser for form filling"
              note="A private Chrome browser used only on your computer."
              kind={playwright ? "active" : "missing"}
              label={playwright ? "Ready" : "Needs install"}
            >
              {playwright ? (
                <p className="text-sm text-stone">Installed. LinkedIn, Naukri, and Prefill form can use it.</p>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-stone">Click once — no terminal. Takes about a minute.</p>
                  <Button variant="lime" size="sm" onClick={installPlaywright} isLoading={savingKey === "playwright"}>
                    <Download size={13} />
                    {savingKey === "playwright" ? "Installing…" : "Install browser"}
                  </Button>
                </div>
              )}
            </ConnectorRow>

            <ConnectorRow
              name="LinkedIn"
              note="Your LinkedIn login, so Easy Apply pages can be filled automatically."
              kind={conn?.linkedin.password_set ? "active" : "optional"}
              label={conn?.linkedin.password_set ? "Saved" : "Optional"}
            >
              <div className={formCls}>
                <div className={pairCls}>
                  <Field label="LinkedIn email">
                    <input type="email" value={liEmail} onChange={(e) => setLiEmail(e.target.value)}
                      placeholder="you@gmail.com" className={inputCls} disabled={connLoading} />
                  </Field>
                  <Field label="LinkedIn password" hint={conn?.linkedin.password_set ? "A password is already saved. Leave blank to keep it." : "Stored only on this computer."}>
                    <input type="password" value={liPassword} onChange={(e) => setLiPassword(e.target.value)}
                      placeholder={conn?.linkedin.password_set ? "••••••••" : "Your LinkedIn password"}
                      className={inputCls} disabled={connLoading} autoComplete="off" />
                  </Field>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="lime" size="sm" isLoading={savingKey === "linkedin"} disabled={connLoading}
                    onClick={() => saveConn("linkedin", {
                      linkedin_email: liEmail,
                      ...(liPassword ? { linkedin_password: liPassword } : {}),
                    })}>
                    <Save size={13} /> Save LinkedIn
                  </Button>
                  {conn?.linkedin.password_set && (
                    <Button variant="ghost" size="sm" isLoading={savingKey === "linkedin-clear"}
                      onClick={() => saveConn("linkedin-clear", { linkedin_password: "" })}>
                      <Trash2 size={13} /> Remove password
                    </Button>
                  )}
                </div>
              </div>
            </ConnectorRow>

            <ConnectorRow
              name="Naukri"
              note="For India job applications that need a Naukri login."
              kind={conn?.naukri.password_set ? "active" : "optional"}
              label={conn?.naukri.password_set ? "Saved" : "Optional"}
            >
              <div className={formCls}>
                <div className={pairCls}>
                  <Field label="Naukri email">
                    <input type="email" value={nkEmail} onChange={(e) => setNkEmail(e.target.value)}
                      placeholder="you@gmail.com" className={inputCls} disabled={connLoading} />
                  </Field>
                  <Field label="Naukri password" hint={conn?.naukri.password_set ? "Already saved — leave blank to keep it." : undefined}>
                    <input type="password" value={nkPassword} onChange={(e) => setNkPassword(e.target.value)}
                      placeholder={conn?.naukri.password_set ? "••••••••" : "Your Naukri password"}
                      className={inputCls} disabled={connLoading} autoComplete="off" />
                  </Field>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="lime" size="sm" isLoading={savingKey === "naukri"} disabled={connLoading}
                    onClick={() => saveConn("naukri", {
                      naukri_email: nkEmail,
                      ...(nkPassword ? { naukri_password: nkPassword } : {}),
                    })}>
                    <Save size={13} /> Save Naukri
                  </Button>
                  {conn?.naukri.password_set && (
                    <Button variant="ghost" size="sm" isLoading={savingKey === "naukri-clear"}
                      onClick={() => saveConn("naukri-clear", { naukri_password: "" })}>
                      <Trash2 size={13} /> Remove password
                    </Button>
                  )}
                </div>
              </div>
            </ConnectorRow>
          </div>
        </ConnectorSection>

        {/* ── 3. Email ────────────────────────────────────────────────── */}
        <ConnectorSection
          icon={Mail}
          title="Email (optional)"
          subtitle="Import job-alert emails into Discover, and send applications from your own Gmail. Nothing is ever sent without you."
          defaultOpen={false}
        >
          <div className="space-y-3">
            <ConnectorRow
              name="Send email (most people only need this)"
              note="Lets Shortlistr send cover letters and applications from your Gmail. Uses a special App Password — not your normal Gmail password."
              kind={conn?.gmail.app_password_set ? "active" : "optional"}
              label={conn?.gmail.app_password_set ? "Ready to send" : "Not set up"}
            >
              <div className={formCls}>
                <HelpDetails title="How do I create a Gmail App Password? (2 minutes)">
                  <ol className="list-decimal space-y-1.5 pl-4">
                    <li>Turn on 2-Step Verification for your Google account if it isn’t already.</li>
                    <li>
                      Open{" "}
                      <a
                        href="https://myaccount.google.com/apppasswords"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-0.5 font-bold text-ink underline"
                      >
                        App passwords <ExternalLink size={11} />
                      </a>
                      .
                    </li>
                    <li>Choose app name “Shortlistr”, create, then copy the 16-character password.</li>
                    <li>Paste it below and press Save.</li>
                  </ol>
                </HelpDetails>
                <div className={pairCls}>
                  <Field label="Gmail address to send from">
                    <input
                      type="email"
                      value={gmailSender}
                      onChange={(e) => setGmailSender(e.target.value)}
                      placeholder={profile?.email || "you@gmail.com"}
                      className={inputCls}
                      disabled={connLoading}
                    />
                  </Field>
                  <Field label="App Password" hint="16 characters from Google. Not the password you use to sign in to Gmail.">
                    <input
                      type="password"
                      value={gmailPassword}
                      onChange={(e) => setGmailPassword(e.target.value)}
                      placeholder={conn?.gmail.app_password_set ? "•••••••• (already saved)" : "xxxx xxxx xxxx xxxx"}
                      className={inputCls}
                      disabled={connLoading}
                      autoComplete="off"
                    />
                  </Field>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="lime"
                    size="sm"
                    isLoading={savingKey === "gmail"}
                    disabled={connLoading || (!gmailPassword && !gmailSender)}
                    onClick={() =>
                      saveConn("gmail", {
                        gmail_sender: gmailSender,
                        ...(gmailPassword ? { gmail_app_password: gmailPassword } : {}),
                      })
                    }
                  >
                    <Save size={13} /> Save email
                  </Button>
                  {conn?.gmail.app_password_set && (
                    <Button
                      variant="ghost"
                      size="sm"
                      isLoading={savingKey === "gmail-clear"}
                      onClick={() => saveConn("gmail-clear", { gmail_app_password: "" })}
                    >
                      <Trash2 size={13} /> Remove
                    </Button>
                  )}
                </div>
              </div>
            </ConnectorRow>

            <ConnectorRow
              name="Read job-alert emails (optional)"
              note="Only if you want Shortlistr to pick up jobs that arrive in your Gmail from LinkedIn, Naukri, etc."
              kind={conn?.gmail.token_present ? "active" : conn?.gmail.credentials_present ? "optional" : "optional"}
              label={
                conn?.gmail.token_present ? "Connected" :
                conn?.gmail.credentials_present ? "File ready — connect next" :
                "Skipped"
              }
            >
              {conn?.gmail.token_present ? (
                <div className="space-y-2">
                  <p className="text-sm text-stone">Your Gmail inbox is connected. Job alerts can be imported automatically.</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    isLoading={savingKey === "gmail-disconnect"}
                    onClick={async () => {
                      setSavingKey("gmail-disconnect");
                      try {
                        applyConn(await api.disconnectGmail());
                        toast.success("Gmail disconnected");
                      } catch (e) {
                        toast.error(e instanceof ApiError ? e.message : "Failed");
                      } finally {
                        setSavingKey(null);
                      }
                    }}
                  >
                    Disconnect Gmail
                  </Button>
                </div>
              ) : (
                <div className={formCls}>
                  <HelpDetails title="One-time Google setup (guided)">
                    <ol className="list-decimal space-y-1.5 pl-4">
                      <li>
                        Open{" "}
                        <a
                          href="https://console.cloud.google.com/apis/credentials"
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-0.5 font-bold text-ink underline"
                        >
                          Google Cloud credentials <ExternalLink size={11} />
                        </a>
                        {" "}(free).
                      </li>
                      <li>Create a project if asked, then create an OAuth client of type <strong className="text-ink">Desktop app</strong>.</li>
                      <li>Click Download JSON — you’ll get a file like <code className="text-ink">client_secret_….json</code>.</li>
                      <li>Upload that file with the button below, then click Connect Gmail and approve access in the browser.</li>
                    </ol>
                  </HelpDetails>
                  <input
                    ref={credsInputRef}
                    type="file"
                    accept=".json,application/json"
                    className="hidden"
                    onChange={(e) => void onCredsFile(e.target.files?.[0] ?? null)}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      isLoading={savingKey === "gmail-creds"}
                      onClick={() => credsInputRef.current?.click()}
                    >
                      <Upload size={13} />
                      {conn?.gmail.credentials_present ? "Replace credentials file" : "Upload Google JSON file"}
                    </Button>
                    <Button
                      variant="lime"
                      size="sm"
                      disabled={!conn?.gmail.credentials_present}
                      isLoading={savingKey === "gmail-connect"}
                      onClick={() => void connectGmail()}
                    >
                      Connect Gmail
                    </Button>
                  </div>
                  {!conn?.gmail.credentials_present && (
                    <p className="text-sm text-stone">Upload the JSON file first — Connect stays disabled until then.</p>
                  )}
                </div>
              )}
            </ConnectorRow>
          </div>
        </ConnectorSection>

        {/* ── 4. Phone alerts ─────────────────────────────────────────── */}
        <ConnectorSection
          icon={MessageSquare}
          title="Phone alerts"
          subtitle="Optional. Chat with the same job-search agent from your phone."
          defaultOpen={false}
        >
          <ConnectorRow
            name="Telegram"
            note="Same agent as the dashboard assistant — status, approve, skip, prep. After you message the bot once, strong evaluations can ping this chat."
            kind={conn?.telegram.token_set ? "active" : "optional"}
            label={conn?.telegram.token_set ? "Token saved" : "Optional"}
          >
            <div className={formCls}>
              <HelpDetails title="How do I get a bot token?">
                <ol className="list-decimal space-y-1.5 pl-4">
                  <li>Open Telegram and search for <strong className="text-ink">@BotFather</strong>.</li>
                  <li>Send <code className="text-ink">/newbot</code> and follow the prompts.</li>
                  <li>Copy the long token BotFather gives you and paste it below.</li>
                  <li>Save, then in a terminal run <code className="text-ink">make telegram</code> and leave it running.</li>
                  <li>Open your bot in Telegram and send <code className="text-ink">/start</code>.</li>
                </ol>
              </HelpDetails>
              <Field label="Bot token">
                <input
                  type="password"
                  value={telegramToken}
                  onChange={(e) => setTelegramToken(e.target.value)}
                  placeholder={conn?.telegram.token_set ? "•••••••• (already saved)" : "Paste token from BotFather"}
                  className={inputCls}
                  disabled={connLoading}
                  autoComplete="off"
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="lime"
                  size="sm"
                  isLoading={savingKey === "telegram"}
                  disabled={connLoading || !telegramToken}
                  onClick={() => saveConn("telegram", { telegram_bot_token: telegramToken })}
                >
                  <Save size={13} /> Save Telegram
                </Button>
                {conn?.telegram.token_set && (
                  <Button
                    variant="ghost"
                    size="sm"
                    isLoading={savingKey === "telegram-clear"}
                    onClick={() => saveConn("telegram-clear", { telegram_bot_token: "" })}
                  >
                    <Trash2 size={13} /> Remove
                  </Button>
                )}
              </div>
            </div>
          </ConnectorRow>
        </ConnectorSection>

        {/* ── 5. Advanced ─────────────────────────────────────────────── */}
        <ConnectorSection
          icon={Server}
          title="Advanced tools"
          subtitle="For developers only — extra MCP tools for the agent chat. Most people can ignore this."
          defaultOpen={false}
        >
          <div className="space-y-3">
            {mcpDraft.map((server, idx) => (
              <div key={`${server.name}-${idx}`} className="space-y-4 rounded-2xl border border-mist/60 bg-white p-5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-base font-bold text-ink">{server.name || `Server ${idx + 1}`}</p>
                  <button
                    type="button"
                    onClick={() => setMcpDraft((rows) => rows.filter((_, i) => i !== idx))}
                    className="rounded-lg p-1.5 text-stone hover:bg-mist hover:text-ink"
                    aria-label="Remove server"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  <Field label="Name">
                    <input
                      value={server.name}
                      onChange={(e) =>
                        setMcpDraft((rows) =>
                          rows.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r))
                        )
                      }
                      placeholder="filesystem"
                      className={inputCls}
                    />
                  </Field>
                  <Field label="Type">
                    <select
                      value={server.type === "http" ? "http" : "stdio"}
                      onChange={(e) =>
                        setMcpDraft((rows) =>
                          rows.map((r, i) => (i === idx ? { ...r, type: e.target.value } : r))
                        )
                      }
                      className={inputCls}
                    >
                      <option value="stdio">Program on this computer</option>
                      <option value="http">Web address</option>
                    </select>
                  </Field>
                </div>
                {server.type === "http" ? (
                  <Field label="URL">
                    <input
                      value={server.url || ""}
                      onChange={(e) =>
                        setMcpDraft((rows) =>
                          rows.map((r, i) => (i === idx ? { ...r, url: e.target.value } : r))
                        )
                      }
                      placeholder="https://api.example.com/mcp"
                      className={inputCls}
                    />
                  </Field>
                ) : (
                  <>
                    <Field label="Command">
                      <input
                        value={server.command || ""}
                        onChange={(e) =>
                          setMcpDraft((rows) =>
                            rows.map((r, i) => (i === idx ? { ...r, command: e.target.value } : r))
                          )
                        }
                        placeholder="mcp-server-filesystem"
                        className={inputCls}
                      />
                    </Field>
                    <Field label="Arguments" hint="Separate with spaces">
                      <input
                        value={(server.args || []).join(" ")}
                        onChange={(e) =>
                          setMcpDraft((rows) =>
                            rows.map((r, i) =>
                              i === idx
                                ? { ...r, args: e.target.value.split(/\s+/).filter(Boolean) }
                                : r
                            )
                          )
                        }
                        placeholder="/Users/you/docs"
                        className={inputCls}
                      />
                    </Field>
                  </>
                )}
                <Field label="Secret name (optional)">
                  <input
                    value={server.secret_ref || ""}
                    onChange={(e) =>
                      setMcpDraft((rows) =>
                        rows.map((r, i) => (i === idx ? { ...r, secret_ref: e.target.value } : r))
                      )
                    }
                    placeholder="MY_MCP_TOKEN"
                    className={inputCls}
                  />
                </Field>
              </div>
            ))}

            {mcpDraft.length === 0 && (
              <p className="rounded-xl border border-dashed border-mist bg-mist/30 px-3 py-4 text-center text-sm text-stone">
                No advanced tools added.
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setMcpDraft((rows) => [
                    ...rows,
                    { name: "", type: "stdio", command: "", args: [], url: "", secret_ref: "" },
                  ])
                }
              >
                <Plus size={13} /> Add tool
              </Button>
              <Button
                variant="lime"
                size="sm"
                isLoading={savingKey === "mcp"}
                disabled={connLoading}
                onClick={() =>
                  saveConn("mcp", {
                    mcp_servers: mcpDraft.map((s) => ({
                      name: s.name,
                      type: s.type === "http" ? "http" : "stdio",
                      command: s.command,
                      args: s.args,
                      url: s.url,
                      secret_ref: s.secret_ref,
                    })),
                  })
                }
              >
                <Save size={13} /> Save tools
              </Button>
            </div>
          </div>
        </ConnectorSection>
      </div>
    </DashboardShell>
  );
}
