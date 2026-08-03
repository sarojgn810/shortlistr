import { env } from "@/src/config/env";

/** An application the mailbox says is waiting on you.
 *
 * Separate from the tracker board because the board is job-centric and these
 * usually come from applications made outside the tool — there is no job row.
 */
export interface FollowUp {
  id: number;
  kind: string;
  company: string;
  role: string;
  subject: string;
  sender: string;
  source: string;
  job_id: string | null;
  application_id: number | null;
  created_at: string;
  resolved_at: string | null;
}

export interface FollowUpsResponse {
  follow_ups: FollowUp[];
  open: number;
}

export interface LlmStatus {
  provider: string;
  resolved_provider?: string;
  model: string;
  configured: boolean;
  api_key_set: boolean;
  available: boolean;
  mode: "llm" | "template";
  sdk_installed?: boolean;
  reason?: "not_configured" | "missing_api_key" | "sdk_missing" | "unavailable" | "ok";
  hint?: string;
  install_hint?: string;
  env_files: string[];
  env_var: string;
  prompt_template: string;
  features: {
    evaluation: boolean;
    cover_letter: boolean;
    tool_calling: boolean;
    rag: boolean;
    memory: boolean;
    embeddings: boolean;
  };
}

export interface ProfileSetup {
  exists: boolean;
  name: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  github: string;
  years_exp: number;
  min_salary_inr_lpa: number;
  min_salary_usd: number;
  salary_unlisted: string;
  target_titles: string[];
  preferred_locations: string[];
  min_fit_score: number;
  llm_provider: string;
  llm_model: string;
  llm_api_key_set: boolean;
  llm_two_stage_triage?: boolean;
  suggested_provider?: string | null;
  website: string;
  notice_period: string;
  current_ctc: string;
  expected_ctc: string;
  how_heard: string;
  work_authorization: string;
  preferred_name: string;
  cover_letter_snippet: string;
  willing_to_relocate: string;
}

export interface McpServerConfig {
  name: string;
  type: "stdio" | "http" | string;
  command?: string;
  args?: string[];
  url?: string;
  secret_ref?: string;
}

export interface LocalAiModelOption {
  id: string;
  name: string;
  min_ram_gb: number;
  download_mb: number;
  quality: string;
  speed: string;
  fit: "smooth" | "tight" | "heavy" | string;
  fit_label: string;
  recommended: boolean;
}

export interface LocalAiCapability {
  system?: {
    os?: string;
    os_label?: string;
    arch?: string;
    ram_gb?: number | null;
    cpu_cores?: number;
    tier?: string;
    tier_label?: string;
    summary?: string;
  };
  models?: LocalAiModelOption[];
  recommended_model?: string;
  guide?: { title: string; body: string }[];
  error?: string;
}

export interface LocalAiStatus {
  phase: string;
  message: string;
  model: string;
  ollama_installed?: boolean;
  ollama_running?: boolean;
  model_ready?: boolean;
  ready: boolean;
  error?: string | null;
  updated_at?: string | null;
  capability?: LocalAiCapability;
}

export interface ConnectionsSetup {
  playwright: { installed: boolean; label: string };
  local_ai?: LocalAiStatus;
  apify?: { token_set: boolean; enabled: boolean; ready: boolean };
  linkedin: { email: string; password_set: boolean };
  naukri: { email: string; password_set: boolean };
  gmail: {
    credentials_present: boolean;
    token_present: boolean;
    app_password_set: boolean;
    sender: string;
  };
  telegram: { token_set: boolean };
  email_verify?: { api_key_set: boolean; provider: string };
  serper?: { api_key_set: boolean };
  google_cse?: { api_key_set: boolean; cx_set: boolean; ready: boolean };
  page_reader?: {
    enabled: boolean;
    ready: boolean;
    hint?: string;
  };
  github?: { token_set: boolean };
  mcp_servers: McpServerConfig[];
}

/** Partial update — omit a field to leave it; send "" on a secret to clear it. */
export interface ConnectionsUpdate {
  linkedin_email?: string;
  linkedin_password?: string;
  naukri_email?: string;
  naukri_password?: string;
  gmail_sender?: string;
  gmail_app_password?: string;
  telegram_bot_token?: string;
  apify_token?: string;
  apify_enabled?: boolean;
  page_reader_enabled?: boolean;
  email_verify_api_key?: string;
  email_verify_provider?: string;
  serper_api_key?: string;
  google_cse_api_key?: string;
  google_cse_cx?: string;
  github_token?: string;
  mcp_servers?: McpServerConfig[];
}

export interface SetupStatus {
  ready: boolean;
  checks: {
    cv: boolean;
    profile: boolean;
    sqlite: boolean;
    llm: boolean;
    playwright?: boolean;
    apify?: boolean;
  };
  llm: LlmStatus;
  /** Demo gate — API up, DB present, LLM local-or-key, Playwright optional. */
  demo?: {
    api: boolean;
    db_migrated: boolean;
    llm_available: boolean;
    playwright_optional: boolean;
    ready_for_chat: boolean;
    hint?: string | null;
  };
  counts: { pipeline: number; jobs: number };
  automation?: AutomationSettings;
  cv?: CvSettings;
  onboarding_complete?: boolean;
  /** Human-readable leftovers when onboarding_complete is false. */
  onboarding_gaps?: string[];
}

export interface DiscoverStatus {
  running: boolean;
  queue: Record<string, number>;
  last_status: string | null;
  last_started_at: string | null;
  last_finished_at: string | null;
  total_jobs: number;
}

export interface AutomationSettings {
  scan_enabled: boolean;
  scan_interval_hours: number;
  auto_evaluate: boolean;
  auto_evaluate_min_score: number;
  auto_approve_score: number;
  last_scan_at: string | null;
  last_scan_jobs?: number;
  last_scan_errors?: Record<string, string> | null;
  last_scan_sources_ok?: number;
  last_scan_sources_total?: number;
  onboarding_complete?: boolean;
  scan_due?: boolean;
}

export interface CvTemplate {
  id: string;
  name: string;
  description: string;
  ats_notes: string;
  family?: string;
  recommended?: boolean;
  inspiration?: string;
}

export interface AtsScore {
  score: number;
  content_score?: number;
  ats_readiness?: number;
  job_match_percent?: number;
  tier: string;
  checks: {
    label: string;
    ok: boolean;
    points: number;
    max_points?: number;
    hint?: string;
  }[];
  fixes?: { label: string; hint: string }[];
  template_id?: string;
}

export interface PrepSummary {
  job_id: string;
  company: string;
  role: string;
  url: string;
  location: string;
  source: string;
  pipeline_status: string;
  application_status: string;
  has_prep_guide: boolean;
  has_cover_draft: boolean;
  has_cv_pdf: boolean;
  ready: boolean;
  updated_at: string;
  candidate_name?: string;
  fit_score?: number;
  eval_score?: number | null;
  fit_label?: string;
  fit_reason?: string;
}

export type PageTarget = "auto" | "1" | "2";

export interface LinkedInExperienceJob {
  title: string;
  company: string;
  bullets: string[];
}

export interface LinkedInProfile {
  raw?: string;
  name: string;
  headline: string;
  about: string;
  experience: LinkedInExperienceJob[];
  skills: string[];
  featured: string;
  open_to_work: string;
  location: string;
  contact: string;
  linkedin_url?: string;
  source?: string;
}

export interface LinkedInScore {
  role_id: string;
  role_label: string;
  overall: number;
  dimensions: {
    keyword_match: number;
    role_alignment: number;
    quantification: number;
    clarity: number;
    impact: number;
    completeness: number;
    consistency: number;
  };
  weak_areas: string[];
  found_keywords: string[];
  missing_keywords: string[];
  missing_nice_keywords: string[];
  likely_recruiter_searches: string[];
  title_hits: string[];
  checklist: { id: string; label: string; detail: string; severity: string }[];
  section_presence: Record<string, boolean>;
  mode: string;
}

export interface LinkedInRoleOption {
  id: string;
  label: string;
  search_titles: string[];
}

export interface LinkedInCoverTheme {
  id: string;
  label: string;
  description: string;
  preview_colors: { bg: string; accent: string; text: string };
}

export interface LinkedInOptimizerState {
  profile: LinkedInProfile;
  target_role: string;
  score: LinkedInScore;
  roles: LinkedInRoleOption[];
  profile_target_titles?: string[];
  cover_themes: LinkedInCoverTheme[];
  linkedin_url?: string;
  source?: string;
  substantial?: boolean;
  needs_import?: boolean;
  import_note?: string | null;
}

export interface LinkedInRewriteResult {
  section: string;
  original: string;
  suggested: string;
  rationale: string;
  mode: string;
  llm_attempted?: boolean;
  suggested_list?: string[];
  suggested_structured?: LinkedInExperienceJob[];
  recommended_keywords?: string[];
  notes?: string[];
  error?: string;
}

export interface LinkedInImportResult {
  ok: boolean;
  profile?: LinkedInProfile | null;
  score?: LinkedInScore;
  target_role?: string;
  linkedin_url?: string;
  source?: string;
  error?: string;
  needs_url?: boolean;
  cv_fallback_available?: boolean;
  import_note?: string;
  partial?: boolean;
  hint?: string;
}

export interface CvArtifacts {
  cv_path: string | null;
  template_id: string | null;
  tex_path: string | null;
  pdf_path: string | null;
  has_md: boolean;
  has_tex: boolean;
  has_pdf: boolean;
  page_target: PageTarget;
  page_count: number;
  /** Which rung of the density ladder the fit search settled on. */
  density: string | null;
}

export interface ExtractedProfile {
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  linkedin?: string;
  github?: string;
  years_exp?: number;
  target_titles?: string[];
  preferred_locations?: string[];
}

export interface CvUploadResult {
  markdown: string;
  source_format: string;
  pdf_path: string | null;
  cv_path: string;
  char_count: number;
  ats: AtsScore;
  is_placeholder?: boolean;
  profile?: ExtractedProfile;
  applied_target_titles?: string[];
}

export interface CvSettings {
  template_id: string;
  last_generated_tex?: string | null;
  last_generated_pdf?: string | null;
  ats_score?: number;
  ats?: AtsScore;
  resume_source?: "uploaded" | "generated";
  page_target?: PageTarget;
  last_page_count?: number;
  last_density?: string | null;
}

export interface HealthResponse {
  status: string;
  llm: LlmStatus;
}

class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function authHeaders(): HeadersInit {
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (env.apiToken) {
    headers.Authorization = `Bearer ${env.apiToken}`;
  }
  return headers;
}

function authHeadersMultipart(): HeadersInit {
  const headers: HeadersInit = {};
  if (env.apiToken) {
    headers.Authorization = `Bearer ${env.apiToken}`;
  }
  return headers;
}

function formatApiErrorDetail(detail: unknown): string {
  if (detail == null) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (typeof detail === "object" && "msg" in (detail as object)) {
    return String((detail as { msg: unknown }).msg);
  }
  return JSON.stringify(detail);
}

/** Nothing here should be able to hang forever.
 *
 * fetch has no default timeout, so an API that accepts the connection and then
 * stops answering leaves the caller awaiting indefinitely. In the chat dock
 * that meant `busy` stayed true, the input stayed disabled, and the message sat
 * there with no reply and no error — which reads as the chat being broken
 * rather than slow.
 *
 * 30s covers ordinary calls; the chat passes a longer one because a real model
 * reply can legitimately take a while.
 */
const DEFAULT_TIMEOUT_MS = 30_000;

async function request<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init || {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${env.apiUrl}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        ...authHeaders(),
        ...rest?.headers,
      },
    });
  } catch (e) {
    // Distinguish "took too long" from "could not reach it at all" — the fixes
    // are different and "Failed to fetch" tells the user neither.
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(
        `The API did not respond within ${Math.round(timeoutMs / 1000)}s. It may still be starting up.`,
        0,
      );
    }
    throw new ApiError(
      "Could not reach the Shortlistr API. Is it still running on port 8787?",
      0,
    );
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let message = text || res.statusText;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (parsed.detail != null) {
        message = formatApiErrorDetail(parsed.detail);
      }
    } catch {
      /* keep raw text */
    }
    // The dashboard talks to the API through a Next rewrite, so an API that is
    // down does not fail the fetch — the proxy answers 500/502/504 with a body
    // that says nothing. "Internal Server Error" then reads as a bug in the app
    // rather than a service that is not running.
    const proxyBlind =
      (res.status === 500 && (!text || text === "Internal Server Error")) ||
      res.status === 502 ||
      res.status === 503 ||
      res.status === 504;
    if (proxyBlind) {
      message =
        "Could not reach the Shortlistr API. Check it is running on port 8787 — " +
        "if you started the app with `automation.cli start`, look for errors in that window.";
    }
    throw new ApiError(message, res.status);
  }

  return res.json() as Promise<T>;
}

export interface ChatTurn {
  role: string;
  content: string;
}

export interface PendingConfirm {
  tool: string;
  args: Record<string, unknown>;
  prompt: string;
}

export interface ChatResponse {
  reply: string;
  actions: { tool: string; result?: unknown }[];
  pending_confirm?: PendingConfirm;
  /** True when reply came from the no-LLM fallback — show Groq / Connections CTA. */
  needs_llm?: boolean;
}


export const api = {
  health: () => request<HealthResponse>("/health"),
  sendChat: (body: {
    message?: string;
    history?: ChatTurn[];
    confirm_tool?: string;
    confirm_args?: Record<string, unknown>;
  }) =>
    request<ChatResponse>("/agent/chat", {
      method: "POST",
      body: JSON.stringify(body),
      // A model reply is allowed to be slow; a hang is not.
      timeoutMs: 90_000,
    }),
  setupStatus: () => request<SetupStatus>("/setup/status"),
  getProfile: () => request<ProfileSetup>("/setup/profile"),
  saveProfile: (body: Partial<ProfileSetup> & { llm_api_key?: string; target_titles?: string[] }) =>
    request<ProfileSetup>("/setup/profile", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  getConnections: () => request<ConnectionsSetup>("/setup/connections"),
  testLlm: () =>
    request<{ ok: boolean; provider?: string; model?: string; message: string }>(
      "/setup/connections/test-llm",
      { method: "POST" },
    ),
  testSearch: () =>
    request<{ ok: boolean; backend: string; message: string }>(
      "/setup/connections/test-search",
      { method: "POST" },
    ),
  saveConnections: (body: ConnectionsUpdate) =>
    request<ConnectionsSetup>("/setup/connections", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  installPlaywright: () =>
    request<{ ok: boolean; playwright: { installed: boolean; label: string } }>(
      "/setup/playwright/install",
      { method: "POST" }
    ),
  getLocalAi: () => request<LocalAiStatus>("/setup/local-ai"),
  ensureLocalAi: (force = false, model?: string) => {
    const q = new URLSearchParams();
    if (force) q.set("force", "true");
    if (model) q.set("model", model);
    const qs = q.toString();
    return request<{ ok: boolean; local_ai: LocalAiStatus }>(
      `/setup/local-ai/ensure${qs ? `?${qs}` : ""}`,
      { method: "POST" }
    );
  },
  uploadGmailCredentials: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${env.apiUrl}/setup/gmail/credentials`, {
      method: "POST",
      headers: authHeadersMultipart(),
      body: form,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      let message = text || res.statusText;
      try {
        const parsed = JSON.parse(text) as { detail?: unknown };
        if (parsed.detail != null) message = formatApiErrorDetail(parsed.detail);
      } catch {
        /* keep */
      }
      throw new ApiError(message, res.status);
    }
    return res.json() as Promise<ConnectionsSetup>;
  },
  connectGmail: () =>
    request<ConnectionsSetup>("/setup/gmail/connect", { method: "POST" }),
  disconnectGmail: () =>
    request<ConnectionsSetup>("/setup/gmail/disconnect", { method: "POST" }),
  listJobs: (status = "inbox", relevance: "relevant" | "all" = "all", offset = 0) =>
    request<Record<string, unknown>[]>(
      `/jobs?status=${encodeURIComponent(status)}&relevance=${relevance}&offset=${offset}`
    ),
  getJob: (jobId: string) => request<Record<string, unknown>>(`/jobs/${jobId}`),
  getExplain: (jobId: string) =>
    request<import("@/src/types/job").ExplainResult>(`/jobs/${jobId}/explain`),
  listApplications: () => request<Record<string, unknown>[]>("/applications"),
  evaluateJob: (jobId: string) =>
    request<import("@/src/types/job").EvalResult>(`/jobs/${jobId}/evaluate`, { method: "POST" }),
  discover: (dryRun = true) =>
    request<import("@/src/types/job").DiscoverResult>("/jobs/discover?async_run=true", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    }),
  discoverStatus: () => request<DiscoverStatus>("/jobs/discover/status"),
  setPipelineStatus: (
    jobId: string,
    status: "approved" | "skipped" | "pending" | "evaluated"
  ) =>
    request<import("@/src/types/job").PipelineTransitionResult>(`/jobs/${jobId}/pipeline-status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  getDiff: (jobId: string) => request<import("@/src/types/job").ResumeDiff>(`/jobs/${jobId}/diff`),
  getReceipts: (jobId: string) =>
    request<import("@/src/types/job").ApplicationReceipt[]>(`/jobs/${jobId}/receipts`),
  exportTracker: () =>
    request<{ pipeline: string; applications: string }>("/sync/export-tracker", {
      method: "POST",
    }),
  applyAssist: (jobId: string, headless = true, confirm = true) =>
    request<import("@/src/types/job").ApplyAssistReport>(`/jobs/${jobId}/apply-assist`, {
      method: "POST",
      body: JSON.stringify({ headless, confirm }),
    }),
  applyBatch: (jobIds: string[], confirm = true) =>
    request<{ queued: string[]; count: number; skipped: { job_id: string; reason: string }[] }>(
      "/jobs/apply-batch",
      { method: "POST", body: JSON.stringify({ job_ids: jobIds, confirm }) }
    ),
  markSubmitted: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/jobs/${jobId}/mark-submitted`, { method: "POST" }),
  sendApplication: (jobId: string, body: string, confirm = true) =>
    request<{ sent: boolean; job_id: string }>(`/jobs/${jobId}/send-application`, {
      method: "POST",
      body: JSON.stringify({ body, confirm }),
    }),
  getPrep: (jobId: string) =>
    request<import("@/src/types/job").PrepBundle>(`/jobs/${jobId}/prep`),
  listPrep: (limit = 100) =>
    request<{ items: PrepSummary[] }>(`/prep?limit=${limit}`),
  generatePrep: (jobId: string) =>
    request<import("@/src/types/job").PrepBundle>(`/jobs/${jobId}/prep/generate`, {
      method: "POST",
    }),
  // Generate only when missing. Approving uses this rather than generatePrep so
  // re-approving never discards a cover letter the user has already edited.
  ensurePrep: (jobId: string) =>
    request<import("@/src/types/job").PrepBundle>(`/jobs/${jobId}/prep/ensure`, {
      method: "POST",
    }),
  savePrepCoverLetter: (jobId: string, body: string) =>
    request<{ saved: boolean; job_id: string }>(`/jobs/${jobId}/prep/cover-letter`, {
      method: "PATCH",
      body: JSON.stringify({ body }),
    }),
  savePrepReachOutContacts: (
    jobId: string,
    contacts: import("@/src/types/job").ReachOutContact[]
  ) =>
    request<{ saved: boolean; job_id: string; count: number }>(
      `/jobs/${jobId}/prep/reach-out/contacts`,
      {
        method: "PATCH",
        body: JSON.stringify({ contacts }),
      }
    ),
  savePrepOutreachDraft: (jobId: string, body: string) =>
    request<{ saved: boolean; job_id: string }>(`/jobs/${jobId}/prep/reach-out/outreach`, {
      method: "PATCH",
      body: JSON.stringify({ body }),
    }),
  suggestReachOutEmails: (
    jobId: string,
    body: { name: string; company?: string; domain?: string; website?: string; verify?: boolean }
  ) =>
    request<{
      job_id: string;
      suggestions: { email: string; status?: string; score?: number | null; source?: string }[];
      verified: boolean;
      note?: string;
    }>(`/jobs/${jobId}/prep/reach-out/suggest-emails`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resolveContact: (
    jobId: string,
    body?: { use_serp?: boolean; use_github?: boolean; verify?: boolean }
  ) =>
    request<import("@/src/types/job").ContactResolution>(
      `/jobs/${jobId}/prep/reach-out/resolve`,
      { method: "POST", body: JSON.stringify(body || {}) }
    ),
  getContactResolution: (jobId: string) =>
    request<import("@/src/types/job").ContactResolution>(
      `/jobs/${jobId}/prep/reach-out/resolve`
    ),
  fingerprintPortals: (urls: string[], companyName?: string) =>
    request<{ proposals: Record<string, unknown>[] }>("/portals/fingerprint", {
      method: "POST",
      body: JSON.stringify({ urls, company_name: companyName || "" }),
    }),
  applyPortalFingerprints: (proposals: Record<string, unknown>[]) =>
    request<{ path: string; added: number; updated: number; total: number }>(
      "/portals/fingerprint/apply",
      { method: "POST", body: JSON.stringify({ proposals }) }
    ),
  exportInstantlyCsv: async (body: {
    job_id?: string;
    contacts?: Record<string, unknown>[];
    company?: string;
    personalization?: string;
  }) => {
    const res = await fetch(`${env.apiUrl}/export/instantly-csv`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const j = await res.json();
        msg = formatApiErrorDetail(j.detail) || j.message || msg;
      } catch {
        /* ignore */
      }
      throw new ApiError(typeof msg === "string" ? msg : "Export failed", res.status);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "instantly-leads.csv";
    a.click();
    URL.revokeObjectURL(url);
    return { ok: true as const };
  },
  getTrackerBoard: (relevance: "relevant" | "all" = "relevant") =>
    request<import("@/src/types/job").TrackerBoard>(`/tracker/board?relevance=${relevance}`),
  getFollowUps: (includeResolved = false) =>
    request<FollowUpsResponse>(
      `/tracker/follow-ups${includeResolved ? "?include_resolved=true" : ""}`,
    ),
  resolveFollowUp: (id: number) =>
    request<{ id: number; resolved: boolean }>(`/tracker/follow-ups/${id}/resolve`, {
      method: "POST",
    }),
  reopenFollowUp: (id: number) =>
    request<{ id: number; resolved: boolean }>(`/tracker/follow-ups/${id}/reopen`, {
      method: "POST",
    }),
  listCvTemplates: () => request<{ templates: CvTemplate[] }>("/cv/templates"),
  getCvStatus: () =>
    request<{
      cv_settings: CvSettings;
      has_cv: boolean;
      ats: AtsScore;
      has_uploaded_pdf: boolean;
      /** "" when no LaTeX engine is installed and PDFs fall back to Chromium. */
      latex_engine: string;
    }>("/cv/status"),
  setResumeSource: (resumeSource: "uploaded" | "generated") =>
    request<{ cv_settings: CvSettings }>("/cv/resume-source", {
      method: "POST",
      body: JSON.stringify({ resume_source: resumeSource }),
    }),
  getCvContent: () => request<{ markdown: string }>("/cv/content"),
  saveCv: (markdown: string) =>
    request<{ path: string; ats: AtsScore; is_placeholder?: boolean }>("/cv/save", {
      method: "POST",
      body: JSON.stringify({ markdown }),
    }),
  uploadCv: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${env.apiUrl}/cv/upload`, {
      method: "POST",
      headers: authHeadersMultipart(),
      body: form,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      let message = text || res.statusText;
      try {
        const parsed = JSON.parse(text) as { detail?: unknown };
        if (parsed.detail != null) {
          message = formatApiErrorDetail(parsed.detail);
        }
      } catch {
        /* keep raw */
      }
      throw new ApiError(message, res.status);
    }
    return res.json() as Promise<CvUploadResult>;
  },
  generateCv: (templateId: string, markdown?: string, pageTarget?: PageTarget) =>
    request<import("@/src/types/job").GenerateCvResult>("/cv/generate", {
      method: "POST",
      body: JSON.stringify({
        template_id: templateId,
        markdown: markdown ?? null,
        page_target: pageTarget ?? null,
      }),
    }),
  /** Object URL for the compiled PDF. Fetched rather than linked so the
   *  request carries the auth header; the caller must revoke it. */
  cvPdfObjectUrl: async () => {
    const res = await fetch(`${env.apiUrl}/cv/file/pdf`, { headers: authHeaders() });
    if (!res.ok) throw new ApiError(res.statusText, res.status);
    return URL.createObjectURL(await res.blob());
  },
  previewCv: (
    templateId: string,
    markdown?: string,
    useSample = false,
    /** false = readable type, paginate when long (default). true = try one page. */
    singlePage = false
  ) =>
    request<{ html: string; template_id: string }>("/cv/preview", {
      method: "POST",
      body: JSON.stringify({
        template_id: templateId,
        markdown: markdown !== undefined ? markdown : null,
        use_sample: useSample,
        single_page: singlePage,
      }),
    }),
  getCvArtifacts: () => request<CvArtifacts>("/cv/artifacts"),
  deleteCv: () => request<{ deleted: boolean }>("/cv", { method: "DELETE" }),
  downloadCvFile: async (fileType: "md" | "tex" | "pdf" | "uploaded") => {
    const res = await fetch(`${env.apiUrl}/cv/file/${fileType}`, {
      headers: authHeaders(),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new ApiError(text || res.statusText, res.status);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("content-disposition") ?? "";
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const filename = match?.[1] ?? `cv.${fileType === "md" ? "md" : fileType}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
  downloadFile: async (path: string, fallbackName: string) => {
    const res = await fetch(`${env.apiUrl}${path}`, { headers: authHeaders() });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new ApiError(text || res.statusText, res.status);
    }
    const blob = await res.blob();
    const match = /filename="?([^"]+)"?/.exec(res.headers.get("content-disposition") ?? "");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = match?.[1] ?? fallbackName;
    a.click();
    URL.revokeObjectURL(url);
  },
  downloadJobCvPdf: (jobId: string) =>
    api.downloadFile(`/jobs/${jobId}/cv-pdf`, "cv.pdf"),
  getOutcomeInsights: () =>
    request<{
      rates: Record<string, number>;
      learnings: { insight: string; key: string; confidence: number }[];
    }>("/outcomes/insights"),
  listReports: () => request<{ reports: string[] }>("/reports"),
  downloadReport: (name: string) =>
    api.downloadFile(`/reports/${encodeURIComponent(name)}`, name),
  getAutomation: () => request<AutomationSettings>("/settings/automation"),
  setAutomation: (body: Partial<AutomationSettings>) =>
    request<AutomationSettings>("/settings/automation", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  runScheduledScan: (dryRun = false, asyncRun = false) =>
    request<{ enqueued?: string; run_id?: string; stats?: Record<string, unknown> }>(
      `/scan/scheduled?dry_run=${dryRun ? "true" : "false"}&async_run=${asyncRun ? "true" : "false"}`,
      { method: "POST" }
    ),
  pipelineStats: () =>
    request<{
      pipeline: Record<string, number>;
      pipeline_targeted?: Record<string, number>;
      applications: Record<string, number>;
    }>("/pipeline/stats"),
  linkedInState: () => request<LinkedInOptimizerState>("/linkedin/optimizer/state"),
  linkedInAnalyze: (body: {
    text?: string;
    profile?: Partial<LinkedInProfile>;
    target_role?: string;
    linkedin_url?: string;
  }) =>
    request<{
      profile: LinkedInProfile;
      score: LinkedInScore;
      target_role: string;
      role: LinkedInRoleOption;
      beats: string[];
      linkedin_url?: string;
      source?: string;
      substantial?: boolean;
    }>("/linkedin/optimizer/analyze", { method: "POST", body: JSON.stringify(body) }),
  linkedInImportCv: (target_role?: string) =>
    request<LinkedInImportResult>("/linkedin/optimizer/import-cv", {
      method: "POST",
      body: JSON.stringify({ target_role: target_role || null }),
    }),
  linkedInImportUrl: (url?: string, target_role?: string) =>
    request<LinkedInImportResult>("/linkedin/optimizer/import-url", {
      method: "POST",
      body: JSON.stringify({ url: url || null, target_role: target_role || null }),
    }),
  linkedInSave: (profile: LinkedInProfile, target_role: string) =>
    request<{
      profile: LinkedInProfile;
      score: LinkedInScore;
      target_role: string;
    }>("/linkedin/optimizer/save", {
      method: "POST",
      body: JSON.stringify({ profile, target_role }),
    }),
  linkedInRewrite: (body: {
    section: string;
    profile?: LinkedInProfile;
    target_role?: string;
    use_llm?: boolean;
  }) =>
    request<LinkedInRewriteResult>("/linkedin/optimizer/rewrite", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  linkedInRewriteAll: (body: {
    profile?: LinkedInProfile;
    target_role?: string;
    use_llm?: boolean;
  }) =>
    request<{ sections: Record<string, LinkedInRewriteResult>; target_role: string }>(
      "/linkedin/optimizer/rewrite-all",
      { method: "POST", body: JSON.stringify(body) }
    ),
  linkedInCoverThemes: () =>
    request<{ themes: LinkedInCoverTheme[] }>("/linkedin/optimizer/cover/themes"),
  linkedInCoverRender: (body: {
    theme_id: string;
    name?: string;
    headline?: string;
    subline?: string;
  }) =>
    request<{
      theme_id: string;
      width: number;
      height: number;
      svg: string;
      mime: string;
      hint: string;
    }>("/linkedin/optimizer/cover/render", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export { ApiError };
