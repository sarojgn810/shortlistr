"""
shortlistr — Cover Letter Generator

Two modes (selected automatically based on profile.yml → llm.provider):

  LLM mode   — calls get_llm().complete() for a fully personalized letter
  Template   — résumé/JD overlap bullets (no fixed SRE skill map)

Both produce the same dict structure:
    {"subject": str, "body": str, "mode": "llm" | "template"}
"""

import os
import re
import logging
from config import CANDIDATE

logger = logging.getLogger(__name__)


def _cv_markdown() -> str:
    try:
        from config import CV_MD_PATH

        if os.path.exists(CV_MD_PATH):
            return open(CV_MD_PATH, encoding="utf-8").read()
    except Exception:
        pass
    return ""


def _skill_phrases_from_cv(cv_md: str) -> list[str]:
    try:
        from cv.parser import parse_cv_markdown

        sections = parse_cv_markdown(cv_md or "")
        blob = (sections.skills or "").strip()
        if not blob:
            return []
        parts = re.split(r"[,;/\n•·|]+", blob)
        out: list[str] = []
        for p in parts:
            s = p.strip()
            if 2 <= len(s) <= 60 and s.lower() not in {x.lower() for x in out}:
                out.append(s)
        return out[:40]
    except Exception:
        return []


def _experience_bullets_from_cv(cv_md: str, *, limit: int = 8) -> list[str]:
    """Pull measurable-looking bullets from the experience section."""
    bullets: list[str] = []
    in_exp = False
    for raw in (cv_md or "").splitlines():
        line = raw.strip()
        heading = line.lstrip("#").strip().lower()
        if heading in (
            "professional experience",
            "experience",
            "work experience",
            "employment",
        ):
            in_exp = True
            continue
        if in_exp and line.startswith("#"):
            break
        if not in_exp:
            continue
        m = re.match(r"^[-*•]\s+(.+)$", line)
        if m:
            text = m.group(1).strip()
            if len(text) >= 20:
                bullets.append(text[:220])
        if len(bullets) >= limit:
            break
    return bullets


def _template_bullets(job: dict, cv_md: str) -> list[str]:
    """Pick up to 3 proof points from the user's CV that overlap the JD."""
    jd = (job.get("jd_snippet") or job.get("jd_text") or "").lower()
    title = (job.get("title") or "").lower()
    hay = f"{jd} {title}"

    skills = _skill_phrases_from_cv(cv_md)
    matched_skills: list[str] = []
    for skill in skills:
        if skill.lower() in hay:
            matched_skills.append(skill)
        if len(matched_skills) >= 5:
            break

    exp = _experience_bullets_from_cv(cv_md)
    skill_l = [s.lower() for s in matched_skills]
    ranked_exp: list[str] = []
    for b in exp:
        bl = b.lower()
        if any(s in bl for s in skill_l) or (
            hay and any(tok in bl for tok in hay.split() if len(tok) > 4)
        ):
            ranked_exp.append(b)
    if not ranked_exp:
        ranked_exp = exp[:3]

    bullets: list[str] = []
    for b in ranked_exp[:3]:
        bullets.append(f"• {b if b.endswith('.') else b + '.'}")
    if len(bullets) < 3 and matched_skills:
        for skill in matched_skills:
            if len(bullets) >= 3:
                break
            bullets.append(
                f"• Hands-on experience with {skill}, relevant to this {job.get('title') or 'role'}."
            )

    if not bullets:
        titles = []
        try:
            import config as _cfg

            titles = list(_cfg.SEARCH_KEYWORDS or [])[:2]
        except Exception:
            pass
        focus = ", ".join(titles) if titles else "the areas this role emphasises"
        bullets = [
            "• A track record of delivering measurable results in roles like this one.",
            f"• Background aligned with {focus}.",
            "• Clear communication, ownership, and a bias for shipping.",
        ]
    return bullets[:3]


def _template_letter(job: dict) -> str:
    """Résumé-grounded template cover letter (no fixed field map)."""
    company = job.get("company", "your company")
    title = job.get("title", "the role")
    yoe = CANDIDATE.get("years_exp") or "several"
    cv_md = _cv_markdown()
    bullets = _template_bullets(job, cv_md)
    skill_block = "\n".join(bullets)

    name = CANDIDATE.get("name", "")
    email = CANDIDATE.get("email", "")
    phone = CANDIDATE.get("phone", "")
    linkedin = CANDIDATE.get("linkedin", "")
    github = CANDIDATE.get("github", "")
    contact_lines = "\n".join(x for x in [phone, email, linkedin, github] if x)

    return f"""Dear Hiring Manager,

I am writing to apply for the {title} position at {company}. With {yoe}+ years of relevant hands-on experience, I believe I can make an immediate contribution to your team.

Three areas where my background maps to what you are looking for:
{skill_block}

I work well in async, ownership-heavy teams and would welcome the chance to discuss how my experience fits {company}'s needs.

Warm regards,
{name}
{contact_lines}""".strip()


def _llm_letter(job: dict, llm) -> str:
    """Use the configured LLM to produce a personalized cover letter."""
    company = job.get("company", "the company")
    title = job.get("title", "the role")
    jd = job.get("jd_snippet", "") or ""
    name = CANDIDATE.get("name", "")
    yoe = CANDIDATE.get("years_exp") or "several"
    phone = CANDIDATE.get("phone", "")
    email = CANDIDATE.get("email", "")
    linkedin = CANDIDATE.get("linkedin", "")
    github = CANDIDATE.get("github", "")

    contact_block = "\n".join(x for x in [name, phone, email, linkedin, github] if x)

    system = (
        "You are a professional cover letter writer. "
        "Write concise, confident, and specific letters. "
        "No fluff. No clichés. The letter should read like it was written by the candidate, not a recruiter."
    )

    cv_md = _cv_markdown()[:3000]

    prompt = f"""Write a cover letter for the following job application.

Candidate: {name} ({yoe} years of experience)
Role: {title}
Company: {company}

Candidate résumé (ground the letter in this real background — do NOT assume a field):
{cv_md or "Not provided."}

Job description excerpt:
{jd[:1500] if jd else "Not provided."}

Requirements:
- 3 short paragraphs maximum
- Opening: directly state the role and strongest relevant qualifier
- Middle: 2–3 specific skills from the JD, with a brief proof point each
- Closing: one line on culture fit, one line requesting a conversation
- End with "Warm regards," then a blank line, then this contact block exactly:
{contact_block}

Do not include a subject line. Do not use generic phrases like "I am a highly motivated professional".
"""

    try:
        return llm.complete(prompt, system=system, max_tokens=600)
    except Exception as e:
        logger.warning(f"LLM cover letter failed ({e}) — falling back to template")
        return _template_letter(job)


def generate_cover_letter(job: dict) -> dict:
    """
    Generate a cover letter for a job dict.

    Returns:
        {
            "subject": str,
            "body":    str,   # the letter text
            "mode":    "llm" | "template"
        }
    """
    try:
        from llm import get_llm
        llm = get_llm()
    except Exception:
        llm = None

    if llm and llm.is_available():
        body = _llm_letter(job, llm)
        mode = "llm"
    else:
        body = _template_letter(job)
        mode = "template"

    subject = generate_subject(job)
    return {"subject": subject, "body": body, "mode": mode}


def generate_subject(job: dict) -> str:
    """Generate the application email subject line."""
    name = CANDIDATE.get("name", "Applicant")
    yoe = CANDIDATE.get("years_exp") or ""
    title = job.get("title") or "the role"
    yoe_str = f"{yoe} YOE " if yoe else ""
    return f"Application: {title} | {yoe_str}{name}"
