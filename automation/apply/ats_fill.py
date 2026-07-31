"""
Playwright apply assist — pre-fill Greenhouse / Lever / Ashby forms.

ETHICAL RULE: Never clicks Submit / Apply. User confirms in browser.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from config import CV_MD_PATH
from scrapers.ats_url_resolver import parse_ats_url

logger = logging.getLogger(__name__)

_SUBMIT_PATTERNS = re.compile(
    r"submit|apply now|send application|complete application",
    re.I,
)

_APPLY_NAV_PATTERNS = re.compile(
    r"apply for this job|start application|apply to this job|view application",
    re.I,
)

_FIELD_CANDIDATES: list[tuple[str, str]] = [
    ("input[name*='first' i], input[id*='first' i]", "first_name"),
    ("input[name*='last' i], input[id*='last' i]", "last_name"),
    ("input[type='email'], input[name*='email' i]", "email"),
    ("input[type='tel'], input[name*='phone' i]", "phone"),
    ("input[name*='linkedin' i], input[id*='linkedin' i]", "linkedin"),
    ("input[name*='github' i], input[id*='github' i]", "github"),
    ("input[name*='website' i], input[id*='website' i], input[name*='portfolio' i]", "website"),
    ("input[name*='location' i], input[id*='location' i]", "location"),
]


def _profile_fields() -> dict[str, str]:
    # Always re-read so a Profile save is live without an API restart.
    try:
        from config import reload_discovery_config

        reload_discovery_config()
    except Exception:
        pass
    from config import APPLICATION as app
    from config import CANDIDATE as cand

    name = (cand.get("name") or "").strip()
    parts = name.split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    years = cand.get("years_exp") or 0
    preferred = str(app.get("preferred_name") or "").strip()
    return {
        "first_name": first,
        "last_name": last,
        "full_name": name,
        "preferred_name": preferred or first,
        "email": str(cand.get("email") or ""),
        "phone": str(cand.get("phone") or ""),
        "linkedin": str(cand.get("linkedin") or ""),
        "github": str(cand.get("github") or ""),
        "location": str(cand.get("location") or ""),
        # Application answers (ATS custom questions, matched by visible label)
        "website": str(app.get("website") or ""),
        "years_exp": str(years) if years else "",
        "notice_period": str(app.get("notice_period") or ""),
        "current_ctc": str(app.get("current_ctc") or ""),
        "expected_ctc": str(app.get("expected_ctc") or ""),
        "how_heard": str(app.get("how_heard") or ""),
        "work_authorization": str(app.get("work_authorization") or ""),
        "cover_letter_snippet": str(app.get("cover_letter_snippet") or ""),
        "willing_to_relocate": str(app.get("willing_to_relocate") or ""),
    }


# Custom ATS questions are labelled by visible text, not a semantic name/id.
# Match the field by its <label> and fill the associated input/textarea/select.
_LABEL_FIELDS: list[tuple[str, str]] = [
    (r"preferred name|goes by|nickname", "preferred_name"),
    (r"linkedin", "linkedin"),
    (r"\bgithub\b", "github"),
    (r"website|portfolio|personal site|personal url", "website"),
    (r"current location|where are you|^location$|your location|city", "location"),
    (r"years of experience|how many years|total experience", "years_exp"),
    (r"notice period|availability to join|joining time|when can you (join|start)", "notice_period"),
    (r"current ctc|current salary|current compensation|present ctc|current pay", "current_ctc"),
    (r"expected ctc|expected salary|expected compensation|desired salary|salary expectation", "expected_ctc"),
    (r"how did you hear|how do you know|source", "how_heard"),
    (
        r"work authorization|authorized to work|legally authorized|require sponsorship|"
        r"visa sponsorship|need sponsorship|eligible to work",
        "work_authorization",
    ),
    (
        r"willing to relocate|open to relocate|relocation",
        "willing_to_relocate",
    ),
    (
        r"cover letter|why (do you |are you )?(want|interested)|tell us about yourself|"
        r"additional information|anything else|motivation",
        "cover_letter_snippet",
    ),
]


def _select_native(loc, value: str) -> bool:
    """Best-effort select on a native <select>: match option text by substring."""
    target = value.strip().lower()
    try:
        options = loc.locator("option")
        for i in range(options.count()):
            txt = (options.nth(i).inner_text(timeout=300) or "").strip()
            low = txt.lower()
            if not low or low in ("select...", "select"):
                continue
            if target and (target in low or low in target):
                loc.select_option(index=i)
                return True
    except Exception:
        pass
    try:
        loc.select_option(label=value)
        return True
    except Exception:
        return False


def _fill_by_labels(page, profile: dict[str, str], report: dict[str, Any]) -> None:
    """Fill ATS custom questions located by visible label text."""
    for pattern, key in _LABEL_FIELDS:
        value = str(profile.get(key) or "").strip()
        if not value or key in report.get("filled", []):
            continue
        try:
            field = page.get_by_label(re.compile(pattern, re.I)).first
            if field.count() == 0 or not field.is_visible(timeout=600):
                continue
            tag = str(field.evaluate("el => el.tagName") or "").lower()
            if tag == "select":
                if _select_native(field, value):
                    report.setdefault("filled", []).append(key)
            else:
                field.fill(value, timeout=2500)
                report.setdefault("filled", []).append(key)
        except Exception as e:  # label not present / not fillable — skip
            logger.debug("label fill %s: %s", key, e)


def _ats_label(url: str) -> str:
    parsed = parse_ats_url(url)
    if parsed:
        return parsed.ats_type
    host = urlparse(url).netloc.lower()
    if "greenhouse" in host:
        return "greenhouse"
    if "lever" in host:
        return "lever"
    if "ashby" in host:
        return "ashby"
    return "unknown"


def _reveal_application_form(page, ats: str) -> None:
    """Scroll / navigate to embedded ATS application (never final submit)."""
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
    except Exception:
        pass

    if ats != "greenhouse":
        return

    for sel in ("#application", "a[href*='#app']", "[id*='application']"):
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.scroll_into_view_if_needed(timeout=3000)
                page.wait_for_timeout(400)
                break
        except Exception:
            continue

    try:
        links = page.locator("a")
        for i in range(min(links.count(), 40)):
            text = (links.nth(i).inner_text(timeout=300) or "").strip()
            if _APPLY_NAV_PATTERNS.search(text):
                links.nth(i).click(timeout=3000)
                page.wait_for_timeout(1200)
                break
    except Exception:
        pass


def _fill_known_fields(
    page,
    profile: dict[str, str],
    report: dict[str, Any],
    *,
    selectors: list[tuple[str, str]] | None = None,
) -> None:
    field_list = selectors or _FIELD_CANDIDATES
    for selector, key in field_list:
        value = profile.get(key, "")
        if not value:
            continue
        try:
            loc = page.locator(selector).first
            if loc.count() == 0:
                if key not in report["unfilled"]:
                    report["unfilled"].append(key)
                continue
            if loc.is_visible(timeout=800):
                loc.fill(value, timeout=3000)
                if key not in report["filled"]:
                    report["filled"].append(key)
        except Exception as e:
            logger.debug("Fill %s: %s", key, e)
            if key not in report["unfilled"]:
                report["unfilled"].append(key)

    if "first_name" not in report["filled"] and "full_name" not in report["filled"] and profile.get("full_name"):
        try:
            loc = page.locator("input[name*='name' i]").first
            if loc.count() and loc.is_visible(timeout=800):
                loc.fill(profile["full_name"], timeout=3000)
                report["filled"].append("full_name")
        except Exception:
            pass


def _ensure_proactor_loop() -> None:
    """Playwright's driver subprocess needs the Proactor event loop on Windows; a
    server (uvicorn) can leave a Selector policy active, which makes it crash with
    NotImplementedError. Safe to call repeatedly."""
    import os

    if os.name == "nt":
        import asyncio

        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass


def playwright_ready() -> tuple[bool, str]:
    """Return (ok, message) — package import + chromium binary on disk."""
    _ensure_proactor_loop()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "Playwright not installed. Run: pip3 install -r automation/requirements.txt"

    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
        if path and __import__("os").path.exists(path):
            return True, "ok"
    except Exception as e:
        return False, f"Playwright chromium not installed: {e}"
    return False, "Playwright chromium not installed. Open Connections → Install Playwright."


def fill_application_form(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45_000,
    company: str = "",
    cv_pdf_path: str | None = None,
) -> dict[str, Any]:
    """
    Open job URL and fill known fields from profile.yml.
    Returns a report dict; submit_blocked is always True.
    """
    from apply.ats_strategies import fill_ats_fields, resolve_resume_pdf, upload_resume

    profile = _profile_fields()
    report: dict[str, Any] = {
        "url": url,
        "ats": _ats_label(url),
        "filled": [],
        "unfilled": [],
        "errors": [],
        "submit_detected": False,
        "submit_blocked": True,
        "ready_for_user_review": False,
        "cv_path": CV_MD_PATH if __import__("os").path.exists(CV_MD_PATH) else None,
    }

    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("file:")):
        report["errors"].append("Invalid URL")
        return report

    ok, msg = playwright_ready()
    if not ok:
        report["errors"].append(msg)
        return report

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        report["errors"].append(
            "Playwright not installed. Open Connections → Install Playwright."
        )
        return report

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            ats = report["ats"]
            _reveal_application_form(page, ats)
            fill_ats_fields(page, ats, profile, report)
            # Custom ATS questions (CTC, notice period, website, …) are matched
            # by visible label, not name/id — so run this on every page.
            _fill_by_labels(page, profile, report)

            if not report["filled"]:
                for frame in page.frames:
                    if frame == page.main_frame:
                        continue
                    try:
                        fill_ats_fields(frame, ats, profile, report)
                        _fill_by_labels(frame, profile, report)
                        if report["filled"]:
                            break
                    except Exception:
                        continue

            pdf_path = cv_pdf_path or resolve_resume_pdf(company)
            if pdf_path:
                upload_resume(page, pdf_path, report)
                if not report.get("resume_path"):
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        if upload_resume(frame, pdf_path, report):
                            break

            buttons = page.locator("button, input[type='submit']")
            for i in range(min(buttons.count(), 20)):
                try:
                    text = (buttons.nth(i).inner_text(timeout=500) or "").strip()
                    if _SUBMIT_PATTERNS.search(text):
                        report["submit_detected"] = True
                        break
                except Exception:
                    continue

            report["ready_for_user_review"] = len(report["filled"]) > 0
            if not headless:
                report["message"] = "Browser open — review fields and click Submit yourself."
                # Keep the window open so the user can review (API headed assist).
                page.wait_for_timeout(120_000)
            browser.close()
    except Exception as e:
        logger.warning("Apply assist failed: %s", e)
        report["errors"].append(str(e))

    return report


def apply_assist_for_job(job_id: str, *, headless: bool = True) -> dict[str, Any]:
    """Load job from SQLite, verify approved pipeline, run fill (no submit)."""
    from store.status import StatusError, get_pipeline_row, validate_job_id
    from store import db as store

    jid = validate_job_id(job_id)
    pipe = get_pipeline_row(jid)
    if not pipe or pipe["status"] not in ("approved", "evaluated"):
        raise StatusError(
            f"Apply assist requires pipeline status approved or evaluated (got {pipe['status'] if pipe else 'none'})"
        )

    with store.db() as conn:
        row = conn.execute(
            "SELECT url, company, title, source FROM jobs WHERE id = ?", (jid,)
        ).fetchone()
    if not row or not row["url"]:
        raise ValueError(f"Job {jid} has no URL")

    from apply.channels import LINK_ONLY_MESSAGE, NotFillableError, is_link_only

    if is_link_only(row["url"], str(row["source"] or "")):
        raise NotFillableError(LINK_ONLY_MESSAGE)

    from apply.ats_strategies import resolve_resume_pdf
    from processors.generate_cv import generate_cv_for_job

    company = str(row["company"] or "")
    job_payload = {"url": row["url"], "company": company, "title": row["title"] or "", "jd_snippet": ""}

    # Which résumé to attach. In "generated" mode, render a fresh tailored CV for THIS
    # exact job and attach that precise file — deterministic, and it always matches the
    # template the user previews (no "newest PDF in the folder" guesswork).
    try:
        from store.settings import get_cv_settings

        resume_source = get_cv_settings().get("resume_source", "uploaded")
    except Exception:
        resume_source = "uploaded"

    cv_pdf = None
    if resume_source == "generated":
        try:
            gen = generate_cv_for_job(job_payload)
            if gen.get("success"):
                cv_pdf = gen.get("path")
        except Exception as exc:
            logger.debug("Tailored CV generation failed, falling back: %s", exc)
    if not cv_pdf:
        cv_pdf = resolve_resume_pdf(company)  # uploaded original (or last tailored)
    if not cv_pdf:
        try:
            gen = generate_cv_for_job(job_payload)
            if gen.get("success"):
                cv_pdf = gen.get("path")
        except Exception as exc:
            logger.debug("CV PDF generation skipped: %s", exc)

    report = fill_application_form(
        row["url"],
        headless=headless,
        company=company,
        cv_pdf_path=cv_pdf,
    )
    report["job_id"] = jid
    report["company"] = row["company"]
    report["title"] = row["title"]
    store.audit(
        "apply_assist",
        "job",
        jid,
        {
            "filled": report.get("filled", []),
            "unfilled": report.get("unfilled", []),
            "resume": report.get("resume_path", ""),
            "submit_detected": report.get("submit_detected", False),
        },
    )
    return report
