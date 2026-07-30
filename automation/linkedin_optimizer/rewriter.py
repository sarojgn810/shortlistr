"""Evidence-grounded LinkedIn section rewrites — no invented employers or metrics.

Rules:
- Only rephrase / reorder content that already exists in the profile (or CV corpus).
- Missing recruiter keywords are listed as recommendations, not silently invented
  as facts.
- Never invent employers, job titles, or fake N% metrics.
- Works offline without an LLM; optional LLM polish must keep the same constraints.
"""

from __future__ import annotations

import re
from typing import Any

from linkedin_optimizer.from_cv import corpus_text
from linkedin_optimizer.roles import get_role

_METRIC_RE = re.compile(
    r"(\d+\s*%|\d+\s*x\b|\$\d|\d+\s*(ms|s|min|hours?|days?|weeks?|months?|years?|"
    r"k\b|m\b|million|billion|users?|requests?|nodes?|clusters?|teams?))",
    re.I,
)
_FLUFF = {
    "passionate", "synergy", "rockstar", "ninja", "guru", "driven professional",
    "hard worker", "team player", "results-oriented", "self-starter",
}


def _sanitize_suggested(text: str) -> str:
    try:
        from writing.sanitize import sanitize

        return sanitize(text or "", mode="prose")
    except Exception:
        return text or ""


def _finalize_rewrite(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("suggested"):
        result["suggested"] = _sanitize_suggested(str(result["suggested"]))
    if result.get("rationale"):
        result["rationale"] = _sanitize_suggested(str(result["rationale"]))
    return result


def _seniority_prefix(text: str, role: dict) -> str:
    t = (text or "").lower()
    for s in ("principal", "staff", "senior", "lead"):
        if s in t and s in role.get("seniority", []):
            return s.title() + " "
    return ""


def _keywords_present(corpus: str, keywords: list[str]) -> list[str]:
    h = re.sub(r"\s+", " ", (corpus or "").lower())
    found = []
    for kw in keywords:
        if kw.lower() in h:
            found.append(kw)
    return found


def _keywords_missing(corpus: str, keywords: list[str]) -> list[str]:
    have = {k.lower() for k in _keywords_present(corpus, keywords)}
    return [k for k in keywords if k.lower() not in have]


def _skill_label(kw: str) -> str:
    special = {
        "aws": "AWS", "gcp": "GCP", "sql": "SQL", "slo": "SLO", "sla": "SLA",
        "cicd": "CI/CD", "ci/cd": "CI/CD", "api": "API", "nlp": "NLP", "llm": "LLM",
        "kubernetes": "Kubernetes",
    }
    return special.get(kw.lower(), kw.title() if kw.islower() else kw)


def rewrite_headline(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    role = get_role(role_id)
    original = re.sub(r"[*_]+", "", (profile.get("headline") or "").strip())
    corpus = corpus_text(profile)
    seniority = _seniority_prefix(
        original + " " + (profile.get("about") or "") + " " + corpus, role
    )

    # Prefer the strongest evidenced title already on the profile
    title = ""
    exp_titles = [
        re.sub(r"[*_]+", "", j.get("title") or "").strip()
        for j in (profile.get("experience") or [])
        if j.get("title")
    ]
    hay = (original + " " + " ".join(exp_titles)).lower()
    for t in role["search_titles"]:
        if t.lower() in hay:
            title = t
            break
    if not title:
        for t in role["search_titles"]:
            words = [w for w in t.split() if len(w) > 4]
            if words and all(w.lower() in hay for w in words):
                title = t
                break
    if not title and exp_titles:
        title = exp_titles[0]
    if not title:
        title = role["search_titles"][0]

    present = _keywords_present(corpus, role["must_keywords"])[:4]
    stack = " · ".join(_skill_label(k) for k in present) if present else ""

    # If original headline already looks strong and short, refine rather than replace
    parts = [f"{seniority}{title}".strip()]
    if stack:
        parts.append(stack)
    suggested = " | ".join(parts)
    suggested = re.sub(r"\s+", " ", suggested).strip()
    loc = (profile.get("location") or "").strip()
    if loc and len(suggested) < 170:
        city = re.sub(r"[*_]+", "", loc.split(",")[0]).strip()
        if city and city.lower() not in suggested.lower() and "engineer" not in city.lower():
            suggested = f"{suggested} · {city}"

    missing = _keywords_missing(corpus, role["must_keywords"])[:8]
    rationale = (
        "Built from your existing titles and keywords already in your résumé/profile. "
        "No invented claims."
    )
    if missing:
        rationale += f" Still missing for search (add only if true): {', '.join(missing)}."

    return _finalize_rewrite({
        "section": "headline",
        "original": original,
        "suggested": suggested[:220],
        "rationale": rationale,
        "mode": "heuristic",
        "recommended_keywords": missing,
    })


def rewrite_about(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    role = get_role(role_id)
    original = (profile.get("about") or "").strip()
    corpus = corpus_text(profile)
    if not original:
        return _finalize_rewrite({
            "section": "about",
            "original": "",
            "suggested": "",
            "rationale": (
                "No About/summary text found. Paste your LinkedIn About or import "
                "from résumé first."
            ),
            "mode": "heuristic",
            "error": "empty_about",
            "recommended_keywords": _keywords_missing(corpus, role["must_keywords"])[:8],
        })

    cleaned = original
    for fluff in _FLUFF:
        cleaned = re.sub(re.escape(fluff), "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    present = _keywords_present(corpus, role["must_keywords"] + role["nice_keywords"])
    missing = _keywords_missing(corpus, role["must_keywords"])[:8]

    seniority = _seniority_prefix(cleaned + " " + (profile.get("headline") or ""), role)
    title_hit = ""
    for t in role["search_titles"]:
        if t.lower() in cleaned.lower() or t.lower() in (profile.get("headline") or "").lower():
            title_hit = t
            break
    if not title_hit:
        for j in profile.get("experience") or []:
            if j.get("title"):
                title_hit = j["title"]
                break

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    body = paragraphs[0] if paragraphs else cleaned
    opener_needed = bool(title_hit) and title_hit.lower() not in body[:120].lower()
    parts: list[str] = []
    if opener_needed:
        years = ""
        m = re.search(r"(\d+)\+?\s*years?", cleaned, re.I)
        if m:
            years = f" with {m.group(1)}+ years of experience"
        parts.append(
            f"{seniority.strip() or 'Experienced'} {title_hit}{years}.".replace("  ", " ").strip()
        )
        if not body.lower().startswith(title_hit.lower()[:12]):
            parts.append(body)
        else:
            parts = [body]
    else:
        parts.append(body)

    evidenced = [_skill_label(k) for k in present[:8]]
    if evidenced:
        parts.append("Core stack: " + ", ".join(evidenced) + ".")

    for extra in paragraphs[1:3]:
        if extra and extra not in parts:
            parts.append(extra)

    loc = (profile.get("location") or "").strip()
    open_to = (profile.get("open_to_work") or "").strip()
    close_bits = []
    if open_to:
        close_bits.append(open_to)
    elif title_hit:
        close_bits.append(f"Open to {title_hit} roles")
    if loc:
        close_bits.append(f"based in {loc}" if not open_to else loc)
    if close_bits:
        parts.append(". ".join(close_bits).rstrip(".") + ".")

    suggested = "\n\n".join(parts)
    rationale = (
        "Rewrote your existing About using only facts already in the text. "
        "Did not invent employers or metrics."
    )
    if missing:
        rationale += (
            f" Keywords still absent from your profile (mention only if accurate): "
            f"{', '.join(missing)}."
        )

    return _finalize_rewrite({
        "section": "about",
        "original": original,
        "suggested": suggested,
        "rationale": rationale,
        "mode": "heuristic",
        "recommended_keywords": missing,
    })


def _rewrite_bullet(bullet: str, role: dict) -> tuple[str, str | None]:
    """Return (rewritten, note). Never invents metrics."""
    b = re.sub(r"^[\u2022\-\*\u2013]\s*", "", (bullet or "").strip())
    if not b:
        return b, None
    note = None
    verbs = role.get("impact_verbs") or []
    lower = b.lower()
    if not any(lower.startswith(v) for v in verbs):
        if re.match(
            r"^(built|designed|created|implemented|developed|managed|led|owned)\b",
            lower,
        ):
            b = b[0].upper() + b[1:]
        else:
            note = "Consider leading with an impact verb (Reduced / Built / Automated…)."
    if not _METRIC_RE.search(b):
        note = (
            (note + " " if note else "")
            + "Add a real metric if you have one — do not invent numbers."
        )
    return b, note


def rewrite_experience(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    role = get_role(role_id)
    original_jobs = profile.get("experience") or []
    if not original_jobs:
        return _finalize_rewrite({
            "section": "experience",
            "original": "",
            "suggested": "",
            "suggested_structured": [],
            "rationale": (
                "No experience entries loaded. Import from résumé or paste your LinkedIn "
                "Experience section — we will not invent employers or bullets."
            ),
            "mode": "heuristic",
            "error": "empty_experience",
        })

    notes: list[str] = []
    suggested_jobs = []
    for job in original_jobs:
        bullets = []
        for b in job.get("bullets") or []:
            nb, note = _rewrite_bullet(b, role)
            if nb:
                bullets.append(nb)
            if note:
                notes.append(f"{job.get('title') or 'Role'}: {note}")
        suggested_jobs.append(
            {
                "title": job.get("title") or "",
                "company": job.get("company") or "",
                "bullets": bullets[:10],
            }
        )

    def fmt(jobs: list[dict]) -> str:
        parts = []
        for j in jobs:
            parts.append(f"{j.get('title','')}\n{j.get('company','')}".strip())
            for b in j.get("bullets") or []:
                parts.append(f"• {b}")
            parts.append("")
        return "\n".join(parts).strip()

    rationale = (
        "Kept your real employers and bullets. Light edits only — no fabricated metrics."
    )
    if notes:
        rationale += " Notes: " + " ".join(notes[:6])

    return _finalize_rewrite({
        "section": "experience",
        "original": fmt(original_jobs),
        "suggested": fmt(suggested_jobs),
        "suggested_structured": suggested_jobs,
        "rationale": rationale,
        "mode": "heuristic",
        "notes": notes,
    })


def rewrite_skills(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    role = get_role(role_id)
    original = list(profile.get("skills") or [])
    corpus = corpus_text(profile)
    evidenced = _keywords_present(corpus, role["must_keywords"] + role["nice_keywords"])
    recommended = _keywords_missing(corpus, role["must_keywords"])[:10]

    have = {s.lower(): s for s in original}
    ordered: list[str] = []
    for kw in evidenced:
        label = _skill_label(kw)
        key = label.lower()
        if key in have:
            ordered.append(have[key])
        elif kw.lower() in have:
            ordered.append(have[kw.lower()])
        else:
            ordered.append(label)
    for s in original:
        if s.lower() not in {x.lower() for x in ordered}:
            ordered.append(s)
    suggested = ordered[:20]

    return _finalize_rewrite({
        "section": "skills",
        "original": ", ".join(original),
        "suggested": ", ".join(suggested),
        "suggested_list": suggested,
        "rationale": (
            "Ordered skills already evidenced in your résumé/profile. "
            "Did not add unproven keywords as facts."
            + (
                f" Consider adding (only if accurate): {', '.join(recommended)}."
                if recommended
                else ""
            )
        ),
        "mode": "heuristic",
        "recommended_keywords": recommended,
    })


def rewrite_open_to_work(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    role = get_role(role_id)
    original = (profile.get("open_to_work") or "").strip()
    loc = (profile.get("location") or "").strip() or "(add your locations)"
    corpus = corpus_text(profile)
    titles = []
    for t in role["search_titles"]:
        if t.lower() in corpus.lower() or any(
            t.lower() in (j.get("title") or "").lower()
            for j in profile.get("experience") or []
        ):
            titles.append(t)
    if not titles:
        titles = role["search_titles"][:3]
    suggested = (
        f"Open to: {', '.join(titles[:4])}\n"
        f"Locations: {loc}\n"
        f"Job types: Full-time"
    )
    return _finalize_rewrite({
        "section": "open_to_work",
        "original": original,
        "suggested": suggested,
        "rationale": "Uses titles already on your profile/résumé and your stated location.",
        "mode": "heuristic",
    })


def rewrite_featured(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    original = (profile.get("featured") or "").strip()
    if original:
        suggested = (
            "Featured (from your projects — add links on LinkedIn):\n\n" + original[:1200]
        )
        rationale = "Uses your existing Projects text. Add public links where possible."
    else:
        suggested = (
            "No projects/featured content found in your imported profile.\n"
            "Add 1–3 real artifacts on LinkedIn Featured: a case study, talk, "
            "repo, or dashboard screenshot (redact secrets). Do not invent items."
        )
        rationale = "Refused to invent Featured items — paste real project links."
    return _finalize_rewrite({
        "section": "featured",
        "original": original,
        "suggested": suggested,
        "rationale": rationale,
        "mode": "heuristic",
    })


def rewrite_section(section: str, profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    section = (section or "").strip().lower()
    dispatch = {
        "headline": rewrite_headline,
        "about": rewrite_about,
        "experience": rewrite_experience,
        "skills": rewrite_skills,
        "open_to_work": rewrite_open_to_work,
        "featured": rewrite_featured,
    }
    fn = dispatch.get(section)
    if not fn:
        return {
            "section": section,
            "original": "",
            "suggested": "",
            "rationale": f"Unknown section: {section}",
            "mode": "heuristic",
            "error": "unknown_section",
        }
    return fn(profile, role_id)


def maybe_llm_polish(
    draft: str, section: str, role_id: str, evidence: str = ""
) -> tuple[str, str]:
    """Optional polish. Must not invent facts. Falls back to draft."""
    try:
        from llm import get_llm
        from writing.sanitize import sanitize
        from writing.self_check import invents_unsupported_tokens, self_check
        from writing.style import with_style

        llm = get_llm()
        if not llm or not llm.is_available():
            return draft, "heuristic"
        role = get_role(role_id)
        system = with_style(
            "You improve LinkedIn profile copy. HARD RULES: keep every fact grounded in "
            "the evidence; do not invent employers, metrics, skills, or projects; do not "
            "add keywords that are not supported by evidence; stay human and credible. "
            "Return only the revised text."
        )
        prompt = (
            f"Target role family: {role['label']}\n"
            f"Section: {section}\n"
            f"Evidence (only source of truth):\n{evidence[:4000]}\n\n"
            f"Draft to polish:\n{draft}\n"
        )
        out = (llm.complete(prompt, system=system, max_tokens=900) or "").strip()
        if len(out) < 20:
            return draft, "heuristic"
        cleaned = sanitize(out, mode="prose")
        invented = invents_unsupported_tokens(cleaned, evidence + "\n" + (draft or ""))
        check = self_check(cleaned)
        if invented or (not check["ok"] and len(check["hits"]) >= 3):
            return draft, "heuristic"
        return cleaned, "llm"
    except Exception:
        return draft, "heuristic"
