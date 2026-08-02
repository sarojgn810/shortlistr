"""
shortlistr — Interview Prep Generator

Builds a company + role interview guide:
  1. Free web research (DuckDuckGo; optional Google CSE / SerpAPI) for interview
     process + questions asked for this role — Serper not required
  2. JD-derived prompts
  3. Optional LLM STAR drafts grounded in the live cv.md
  4. Short labeled practice fallback when research is unavailable

Output: interview-prep/{job_id}.md (owner-stamped; never reuse foreign files)

Usage (standalone):
    python -m processors.generate_prep --company "Datadog" --role "Staff SRE"

Called by apply_queue.submit_approved() and Prep → Generate.
"""

import os
import re
import logging
from datetime import datetime

from config import CV_MD_PATH, PREP_DIR

logger = logging.getLogger(__name__)


# ── Role detection ─────────────────────────────────────────────────────────────

ROLE_SIGNALS = {
    "sre":      ["site reliability", "sre", "reliability engineer", "production engineer"],
    "mlops":    ["mlops", "ml engineer", "machine learning platform", "ml infra"],
    "devops":   ["devops", "devsecops", "ci/cd", "build engineer", "release engineer"],
    "platform": ["platform engineer", "developer platform", "internal platform", "infra engineer"],
    "aiops":    ["aiops", "ai ops", "observability platform", "self-healing", "autonomous"],
    "cloud":    ["cloud engineer", "cloud infrastructure", "cloud architect"],
    "security": ["devsecops", "security engineer", "appsec"],
}


def _detect_role_type(title: str, jd: str = "") -> str:
    text = (title + " " + jd).lower()
    for role, signals in ROLE_SIGNALS.items():
        if any(s in text for s in signals):
            return role
    return "general"


def _llm_practice_questions(
    company: str, role: str, jd: str, role_type: str
) -> list[tuple[str, str, str]]:
    """Questions written against this posting, not this job family.

    The static banks below are keyed by role family, so every SRE role got the
    same ten questions about a payment service and alert fatigue no matter who
    was hiring or what the description asked for. They were meant as a fallback
    for when web research found nothing — but research needs a search key, so on
    most installs the fallback is all anybody ever sees.

    The job description is already on hand and is the thing the interview will
    actually be about, so it is used directly. Returns [] on any failure and the
    static set takes over; a generic question is better than none.
    """
    if not (jd or "").strip():
        return []
    try:
        from llm import get_llm
    except Exception:
        return []
    provider = get_llm()
    if not provider or not provider.is_available():
        return []

    prompt = (
        f"You are preparing a candidate to interview at {company or 'this company'} "
        f"for: {role or role_type}.\n\n"
        "Write interview questions this specific posting invites — drawn from the "
        "systems, scale and responsibilities the description names. Prefer what is "
        "distinctive about it over what is true of the whole job family. Do not "
        "invent facts about the company that the description does not state.\n\n"
        "Return ONLY JSON:\n"
        '{"questions": [{"category": "SYSTEM DESIGN|TECHNICAL|BEHAVIOURAL|COMPANY FIT",'
        ' "question": "...", "hint": "what a strong answer covers"}]}\n\n'
        "Eight questions: one system design, four technical, two behavioural, one "
        "company fit. The hint is a short phrase, not a sentence.\n\n"
        f"JOB DESCRIPTION:\n{jd[:6000]}\n"
    )
    try:
        try:
            raw = provider.complete(prompt, max_tokens=2000, json_mode=True)
        except TypeError:
            raw = provider.complete(prompt, max_tokens=2000)
        from eval.service import _parse_json_response

        data = _parse_json_response(raw)
    except Exception as exc:
        logger.info("Prep questions: falling back to the practice set (%s)", exc)
        return []

    out: list[tuple[str, str, str]] = []
    for item in (data.get("questions") or [])[:12]:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        category = str(item.get("category") or "TECHNICAL").strip().upper()
        if category not in ("SYSTEM DESIGN", "TECHNICAL", "BEHAVIOURAL", "COMPANY FIT"):
            category = "TECHNICAL"
        label = category if category == "COMPANY FIT" else f"PRACTICE \u00b7 {category}"
        out.append((label, question, str(item.get("hint") or "").strip()))
    return out


def _fallback_practice_questions(role_type: str, company: str) -> list[tuple[str, str, str]]:
    """Short generic practice set — only used when web research finds nothing.

    Labeled clearly in the guide so it is never mistaken for company intel.
    """
    designs = _SYSTEM_DESIGN.get(role_type) or _SYSTEM_DESIGN.get("sre") or []
    tech_map = {
        "sre": _SRE_TECHNICAL,
        "platform": _PLATFORM_TECHNICAL,
        "mlops": _MLOPS_TECHNICAL,
        "aiops": _AIOPS_TECHNICAL,
        "devops": _DEVOPS_TECHNICAL,
        "cloud": _SRE_TECHNICAL,
        "security": _DEVOPS_TECHNICAL,
        "general": _SRE_TECHNICAL[:3] + _DEVOPS_TECHNICAL[:2],
    }
    tech = tech_map.get(role_type, _SRE_TECHNICAL)
    q: list[tuple[str, str, str]] = []
    for d in designs[:1]:
        q.append(("PRACTICE · SYSTEM DESIGN", d[0], d[1]))
    for t in tech[:4]:
        q.append(("PRACTICE · TECHNICAL", t[0], t[1]))
    for b in _COMMON_BEHAVIOURAL[:3]:
        q.append(("PRACTICE · BEHAVIOURAL", b[0], b[1]))
    q.append(
        (
            "COMPANY FIT",
            f"Why {company}?",
            "Research: product, engineering blog, recent public incidents",
        )
    )
    return q


def _jd_derived_questions(jd: str, company: str, role: str) -> list[str]:
    """Turn JD requirements into likely interview prompts."""
    if not jd:
        return []
    out: list[str] = []
    # Bullet-like requirement lines
    for line in jd.splitlines():
        line = re.sub(r"^[-*•\d.)\s]+", "", line).strip()
        if 40 <= len(line) <= 160 and not line.endswith("?"):
            low = line.lower()
            if any(
                k in low
                for k in (
                    "experience",
                    "knowledge",
                    "familiar",
                    "proficien",
                    "design",
                    "build",
                    "own",
                    "manage",
                    "kubernetes",
                    "aws",
                    "observab",
                    "pipeline",
                    "on-call",
                    "incident",
                )
            ):
                out.append(f"Tell me about your experience with: {line.rstrip('.')}.")
        if len(out) >= 4:
            break
    if company and role:
        out.insert(0, f"Why do you want to join {company} as a {role}?")
    return out[:5]

def _load_achievements(cv_md: str) -> list[str]:
    """Extract bullet achievements from cv.md."""
    if not cv_md:
        return []

    # Find any section containing achievements/experience bullets
    bullets = []
    in_section = False
    for line in cv_md.splitlines():
        if re.match(r'^##\s*(key achievements?|achievements?|experience|work experience)', line, re.I):
            in_section = True
            continue
        if in_section and re.match(r'^##', line):
            in_section = False
            continue
        if in_section:
            m = re.match(r'^[-*]\s*[✓✅]?\s*(.+)', line)
            if m:
                text = m.group(1).strip()
                if len(text) > 20:   # skip trivially short lines
                    bullets.append(text)

    return bullets[:12]   # cap at 12 proof points


def _load_skills(cv_md: str) -> list[str]:
    """Extract skills/tech stack from cv.md skills section."""
    if not cv_md:
        return []
    skills = []
    in_skills = False
    for line in cv_md.splitlines():
        if re.match(r'^##\s*(skills?|technical skills?|tech stack)', line, re.I):
            in_skills = True
            continue
        if in_skills and re.match(r'^##', line):
            break
        if in_skills:
            # Extract comma-separated or bulleted items
            line = re.sub(r'^[-*•]\s*', '', line.strip())
            line = re.sub(r'\*\*.*?\*\*:\s*', '', line)   # strip **Category**:
            for item in re.split(r'[,|]', line):
                item = item.strip()
                if 2 < len(item) < 40:
                    skills.append(item)
    return skills[:20]


# ── Question banks ─────────────────────────────────────────────────────────────

_COMMON_BEHAVIOURAL = [
    ("Tell me about a time you improved system reliability significantly.",
     "STAR+R: Situation, Task, Action, Result, Reflect"),
    ("Describe the most complex incident you've handled. Walk me through your decision-making.",
     "Focus: diagnosis speed, comms, root cause, follow-through"),
    ("How do you prioritise between toil reduction and shipping new features?",
     "Angle: error budget thinking, negotiation with product"),
    ("Tell me about a time you pushed back on a technical decision and were right.",
     "Show: data-driven, diplomatic, outcome-oriented"),
    ("Describe a time you had to work across teams to solve a reliability problem.",
     "Focus: stakeholder alignment, communication style"),
    ("What's the hardest on-call shift you've had? What did you learn?",
     "Angle: calm under pressure, systematic thinking, post-mortem culture"),
    ("Tell me about a project you led end-to-end. What would you do differently?",
     "Show: ownership, reflection, growth mindset"),
]

_SRE_TECHNICAL = [
    ("How do you define and implement SLOs for a payment processing service?",
     "Include: latency SLI, availability SLI, error budget policy, burn rate alerts"),
    ("Walk me through how you'd design the observability stack for a new microservice.",
     "Cover: metrics (RED), logs (structured), traces (distributed), dashboards, alerts"),
    ("How do you handle alert fatigue? How have you reduced it in practice?",
     "Angle: alert ownership, actionability, routing, escalation policy"),
    ("Explain how you'd do a zero-downtime migration of a high-traffic database.",
     "Cover: dual-write, blue-green, read replica promotion, rollback plan"),
    ("Kubernetes: how do you ensure a deployment doesn't reduce availability?",
     "Include: PodDisruptionBudgets, readiness probes, rolling update strategy, resource limits"),
    ("How does your team manage on-call rotation and avoid burnout?",
     "Cover: schedule fairness, runbook quality, escalation paths, post-on-call debrief"),
    ("What's the difference between error budget and error rate? How do you use them?",
     "Include: burn rate, budget consumption, freeze decisions, stakeholder comms"),
    ("Walk me through a canary deployment strategy for a critical API.",
     "Cover: traffic splitting, golden signals, automatic rollback triggers"),
    ("How do you handle cascading failures? Give an example.",
     "Include: circuit breakers, bulkheads, graceful degradation, runbook"),
    ("How do you approach capacity planning for a service with unpredictable traffic spikes?",
     "Cover: load testing, auto-scaling, headroom buffers, cost vs. reliability trade-off"),
]

_PLATFORM_TECHNICAL = [
    ("How would you design an internal developer platform from scratch?",
     "Cover: golden path, self-service APIs, paved road vs. escape hatch, adoption strategy"),
    ("How do you balance platform standardisation with engineering team autonomy?",
     "Angle: guardrails not gates, golden paths, opt-in vs. mandatory"),
    ("Describe your experience with Terraform at scale — module design, state management, drift.",
     "Include: remote state, workspaces, module versioning, Atlantis/TFC"),
    ("How do you handle secrets management across multiple environments and teams?",
     "Cover: Vault, AWS Secrets Manager, rotation, least-privilege, audit logging"),
    ("Walk me through your CI/CD pipeline design for a polyglot monorepo.",
     "Include: cache strategy, test parallelisation, environment promotion, rollback"),
    ("How do you measure platform adoption and developer experience?",
     "Cover: DORA metrics, deploy frequency, change failure rate, NPS, ticket volume"),
    ("How do you handle breaking changes in a shared infrastructure library?",
     "Include: semantic versioning, deprecation policy, migration guide, comms plan"),
]

_MLOPS_TECHNICAL = [
    ("How do you build a model serving infrastructure that handles traffic spikes?",
     "Cover: auto-scaling, model caching, latency SLOs, shadow mode serving"),
    ("Describe your approach to ML pipeline observability.",
     "Include: data drift detection, model performance metrics, retraining triggers"),
    ("How do you manage model versions across dev/staging/production?",
     "Cover: model registry, A/B testing, canary rollout, rollback"),
    ("What does a good feature store look like and when would you build vs. buy?",
     "Angle: consistency between training and serving, latency, operational overhead"),
    ("How do you handle training data versioning and reproducibility?",
     "Include: DVC, lineage tracking, experiment logging, artifact stores"),
]

_AIOPS_TECHNICAL = [
    ("How would you build a self-healing system that auto-remediates known failure patterns?",
     "Cover: pattern library, confidence thresholds, human-in-the-loop escalation, audit trail"),
    ("How do you apply anomaly detection to infrastructure metrics without flooding on-call?",
     "Include: baseline seasonality, dynamic thresholds, alert correlation, suppression"),
    ("What LLM/AI tooling have you used in an operational context?",
     "Angle: concrete use cases, accuracy vs. false-positive tradeoff, cost"),
    ("How do you ensure an AI-driven remediation system is safe to run in production?",
     "Cover: dry-run mode, blast radius limits, human approval gates, rollback"),
]

_DEVOPS_TECHNICAL = [
    ("How do you design a CI/CD pipeline for 100 microservices in a monorepo?",
     "Cover: affected-path detection, parallelism, caching, environment promotion"),
    ("How do you handle secrets in CI pipelines without storing them in code?",
     "Include: OIDC, secret injection, rotation, audit"),
    ("Walk me through how you'd implement GitOps for a Kubernetes cluster.",
     "Cover: ArgoCD/Flux, reconciliation loop, drift detection, progressive delivery"),
    ("How do you enforce security scanning in the CI pipeline without slowing teams down?",
     "Include: SAST, DAST, SCA, container scanning, shift-left vs. blocking"),
    ("How do you manage multiple environments (dev/staging/prod) in Terraform?",
     "Cover: workspaces vs. directories, variable hierarchy, remote state, drift"),
]

_SYSTEM_DESIGN = {
    "sre": [
        ("Design a distributed tracing system for 500 microservices.",
         "Cover: sampling strategy, trace propagation, storage (Jaeger/Tempo), query latency"),
        ("Design an alerting system that routes alerts to the right team automatically.",
         "Include: alert taxonomy, routing rules, escalation, dedup, AIOps enrichment"),
    ],
    "platform": [
        ("Design an internal service catalog that tracks 200 microservices.",
         "Cover: ownership, dependencies, SLOs, runbooks, onboarding, search"),
        ("Design a self-service infrastructure provisioning system.",
         "Include: request → approval → Terraform → notification flow, guardrails"),
    ],
    "mlops": [
        ("Design an ML feature store for real-time and batch features.",
         "Cover: online (Redis) vs offline (S3/BQ) store, feature computation, consistency"),
        ("Design a model evaluation pipeline for safe production rollout.",
         "Include: shadow mode, A/B split, metric collection, auto-promote/rollback"),
    ],
    "aiops": [
        ("Design an autonomous incident remediation system.",
         "Cover: detection → classification → action library → blast radius → audit"),
    ],
    "devops": [
        ("Design a multi-region deployment pipeline with automatic rollback.",
         "Cover: traffic shifting, health checks, region isolation, state management"),
    ],
    "cloud": [
        ("Design a multi-cloud disaster recovery strategy.",
         "Cover: RTO/RPO targets, data replication, DNS failover, runbook, testing cadence"),
    ],
}

_COMPANY_FIT = [
    ("Why {company}?",
     "Research: product, engineering blog, reliability culture, recent incidents they've published"),
    ("What do you know about {company}'s tech stack and infrastructure challenges?",
     "Angle: show you've read their engineering blog / job descriptions carefully"),
    ("Where do you see yourself in 3 years at a company like {company}?",
     "Angle: technical depth → influence → broader ownership; not management for its own sake"),
    ("What's your preferred working style in a remote/async team?",
     "Cover: documentation habit, async-first comms, timezone flexibility, outcome focus"),
    ("Do you have any questions for us?",
     "Prepare 3–5 genuine questions: on-call culture, error budget process, eng roadmap, team growth"),
]


def _get_question_bank(role_type: str, company: str) -> list[tuple]:
    """Deprecated alias — short practice fallback only."""
    return _fallback_practice_questions(role_type, company)


# Map shorthand to full list
_BEHAVIOURAL = _COMMON_BEHAVIOURAL


# ── Markdown builder ───────────────────────────────────────────────────────────

def _build_prep_doc(job: dict, cv_md: str) -> str:
    company = job.get("company", "Company")
    title = job.get("title", "Role")
    url = job.get("url", "")
    jd = job.get("jd_text") or job.get("jd_snippet", "") or ""
    job_id = str(job.get("job_id") or job.get("id") or "").strip()
    fit_score = job.get("fit_score", 0)
    eval_score = job.get("eval_score")
    fit_reason = job.get("fit_reason", "")
    role_type = _detect_role_type(title, jd)
    date_str = datetime.now().strftime("%Y-%m-%d")

    achievements = _load_achievements(cv_md)
    skills = _load_skills(cv_md)

    from prep.ownership import front_matter, owner_key
    from prep.research import draft_star_answers, research_interview

    research = research_interview(company, title, jd=jd)
    researched_qs = list(research.get("questions") or [])
    for q in _jd_derived_questions(jd, company, title):
        if q.lower() not in {x.lower() for x in researched_qs}:
            researched_qs.append(q)

    use_research = research.get("mode") == "researched" and (
        researched_qs or research.get("process")
    )
    answers: dict[str, str] = {}
    if researched_qs:
        answers = draft_star_answers(
            researched_qs,
            company=company,
            role=title,
            cv_excerpt=cv_md,
            jd=jd,
        )

    owner = owner_key()
    header = front_matter(job_id=job_id or "unknown", owner=owner, company=company, role=title)

    try:
        eval_n = float(eval_score) if eval_score is not None else 0.0
    except (TypeError, ValueError):
        eval_n = 0.0
    try:
        disc_n = float(fit_score) if fit_score is not None else 0.0
    except (TypeError, ValueError):
        disc_n = 0.0
    if eval_n > 0:
        fit_line = f"**Fit Score:** {eval_n:.1f}/5 (evaluated)"
    elif disc_n > 0:
        fit_line = f"**Fit Score:** {disc_n:.0f}/100 (discovery)"
    else:
        fit_line = "**Fit Score:** not scored yet"

    cand_name = ""
    try:
        from config import CANDIDATE

        cand_name = str((CANDIDATE or {}).get("name") or "").strip()
    except Exception:
        pass

    lines = [
        f"# Interview Prep — {company}",
        f"**Role:** {title}  |  **Date:** {date_str}  |  {fit_line}",
        "",
    ]
    if cand_name:
        lines += [f"**Prepared for:** {cand_name}", ""]
    if url:
        lines += [f"**Job URL:** {url}", ""]
    if fit_reason:
        lines += [f"**Why this fit:** {fit_reason}", ""]

    # Research provenance
    mode_label = (
        "Web-researched for this company + role"
        if use_research
        else "Generic practice set (no company-specific intel yet)"
    )
    lines += [
        f"**Guide source:** {mode_label}",
        "",
    ]
    for note in research.get("notes") or []:
        lines.append(f"> {note}")
    if research.get("notes"):
        lines.append("")

    if jd:
        lines += [
            "---",
            "## Job Description Highlights",
            "",
            jd[:800] + ("..." if len(jd) > 800 else ""),
            "",
        ]

    # Company interview process
    lines += [
        "---",
        f"## How {company} typically interviews",
        "",
    ]
    process = list(research.get("process") or [])
    if process:
        for b in process:
            lines.append(f"- {b}")
        lines.append("")
    else:
        lines += [
            f"_No public process summary found yet for {company}. "
            "Check their careers page, eng blog, and Glassdoor/Blind before the loop._",
            "",
        ]

    sources = list(research.get("sources") or [])
    if sources:
        lines += ["### Sources", ""]
        for s in sources[:6]:
            title_s = s.get("title") or s.get("url")
            url_s = s.get("url") or ""
            if url_s:
                lines.append(f"- [{title_s}]({url_s})")
            else:
                lines.append(f"- {title_s}")
        lines.append("")

    if achievements:
        lines += [
            "---",
            "## Your Proof Points",
            "_Match these to questions. Don't memorise — internalize._",
            "",
        ]
        for a in achievements:
            lines.append(f"- {a}")
        lines.append("")

    if skills:
        lines += [
            "## Key Skills to Reference",
            "",
            ", ".join(skills),
            "",
        ]

    # Questions
    lines += ["---", "## Interview Questions", ""]
    if use_research and researched_qs:
        lines += [
            f"_Questions gathered for **{title}** at **{company}** from public web "
            "results and the job description. Draft answers use your live résumé "
            "when an LLM is configured; otherwise fill the STAR slots._",
            "",
        ]
        current_cat = "RESEARCHED"
        lines += [f"### {current_cat}", ""]
        for question in researched_qs:
            draft = answers.get(question) or ""
            lines += [f"**Q: {question}**", ""]
            if draft:
                lines += ["**Draft answer (edit before use):**", "", draft, ""]
            else:
                lines += [
                    "**My answer:**",
                    "- Situation:",
                    "- Task:",
                    "- Action:",
                    "- Result:",
                    "- Reflect (what I'd do differently):",
                    "",
                ]
    else:
        questions = _llm_practice_questions(company, title, jd, role_type)
        if questions:
            lines += [
                "_Written against this job description. Company interview intel "
                "needs a web search key — see Connections._",
                "",
            ]
        else:
            lines += [
                f"_No company-specific questions found. Short **{role_type}** practice "
                f"set below — add an AI key in Connections for questions written "
                "against this posting, or a Google CSE key for company intel._",
                "",
            ]
            questions = _fallback_practice_questions(role_type, company)
        current_cat = None
        for cat, question, hint in questions:
            if cat != current_cat:
                current_cat = cat
                lines += [f"### {cat}", ""]
            lines += [
                f"**Q: {question}**",
                f"> {hint}",
                "",
                "**My answer:**",
                "- Situation:",
                "- Task:",
                "- Action:",
                "- Result:",
                "- Reflect (what I'd do differently):",
                "",
            ]

    # ── What to study, and in what order ────────────────────────────────────
    # The path is derived from the JD's own requirements, so it is useful even
    # when the web turns up nothing. The reading list is not: it needs search,
    # and free DuckDuckGo is frequently bot-challenged (HTTP 202). Say that
    # plainly rather than printing an empty heading the user cannot explain.
    try:
        from prep.research import research_learning_resources

        learning = research_learning_resources(title, jd=jd, skills=skills)
    except Exception:
        learning = {"resources": [], "path": [], "topics": []}

    if learning.get("path") or learning.get("resources"):
        lines += ["---", "## Prep Path", ""]
        for n, step in enumerate(learning.get("path") or [], 1):
            lines.append(f"{n}. {step}")
        lines.append("")

        resources = learning.get("resources") or []
        if resources:
            lines += ["### Learning material", ""]
            for r in resources:
                title_txt = str(r.get("title") or r.get("link"))
                lines.append(f"- [{title_txt}]({r.get('link')})")
                if r.get("snippet"):
                    lines.append(f"  > {r['snippet']}")
            lines.append("")
        else:
            lines += [
                "### Learning material",
                "",
                "_No reading list — web search is unavailable (DuckDuckGo is "
                "returning a bot challenge). Add a free Serper or Google CSE key "
                "under Connections and regenerate to fill this in._",
                "",
            ]

    lines += [
        "---",
        "## Pre-Interview Research Checklist",
        "",
        f"- [ ] Read {company}'s engineering blog / careers interview tips",
        f"- [ ] Check {company}'s recent outage post-mortems / status page",
        f"- [ ] Confirm interview loop (recruiter → HM → panel → offer)",
        f"- [ ] Know their product and who their customers are",
        f"- [ ] Prepare 3–5 thoughtful questions to ask the interviewer",
        f"- [ ] Review your STAR stories against the questions above",
        "",
    ]

    return header + "\n".join(lines)


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_prep_for_job(job: dict) -> dict:
    """
    Generate interview prep guide for a single job.

    Returns:
        {"success": bool, "path": str, "error": str}
    """
    os.makedirs(PREP_DIR, exist_ok=True)

    cv_md = ""
    if os.path.exists(CV_MD_PATH):
        with open(CV_MD_PATH, encoding="utf-8") as f:
            cv_md = f.read()

    content  = _build_prep_doc(job, cv_md)
    try:
        from writing.sanitize import sanitize

        # Keep YAML front matter intact — sanitize body only.
        from prep.ownership import parse_front_matter, front_matter, owner_key

        meta, body = parse_front_matter(content)
        body = sanitize(body, mode="prose")
        job_id = str(job.get("job_id") or job.get("id") or meta.get("job_id") or "unknown")
        content = front_matter(
            job_id=job_id,
            owner=owner_key(),
            company=str(job.get("company") or ""),
            role=str(job.get("title") or ""),
        ) + body
    except Exception:
        pass

    from prep.ownership import prep_path_for_job

    job_id = str(job.get("job_id") or job.get("id") or "").strip()
    if job_id:
        path = prep_path_for_job(job_id)
    else:
        company  = re.sub(r'[^\w\s-]', '', job.get("company", "Company")).strip().replace(" ", "_")
        role     = re.sub(r'[^\w\s-]', '', job.get("title", "Role")).strip().replace(" ", "_")
        date_str = datetime.now().strftime("%Y-%m-%d")
        path     = os.path.join(PREP_DIR, f"{company}-{role}-{date_str}.md")

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Prep guide → {path}")
        return {"success": True, "path": path}
    except Exception as e:
        logger.error(f"Could not write prep guide: {e}")
        return {"success": False, "path": path, "error": str(e)}


def generate_prep_batch(jobs: list[dict]) -> list[dict]:
    """Generate prep guides for a list of approved jobs."""
    results = []
    for job in jobs:
        result = generate_prep_for_job(job)
        result["job"] = job
        results.append(result)
    return results


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    parser = argparse.ArgumentParser(description="Generate interview prep guide for a job")
    parser.add_argument("--company", default="Company", help="Company name")
    parser.add_argument("--role",    default="Site Reliability Engineer", help="Role title")
    parser.add_argument("--url",     default="", help="Job URL (optional)")
    parser.add_argument("--jd",      default="", help="JD snippet (optional)")
    args = parser.parse_args()

    job = {
        "company":    args.company,
        "title":      args.role,
        "url":        args.url,
        "jd_snippet": args.jd,
        "fit_score":  0,
    }
    result = generate_prep_for_job(job)
    if result["success"]:
        print(f"Generated: {result['path']}")
    else:
        print(f"Error: {result.get('error', '?')}")
