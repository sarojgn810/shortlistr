"""ATS readiness scoring for CV content (0–100). Content structure only — not job-fit match."""

from __future__ import annotations

import re

from cv.parser import infer_cv_name, parse_cv_markdown

# Bullets: -, *, •, ●, numbered lists; optional space after marker (common in PDF extract)
_BULLET = re.compile(
    r"(?m)^(?:[\-\*•●○◦▪]\s*\S|\d+[\.\)]\s+\S)",
)
_METRIC = re.compile(r"\d+\s*%|\d+\+|\$\s*\d+|\d+\s*(?:x|X)\b|(?:reduced|cut|improved|increased|decreased)\s+(?:by\s+)?\d+")
_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")
_LINKEDIN = re.compile(r"linkedin\.com", re.I)


def _experience_text(md: str, sections) -> str:
    """Experience body plus preamble lines that look like roles (PDF dumps)."""
    blocks = [sections.experience]
    if sections.extra:
        blocks.extend(sections.extra.values())
    # Raw ## EXPERIENCE section from markdown (captures ### job lines)
    m = re.search(
        r"(?ms)^##\s+(?:PROFESSIONAL\s+)?EXPERIENCE\s*\n(.*?)(?=^##\s|\Z)",
        md,
    )
    if m:
        blocks.append(m.group(1))
    return "\n".join(b for b in blocks if b).strip()


def score_ats_readiness(
    md: str,
    *,
    template_id: str = "",
    include_template: bool = True,
) -> dict:
    """
    Score how well cv.md is structured for ATS parsers.

    - Content checks sum to 95 points (name, contact, summary, skills, experience, metrics, education, certs).
    - Template bonus is 5 points when include_template=True and a template is selected.
    - During resume upload (before template step), pass include_template=False for a content-only score /100.
    """
    sections = parse_cv_markdown(md)
    name = infer_cv_name(md, sections)
    exp_text = _experience_text(md, sections)
    checks: list[dict] = []
    score = 0

    def add(
        points: int,
        label: str,
        ok: bool,
        *,
        pass_detail: str = "",
        fail_hint: str = "",
    ) -> None:
        nonlocal score
        earned = points if ok else 0
        score += earned
        checks.append(
            {
                "label": label,
                "ok": ok,
                "points": earned,
                "max_points": points,
                "hint": pass_detail if ok else fail_hint,
            }
        )

    has_name = bool(name)
    add(
        10,
        "Name",
        has_name,
        pass_detail=f"Found: {name[:40]}",
        fail_hint="Add a `# Your Full Name` heading at the top of the resume",
    )

    has_contact = bool(
        sections.contact.strip()
        or _EMAIL.search(md)
        or (_PHONE.search(md) and (_EMAIL.search(md) or _LINKEDIN.search(md)))
    )
    add(
        10,
        "Contact details",
        has_contact,
        pass_detail="Email or phone/LinkedIn detected",
        fail_hint="Add email, phone, and LinkedIn in a line under your name",
    )

    summary_len = len(sections.summary.strip())
    has_summary = summary_len >= 50
    add(
        15,
        "Professional summary",
        has_summary,
        pass_detail=f"{summary_len} characters",
        fail_hint="Add a ## PROFESSIONAL SUMMARY section (2–4 lines: role, years, stack, impact)",
    )

    skills_text = sections.skills.strip()
    skill_tokens = [t.strip() for t in re.split(r"[,;|\n]", skills_text) if t.strip()]
    has_skills = len(skills_text) >= 25 or len(skill_tokens) >= 4
    add(
        15,
        "Skills / competencies",
        has_skills,
        pass_detail=f"{len(skill_tokens) or 'multiple'} keywords",
        fail_hint="Add a ## CORE COMPETENCIES or ## SKILLS section with comma-separated keywords",
    )

    has_bullets = bool(_BULLET.search(exp_text) or _BULLET.search(md))
    exp_substance = len(exp_text) >= 60 or (has_bullets and len(exp_text) >= 30)
    has_experience = exp_substance and (has_bullets or exp_text.count("\n") >= 2)
    add(
        20,
        "Work experience",
        has_experience,
        pass_detail="Roles with bullet points" if has_bullets else "Experience section present",
        fail_hint="Add ## PROFESSIONAL EXPERIENCE with `-` bullet lines and metrics per role",
    )

    metric_haystack = f"{sections.summary}\n{exp_text}"
    has_metrics = bool(_METRIC.search(metric_haystack))
    add(
        10,
        "Quantified impact",
        has_metrics,
        pass_detail="Numbers or percentages found",
        fail_hint="Add measurable outcomes (e.g. cut MTTR 40%, 99.9% uptime, $2M saved)",
    )

    has_education = len(sections.education.strip()) >= 8
    add(
        10,
        "Education",
        has_education,
        pass_detail="Education section present",
        fail_hint="Add an ## EDUCATION section with degree and school",
    )

    has_certs = len(sections.certifications.strip()) >= 3
    add(
        5,
        "Certifications",
        has_certs,
        pass_detail="Listed",
        fail_hint="Optional: add ## CERTIFICATIONS (CKA, AWS, etc.) for SRE/DevOps roles",
    )

    template_ok = bool(template_id and template_id.strip())
    if include_template:
        add(
            5,
            "ATS template selected",
            template_ok,
            pass_detail=template_id or "",
            fail_hint="Pick a template in the next step — does not affect resume text parsing",
        )

    content_max = 95 if include_template else 100
    content_score = min(content_max, score)
    if include_template and not template_ok:
        # Content score without template penalty for display
        content_only = min(95, sum(c["points"] for c in checks if c["label"] != "ATS template selected"))
    else:
        content_only = content_score

    total = min(100, score)
    tier = (
        "excellent"
        if total >= 90
        else "strong"
        if total >= 75
        else "good"
        if total >= 60
        else "needs work"
    )

    fixes = [
        {"label": c["label"], "hint": c["hint"]}
        for c in checks
        if not c["ok"] and c.get("hint")
    ]

    passed = [c for c in checks if c["ok"]]

    return {
        "score": total,
        "content_score": content_only,
        "ats_readiness": total,
        "job_match_percent": content_only,  # legacy field — content readiness, not job fit
        "tier": tier,
        "checks": checks,
        "passed": passed,
        "fixes": fixes,
        "template_id": template_id or "",
        "include_template": include_template,
    }
