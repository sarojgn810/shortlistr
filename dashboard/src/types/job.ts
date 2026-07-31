export interface Job {
  id: string;
  url: string;
  source: string;
  company: string | null;
  title: string | null;
  location: string | null;
  jd_text: string | null;
  salary: string | null;
  skills?: string[];
  experience?: string | null;
  fit_score: number;
  fit_reason: string;
  status: string;
  discovered_at: string | null;
  notes?: string;
  company_email?: string | null;
  apply_channel?: string;
  pipeline_status?: string | null;
  eval_score?: number | null;
  legitimacy?: string | null;
  eval_blocks?: Record<string, string>;
  eval_template_only?: boolean;
}

export interface Application {
  id: number;
  job_id: string | null;
  company: string | null;
  role: string | null;
  score: number | null;
  status: string | null;
  applied_date: string | null;
  report_path: string | null;
  notes: string | null;
  created_at?: string;
}

export interface ExplainResult {
  job_id: string;
  company: string | null;
  role: string | null;
  score: number;
  eval_score?: number | null;
  fit_score?: number;
  legitimacy?: string;
  bullets: string[];
  summary: string;
}

export interface EvalResult {
  score: number;
  legitimacy?: string;
  recommendation?: string;
  summary?: string;
  company?: string;
  role?: string;
  blocks?: Record<string, string>;
  explain?: ExplainResult;
  job?: Job;
  template_only?: boolean;
}

export interface ResumeDiff {
  job_id: string;
  company: string;
  role: string;
  change_count: number;
  additions: number;
  removals: number;
  diff: string[];
  baseline_path?: string | null;
  tailored_preview?: string;
  summary?: string;
  highlights?: string[];
  same_as_baseline?: boolean;
  pdf_ready?: boolean;
  pdf_path?: string | null;
}

export interface ApplicationReceipt {
  id: number;
  job_id: string;
  channel: string;
  fields?: Record<string, unknown>;
  resume_path?: string | null;
  cover_letter_text?: string | null;
  submitted_at?: string;
}

export interface CoverLetter {
  subject: string;
  body: string;
  mode: "llm" | "template";
}

export interface PrepBundle {
  job_id: string;
  company: string;
  role: string;
  url: string;
  apply_channel?: string;
  source?: string;
  cover_letter: CoverLetter;
  prep_path?: string | null;
  prep_content?: string | null;
  cv_pdf_path?: string | null;
  diff?: ResumeDiff | { error?: string };
  candidate_name?: string;
  owner?: string;
  fit_score?: number;
  eval_score?: number | null;
  fit_label?: string;
  fit_reason?: string;
  fit_primary?: number;
  fit_scale?: string;
}

export interface TrackerCard {
  job_id: string;
  company: string | null;
  title: string | null;
  url: string | null;
  location?: string | null;
  salary?: string | null;
  source?: string | null;
  skills?: string[];
  experience?: string | null;
  pipeline_status: string | null;
  application_status: string | null;
  score: number | null;
  legitimacy?: string | null;
  applied_date?: string | null;
  application_id?: number | null;
  updated_at?: string | null;
}

export interface TrackerBoard {
  columns: {
    review: TrackerCard[];
    approved: TrackerCard[];
    submitted: TrackerCard[];
    active: TrackerCard[];
  };
  counts: Record<string, number>;
}

export interface DiscoverResult {
  run_id?: string;
  discovered?: number;
  relevant?: number;
  off_target?: number;
  kept?: number;
  dropped_off_target?: number;
  dropped_low_fit?: number;
  stats?: Record<string, unknown>;
  enqueued?: number;
  dry_run?: boolean;
}

export interface PipelineTransitionResult {
  job_id: string;
  status: string;
  previous?: string;
}

export interface ApplyAssistReport {
  filled: string[];
  unfilled: string[];
  url?: string;
  submit_detected: boolean;
  errors?: string[];
}

export interface GenerateCvResult {
  template_id: string;
  tex_path: string;
  pdf_path: string | null;
  pdf_ok: boolean;
  pdf_engine: string | null;
  pdf_error: string | null;
  /** Measured from the compiled PDF, not estimated. */
  pages: number;
  page_target: number;
  /** False when the résumé could not be squeezed into the requested pages. */
  fitted: boolean;
  density: string | null;
  ats: import("@/src/lib/api/client").AtsScore;
}
