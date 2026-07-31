"""
shortlistr — Interview Prep Generator

Generates a role-specific interview prep guide for each approved job.
Pulls proof points from cv.md (repo root) and tailors question sets to the role type.

Output: interview-prep/{Company}-{Role}-{date}.md

Usage (standalone):
    python -m processors.generate_prep --company "Datadog" --role "Staff SRE"

Called automatically by apply_queue.submit_approved() for each approved job.
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
    return "sre"  # default


# ── CV proof-point loader ──────────────────────────────────────────────────────

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
    """Assemble the full question set for a role type."""
    q = []

    # System design (2)
    designs = _SYSTEM_DESIGN.get(role_type, _SYSTEM_DESIGN["sre"])
    q += [("SYSTEM DESIGN", d[0], d[1]) for d in designs]

    # Technical deep-dives (role-specific)
    tech_map = {
        "sre":      _SRE_TECHNICAL,
        "platform": _PLATFORM_TECHNICAL,
        "mlops":    _MLOPS_TECHNICAL,
        "aiops":    _AIOPS_TECHNICAL,
        "devops":   _DEVOPS_TECHNICAL,
        "cloud":    _SRE_TECHNICAL,
        "security": _DEVOPS_TECHNICAL,
    }
    tech = tech_map.get(role_type, _SRE_TECHNICAL)
    q += [("TECHNICAL", t[0], t[1]) for t in tech[:8]]

    # Behavioural (6)
    q += [("BEHAVIOURAL", b[0], b[1]) for b in _BEHAVIOURAL[:6]]

    # Company fit (4)
    fit = [("COMPANY FIT", f[0].format(company=company), f[1]) for f in _COMPANY_FIT]
    q += fit

    return q


# Map shorthand to full list
_BEHAVIOURAL = _COMMON_BEHAVIOURAL


# ── Markdown builder ───────────────────────────────────────────────────────────

def _build_prep_doc(job: dict, cv_md: str) -> str:
    company   = job.get("company", "Company")
    title     = job.get("title", "Role")
    url       = job.get("url", "")
    jd        = job.get("jd_snippet", "")
    job_id    = str(job.get("job_id") or job.get("id") or "").strip()
    fit_score = job.get("fit_score", 0)
    eval_score = job.get("eval_score")
    fit_reason= job.get("fit_reason", "")
    role_type = _detect_role_type(title, jd)
    date_str  = datetime.now().strftime("%Y-%m-%d")

    achievements = _load_achievements(cv_md)
    skills       = _load_skills(cv_md)
    questions    = _get_question_bank(role_type, company)

    from prep.ownership import front_matter, owner_key

    owner = owner_key()
    header = front_matter(job_id=job_id or "unknown", owner=owner, company=company, role=title)

    # Prefer eval /5 when present; else discovery /100.
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

    # ── JD highlights ──
    if jd:
        lines += [
            "---",
            "## Job Description Highlights",
            "",
            jd[:800] + ("..." if len(jd) > 800 else ""),
            "",
        ]

    # ── Your proof points ──
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

    # ── Skills to name-drop ──
    if skills:
        lines += [
            "## Key Skills to Reference",
            "",
            ", ".join(skills),
            "",
        ]

    # ── Questions by category ──
    lines += [
        "---",
        "## Interview Questions",
        "",
        "_Format: write your answer skeleton in the STAR+R slot below each question._",
        "",
    ]

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

    # ── Research checklist ──
    lines += [
        "---",
        "## Pre-Interview Research Checklist",
        "",
        f"- [ ] Read {company}'s engineering blog",
        f"- [ ] Check {company}'s recent outage post-mortems / status page",
        f"- [ ] Review {company}'s tech stack (LinkedIn, StackShare, job descriptions)",
        f"- [ ] Know their product and who their customers are",
        f"- [ ] Prepare 3–5 thoughtful questions to ask the interviewer",
        f"- [ ] Review your STAR stories one more time",
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
