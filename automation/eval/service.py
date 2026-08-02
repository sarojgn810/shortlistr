"""Structured evaluation service with JSON schema output."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from config import CV_MD_PATH, LLM_CONFIG, MIN_FIT_SCORE
from llm import get_llm
from models.job import JobRecord, job_id_from_url
from store import db as store
from store.enrich import _extract_title_from_jd, company_title_from_url, is_boilerplate_text, is_placeholder, prettify_company

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
SCHEMA_VERSION = "v1"


@dataclass
class EvalResult:
    score: float
    legitimacy: str
    company: str
    role: str
    blocks: dict[str, str]
    raw: dict[str, Any]
    eval_mode: str = "llm"  # llm | template
    # The hard requirements the model checked the CV against, and whether each
    # was met. This is what the score is derived from, so keeping it is what
    # makes a score explainable — and "you miss 2 of 7, these two" is the part
    # the user can actually act on in a cover letter.
    must_haves: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        blocks = self.blocks or {}
        summary = ""
        for key in ("B", "C", "D"):
            if blocks.get(key) and not is_boilerplate_text(str(blocks[key])):
                summary = str(blocks[key]).split("\n")[0].strip()[:500]
                break
        template_only = self.eval_mode == "template"
        return {
            "schema_version": SCHEMA_VERSION,
            "score": self.score,
            "legitimacy": self.legitimacy,
            "company": self.company,
            "role": self.role,
            "summary": summary,
            "blocks": blocks,
            "eval_mode": self.eval_mode,
            "template_only": template_only,
            "must_haves": self.must_haves or [],
        }


def _load_prompt(name: str = "evaluate_v1.txt") -> str:
    path = os.path.join(PROMPTS_DIR, name)
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()
    return (
        "Evaluate this job for the candidate. Return JSON with keys: "
        "score (0-5 float), legitimacy (verified|likely|uncertain|suspicious), "
        "company, role, blocks (object with keys A,B,C,D,E,F,G as strings)."
    )


def _is_timeout(exc: Exception) -> bool:
    """True when the provider ran out of time rather than answering badly."""
    try:
        import requests

        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True
    except Exception:
        pass
    text = f"{type(exc).__name__} {exc}".lower()
    return "timeout" in text or "timed out" in text


def _parse_json_response(text: str) -> dict:
    """The JSON object out of a model reply, tolerating what models wrap it in.

    Reasoning models (qwen3, deepseek-r1) put a <think> block before the answer,
    and any model may fence the object in ```json. A greedy match from the first
    brace to the last then swallows braces belonging to the reasoning rather
    than the answer, so those wrappers come off first.
    """
    text = re.sub(r"<think>.*?</think>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"^\s*```(?:json)?|```\s*$", " ", text.strip(), flags=re.M)
    text = text.strip()

    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            # Trailing prose after the object: retry from the first brace to
            # each closing brace, longest first.
            start = text.index("{")
            for end in range(len(text), start, -1):
                if text[end - 1] != "}":
                    continue
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    continue
    preview = (text or "").strip()
    if len(preview) > 220:
        preview = preview[:217] + "…"
    raise ValueError(
        "No JSON object in LLM response "
        f"(got {len(text or '')} chars: {preview!r})"
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_must_haves(value: Any) -> list[dict[str, Any]]:
    """Keep only well-formed requirement rows; a malformed one is not a gap."""
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value[:25]:
        if not isinstance(item, dict):
            continue
        req = str(item.get("req") or "").strip()
        if not req:
            continue
        out.append({
            "req": req[:300],
            "met": bool(item.get("met")),
            "evidence": str(item.get("evidence") or "").strip()[:300],
        })
    return out


def _has_usable_eval(data: dict) -> bool:
    """True if an LLM response carries a real evaluation.

    Guards against a parseable-but-empty payload (no blocks, no score) being
    presented as a genuine LLM eval — that would slip past the template-mode
    badge and show a 0.0 score as if it were full A-G analysis.
    """
    blocks = data.get("blocks") if isinstance(data, dict) else None
    has_block = isinstance(blocks, dict) and any(str(v).strip() for v in blocks.values())
    return has_block or _safe_float(data.get("score")) > 0


# Known applicant-tracking hosts — a posting on one of these is usually real,
# but we never claim "verified" without a live check.
_ATS_HOST_HINTS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workday.com",
    "jobs.ashbyhq.com",
    "boards.greenhouse.io",
    "jobs.lever.co",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "bamboohr.com",
    "taleo.net",
    "successfactors.com",
    "recruitee.com",
    "personio.de",
    "teamtailor.com",
)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9][a-z0-9+.#-]{1,}", (text or "").lower()) if len(t) >= 2}


def _cv_skill_tokens(cv_text: str) -> list[str]:
    """Skills from the CV competencies section, falling back to whole-CV tokens."""
    try:
        from cv.parser import parse_cv_markdown

        sections = parse_cv_markdown(cv_text or "")
        blob = (sections.skills or "").strip()
        if blob:
            parts = re.split(r"[,;/\n•·|\-]+", blob)
            out: list[str] = []
            for p in parts:
                s = p.strip().lower()
                if 2 <= len(s) <= 48 and s not in out:
                    out.append(s)
            if out:
                return out[:50]
    except Exception:
        pass
    # Fallback: frequent tech-ish tokens from the whole CV
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "your", "have",
        "been", "were", "will", "into", "over", "under", "years", "year",
        "experience", "professional", "summary", "education", "present",
    }
    toks = [t for t in _tokenize(cv_text) if t not in stop and not t.isdigit()]
    return toks[:40]


def _jd_requirement_bullets(jd_text: str, *, limit: int = 8) -> list[str]:
    bullets: list[str] = []
    for raw in (jd_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^[-*•]\s+(.+)$", line)
        if m:
            bullets.append(m.group(1).strip()[:200])
        elif re.match(r"^\d+[.)]\s+\S", line):
            bullets.append(re.sub(r"^\d+[.)]\s+", "", line)[:200])
        if len(bullets) >= limit:
            break
    return bullets


def _legitimacy_from_url(url: str) -> str:
    host = ""
    try:
        from urllib.parse import urlparse

        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        return "uncertain"
    if any(h in host for h in _ATS_HOST_HINTS):
        return "likely"
    # Company careers subdomain is a mild positive signal
    if host.startswith("jobs.") or host.startswith("careers.") or ".careers." in host:
        return "likely"
    return "uncertain"


def _heuristic_eval(
    jd_text: str,
    *,
    company: str = "",
    role: str = "",
    url: str = "",
    cv_text: str = "",
) -> dict:
    """Rule-based eval when no LLM is available — CV/JD overlap, not a fixed stack."""
    if is_placeholder(company) and url:
        c, _ = company_title_from_url(url)
        company = c or company
    company = prettify_company(company) or company or "Company"

    if is_placeholder(role):
        role = _extract_title_from_jd(jd_text) or role
    if is_placeholder(role):
        role = "Role (resolve from posting)"

    jd_lower = (jd_text or "").lower()
    jd_tokens = _tokenize(jd_text)
    cv = cv_text
    if not cv and os.path.exists(CV_MD_PATH):
        try:
            cv = open(CV_MD_PATH, encoding="utf-8").read()[:8000]
        except OSError:
            cv = ""

    skills = _cv_skill_tokens(cv)
    matched: list[str] = []
    for skill in skills:
        # Phrase match first, then token overlap for multi-word skills
        if skill in jd_lower or all(tok in jd_tokens for tok in skill.split() if len(tok) > 1):
            matched.append(skill)
        if len(matched) >= 12:
            break

    # Title family overlap from the live profile
    title_hit = False
    try:
        from processors.job_filter import core_titles

        for t in core_titles():
            if t and t in jd_lower:
                title_hit = True
                break
            if t and role and t in role.lower():
                title_hit = True
                break
    except Exception:
        pass

    score = 2.6
    if title_hit:
        score += 0.6
    score += min(1.4, 0.15 * len(matched))
    if "remote" in jd_lower or "work from home" in jd_lower:
        score += 0.1
    # Soft penalty when the JD has substance but nothing overlaps the CV
    if len(jd_tokens) > 40 and not matched and not title_hit:
        score -= 0.4
    score = max(1.5, min(4.6, round(score, 1)))

    reqs = _jd_requirement_bullets(jd_text)
    snippet = (jd_text or "").strip()[:500]
    fit_line = (
        f"Overlapping skills: {', '.join(matched[:8])}."
        if matched
        else "Limited skill overlap with your résumé — review the JD carefully."
    )
    if title_hit:
        fit_line = "Title matches your targets. " + fit_line

    block_c = (
        "Requirements called out in the posting:\n"
        + "\n".join(f"• {b}" for b in reqs[:6])
        if reqs
        else "No clear bullet list in the JD text — skim the posting for must-haves."
    )
    block_d = (
        f"Résumé skills that appear in the JD: {', '.join(matched[:8])}."
        if matched
        else "No strong skill matches found in the JD excerpt. Consider skipping or rewriting your résumé emphasis."
    )
    block_e = (
        "Gaps to check: anything the JD lists that is missing from the skills above. "
        "Prefer roles where most must-haves already show on your résumé."
    )
    block_f = (
        "Suggested next step: approve if the score feels right, then open Prep for a cover letter "
        "and interview guide. Prefill the form only after you have reviewed the materials."
    )

    return {
        "score": score,
        "legitimacy": _legitimacy_from_url(url),
        "company": company,
        "role": role,
        "blocks": {
            "A": f"{role} at {company}",
            "B": fit_line + (f"\n\nJD excerpt:\n{snippet}" if snippet else ""),
            "C": block_c,
            "D": block_d,
            "E": block_e,
            "F": block_f,
            "G": (
                "Basic scoring (no AI key) — overlap of your résumé with the JD. "
                "Set up an AI helper on Connections for full A–G judgment."
            ),
        },
    }


def evaluate_job_text(
    jd_text: str,
    *,
    url: str = "",
    company: str = "",
    role: str = "",
    job_id: str = "",
    cv_text: str | None = None,
) -> EvalResult:
    # cv_text lets callers evaluate against a CV other than the single-user
    # cv.md (e.g. sprint-tailor's per-candidate CVs). Default path unchanged.
    if cv_text is not None:
        cv = cv_text[:6000]
    else:
        cv = ""
        if os.path.exists(CV_MD_PATH):
            cv = open(CV_MD_PATH, encoding="utf-8").read()[:6000]

    system = _load_prompt()
    try:
        from writing.style import with_style

        system = with_style(system)
    except Exception:
        pass
    try:
        from outcomes.adapt import learnings_prompt_block

        signals = learnings_prompt_block()
    except Exception:
        signals = ""
    user = (
        f"URL: {url}\nCompany: {company}\nRole: {role}\n\n"
        f"--- CV ---\n{cv}\n\n--- JD ---\n{jd_text[:8000]}{signals}"
    )

    provider = get_llm()
    eval_mode = "llm"
    triage_meta: dict[str, Any] | None = None
    # Optional cheap gate — skip full A–G when clearly off-target.
    try:
        from eval.triage import run_triage, triage_enabled

        if triage_enabled() and provider and provider.is_available():
            triage_meta = run_triage(
                jd_text=jd_text,
                cv_text=cv,
                company=company,
                role=role,
                url=url,
            )
            if triage_meta and triage_meta.get("proceed") is False:
                eval_mode = "triage_skip"
                guess = _safe_float(triage_meta.get("score_guess"), 2.0)
                reason = str(triage_meta.get("reason") or "Triage flagged a weak fit.")
                data = _heuristic_eval(
                    jd_text, company=company, role=role, url=url, cv_text=cv
                )
                data["score"] = min(guess, 3.0)
                data.setdefault("blocks", {})
                data["blocks"]["G"] = (
                    f"Two-stage triage skipped full eval: {reason} "
                    "(turn off in Settings → Evaluation if you want full A–G every time)."
                )
                # Fall through to sanitize + persist below
                provider = None  # skip full LLM path
    except Exception:
        triage_meta = None

    if provider and provider.is_available():
        data = None
        last_exc: Exception | None = None
        for _attempt in range(2):  # one retry: covers a transient network error or bad JSON
            try:
                # json_mode is advisory: providers that support a JSON
                # grammar (Ollama) stop small models answering in prose, and
                # the rest ignore the keyword. Older third-party providers may
                # not accept it at all, hence the fallback call.
                try:
                    raw_text = provider.complete(
                        user, system=system, max_tokens=4096, json_mode=True
                    )
                except TypeError:
                    raw_text = provider.complete(user, system=system, max_tokens=4096)
                data = _parse_json_response(raw_text)
                if not _has_usable_eval(data):
                    raise ValueError("LLM returned an empty or malformed evaluation")
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                # A retry is for bad JSON or a dropped connection. Retrying a
                # timeout just waits the same amount again — with Ollama's 120s
                # ceiling that is a 240s request, and the dev proxy in front of
                # the API hangs up long before, which surfaces as
                # "socket hang up / ECONNRESET" and a 500 with no body.
                if _is_timeout(exc):
                    break
        if last_exc is not None:
            import logging

            logging.getLogger(__name__).warning(
                "LLM eval failed after retry, using heuristic: %s", last_exc
            )
            eval_mode = "template"
            data = _heuristic_eval(jd_text, company=company, role=role, url=url, cv_text=cv)
            data.setdefault("blocks", {})
            data["blocks"]["G"] = (
                f"AI helper unavailable ({last_exc}). Showing basic résumé/JD overlap — "
                "check Connections, then re-run."
            )
    elif eval_mode != "triage_skip":
        eval_mode = "template"
        data = _heuristic_eval(jd_text, company=company, role=role, url=url, cv_text=cv)

    # Sanitize block prose only — leave score / legitimacy / company / role intact.
    try:
        from writing.sanitize import sanitize_blocks

        if isinstance(data.get("blocks"), dict):
            data["blocks"] = sanitize_blocks(data["blocks"], mode="prose")
    except Exception:
        pass

    raw_out = {**data, "eval_mode": eval_mode}
    if triage_meta:
        raw_out["triage"] = triage_meta
    result = EvalResult(
        score=_safe_float(data.get("score")),
        must_haves=_clean_must_haves(data.get("must_haves")),
        legitimacy=str(data.get("legitimacy", "uncertain")),
        company=str(data.get("company", company)),
        role=str(data.get("role", role)),
        blocks=dict(data.get("blocks") or {}),
        raw=raw_out,
        eval_mode=eval_mode,
    )

    jid = job_id or (job_id_from_url(url) if url else "")
    if url:
        store.upsert_job(
            JobRecord(
                url=url,
                source="eval",
                company=result.company,
                title=result.role,
                jd_text=jd_text[:8000],
                job_id=jid,
            )
        )
    if jid:
        with store.db() as conn:
            conn.execute(
                """
                INSERT INTO eval_results (job_id, schema_version, score, legitimacy, result_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    jid,
                    SCHEMA_VERSION,
                    result.score,
                    result.legitimacy,
                    json.dumps(result.to_dict()),
                ),
            )
        store.audit("job_evaluated", "job", jid, {"score": result.score, "url": url})
        from store.status import mark_evaluated
        try:
            mark_evaluated(
                jid,
                company=result.company,
                role=result.role,
                score=result.score,
                actor="eval_service",
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("mark_evaluated(%s) failed: %s", jid, exc)

    return result


def recommend_apply(score: float, min_score: float | None = None) -> bool:
    threshold = (min_score or MIN_FIT_SCORE) / 20.0  # map 0-100 fit to 0-5 eval scale approx
    return score >= max(threshold, 4.0)
