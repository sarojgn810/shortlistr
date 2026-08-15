"""
Playwright apply assist — pre-fill Greenhouse / Lever / Ashby forms.

RULE: Submit is never clicked unless the caller explicitly asks for it, and the
only caller that does is `apply/submit.py`, which first requires the job to be
approved by a human and to have a tailored CV and cover letter. Filling stops
short of sending by default; `submit=True` is the deliberate exception, not a
convenience.
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
    r"apply for this job|apply to this job|start application|view application"
    r"|apply now|apply online|i'?m interested|^\s*apply\s*$",
    re.I,
)

# Inputs that only an application form has. A job listing page has a search box,
# so a bare text input proves nothing — an email or file field does.
_FORM_MARKERS = (
    "input[type='email']", "input[type='file']",
    "input[name*='email' i]", "input[id*='email' i]",
    "input[name*='resume' i]", "input[name*='first' i]",
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


def _cv_text() -> str:
    """The CV, for grounding experience answers. Empty means we answer fewer questions."""
    try:
        with open(CV_MD_PATH, encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return ""


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
        # Standard screening answers. Blank is a valid setting and means "leave
        # it for me" — apply/screening.py never guesses these.
        "country_of_residence": str(app.get("country_of_residence") or ""),
        "on_call_ok": str(app.get("on_call_ok") or ""),
        "worked_here_before": str(app.get("worked_here_before") or ""),
        "start_date": str(app.get("start_date") or ""),
        "remote_preference": str(app.get("remote_preference") or ""),
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


# react-select renders a text input with role="combobox" and no native <select>.
# The visible text is not the answer — the committed value lives on a wrapper —
# so .fill() types something and answers nothing.
#
# Scoping matters more than it looks. A bare "[role='option']" matched 246
# elements on a Greenhouse form: the phone field's country-code picker is a
# separate always-present widget, so the search walked a list of countries
# looking for "Yes". React-select's own class is the reliable handle, and the
# combobox names its menu through aria-controls / aria-owns when it has one.
_COMBOBOX_OPTION_SELECTOR = "[class*='select__option'], [class*='menu'] [role='option']"


def _is_combobox(field) -> bool:
    """True for a react-select style control masquerading as a text input."""
    try:
        if (field.get_attribute("role") or "").lower() == "combobox":
            return True
        if (field.get_attribute("aria-haspopup") or "").lower() in ("true", "listbox"):
            return True
        return "select__input" in (field.get_attribute("class") or "")
    except Exception:
        return False


def _combobox_options(page, field):
    """The options belonging to *this* combobox, not every listbox on the page.

    Prefer the menu the control names via aria-controls/aria-owns; fall back to
    react-select's own option class. Both beat a page-wide "[role='option']",
    which on a Greenhouse form also matches the phone widget's 246 countries.
    """
    for attr in ("aria-controls", "aria-owns"):
        try:
            menu_id = field.get_attribute(attr)
        except Exception:
            menu_id = None
        if menu_id:
            scoped = page.locator(f"#{menu_id} [role='option'], #{menu_id} li")
            try:
                if scoped.count():
                    return scoped
            except Exception:
                pass
    return page.locator(_COMBOBOX_OPTION_SELECTOR)


def _fill_combobox(page, field, value: str) -> bool:
    """Open the menu, pick an option matching ``value``, and confirm it stuck.

    Returns False rather than settling for a near-miss: an unanswered question
    leaves the user a field to fill, while the wrong option puts a false answer
    on their application.
    """
    target = (value or "").strip().lower()
    if not target:
        return False

    try:
        field.click(timeout=2000)
        page.wait_for_timeout(250)
        # Typing narrows the menu on long lists (countries, for instance).
        try:
            field.type(value, delay=15, timeout=2000)
            page.wait_for_timeout(350)
        except Exception:
            pass

        options = _combobox_options(page, field)
        for i in range(min(options.count(), 60)):
            option = options.nth(i)
            try:
                text = (option.inner_text(timeout=300) or "").strip()
            except Exception:
                continue
            low = text.lower()
            if not low:
                continue
            # Exact first, then "Yes, I am" for "Yes". Never the reverse: "No"
            # must not match "Not applicable".
            if low == target or low.startswith(target + ",") or low.startswith(target + " "):
                option.click(timeout=2000)
                page.wait_for_timeout(200)
                return True
    except Exception as e:
        logger.debug("combobox fill failed for %r: %s", value, e)

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
            if _set_field_value(page, field, value):
                _mark_filled(report, key)
        except Exception as e:  # label not present / not fillable — skip
            logger.debug("label fill %s: %s", key, e)


def _set_field_value(page, field, value: str) -> bool:
    """Put ``value`` into whatever kind of control this is. False if it didn't take."""
    try:
        tag = str(field.evaluate("el => el.tagName") or "").lower()
    except Exception:
        tag = ""

    if tag == "select":
        return _select_native(field, value)
    if _is_combobox(field):
        return _fill_combobox(page, field, value)
    try:
        field.fill(value, timeout=2500)
        return True
    except Exception:
        return False


# Labels worth reading but never answering automatically — the resume/cover
# uploads have their own path, and a free-text essay is not a screening answer.
_SKIP_LABELS = re.compile(r"resume|cv\b|cover letter|attach|upload|file", re.I)


def _labelled_fields(page) -> list[dict[str, Any]]:
    """Every visible control on the form paired with its visible label text."""
    try:
        return page.evaluate(
            """() => {
              const out = [];
              document.querySelectorAll('input, select, textarea').forEach((el, i) => {
                if (el.type === 'hidden' || el.type === 'file') return;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return;
                let label = '';
                if (el.id) {
                  const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                  if (l) label = l.innerText.trim();
                }
                if (!label && el.closest('label')) label = el.closest('label').innerText.trim();
                if (!label) label = el.getAttribute('aria-label') || '';
                if (!label) return;
                el.setAttribute('data-shortlistr-idx', String(i));
                out.push({
                  idx: String(i),
                  label: label.split('\\n')[0].slice(0, 200),
                  filled: !!(el.value && el.value.trim()),
                });
              });
              return out;
            }"""
        ) or []
    except Exception as e:
        logger.debug("could not enumerate labelled fields: %s", e)
        return []


def _answer_screening_questions(
    page, profile: dict[str, str], report: dict[str, Any], cv_text: str = ""
) -> None:
    """Answer the posting's own screening questions from the profile and CV.

    The named fields above cover what every form asks. This covers what *this*
    form asks — "are you comfortable with on-call", "do you have hands-on AWS
    experience" — which on Greenhouse are required, are comboboxes, and were the
    reason a filled-looking form still could not be submitted.

    ``screening.answer_for`` returns None whenever the profile and CV do not
    actually say, and None means leave it blank. Nothing here invents an answer.
    """
    from apply.screening import answer_for

    for field_info in _labelled_fields(page):
        if field_info.get("filled"):
            continue
        label = field_info.get("label") or ""
        if _SKIP_LABELS.search(label):
            continue

        answer = answer_for(label, profile, cv_text)
        if not answer:
            continue

        try:
            field = page.locator(f"[data-shortlistr-idx='{field_info['idx']}']").first
            if field.count() == 0 or not field.is_visible(timeout=600):
                continue
            if _set_field_value(page, field, answer):
                _mark_filled(report, f"q:{label[:48]}")
            else:
                _mark_unfilled(report, f"q:{label[:48]}")
        except Exception as e:
            logger.debug("screening answer failed for %r: %s", label[:40], e)


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


def _application_form_present(page) -> bool:
    """True when this page already shows something to fill in."""
    for sel in _FORM_MARKERS:
        try:
            if page.locator(sel).count():
                return True
        except Exception:
            continue
    return False


def _reveal_application_form(page, ats: str) -> None:
    """Scroll / navigate to the application form (never final submit).

    Most postings open on a description with an Apply button, and the form only
    exists after that click. This used to return immediately for every ATS
    except Greenhouse, so on Workday, Lever, Ashby or a plain careers page the
    run found no fields, filled nothing and closed the browser.

    The click is gated on there being no form yet. That matters because "Apply
    now" is navigation on a listing page and a submit control on a filled form —
    the same words either side of the line this tool must not cross. If anything
    fillable is already on screen, nothing is clicked.
    """
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
    except Exception:
        pass

    if ats == "greenhouse":
        _greenhouse_anchor(page)

    if _application_form_present(page):
        return

    _click_apply_entry(page)


def _click_apply_entry(page) -> None:
    """Click the control that leads to the form. Links first, then buttons."""
    for role in ("link", "button"):
        try:
            items = page.locator("a" if role == "link" else "button, input[type='button']")
            count = min(items.count(), 40)
        except Exception:
            continue
        for i in range(count):
            try:
                item = items.nth(i)
                text = (item.inner_text(timeout=300) or "").strip()
                if not text or not _APPLY_NAV_PATTERNS.search(text):
                    continue
                # "Submit"/"Send application" is the line we never cross, even
                # if some other pattern also matched the same control.
                if re.search(r"submit|send application|complete application", text, re.I):
                    continue
                item.click(timeout=3000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                if _application_form_present(page):
                    return
            except Exception:
                continue


def _greenhouse_anchor(page) -> None:
    for sel in ("#application", "a[href*='#app']", "[id*='application']"):
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.scroll_into_view_if_needed(timeout=3000)
                page.wait_for_timeout(400)
                break
        except Exception:
            continue


def _mark_filled(report: dict[str, Any], key: str) -> None:
    """Record a success, and retract any earlier failure for the same field.

    Filling runs several passes — different selector sets, then each iframe — so
    a field routinely misses on one and lands on the next. Without the retract,
    it ends up in both lists, and a report that says a field was both filled and
    not filled cannot be used to decide whether a form is ready to send.
    """
    if key not in report["filled"]:
        report["filled"].append(key)
    if key in report["unfilled"]:
        report["unfilled"].remove(key)


def _mark_unfilled(report: dict[str, Any], key: str) -> None:
    """Record a miss, unless an earlier pass already filled it."""
    if key not in report["filled"] and key not in report["unfilled"]:
        report["unfilled"].append(key)


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
                _mark_unfilled(report, key)
                continue
            if loc.is_visible(timeout=800):
                loc.fill(value, timeout=3000)
                _mark_filled(report, key)
        except Exception as e:
            logger.debug("Fill %s: %s", key, e)
            _mark_unfilled(report, key)

    if "first_name" not in report["filled"] and "full_name" not in report["filled"] and profile.get("full_name"):
        try:
            loc = page.locator("input[name*='name' i]").first
            if loc.count() and loc.is_visible(timeout=800):
                loc.fill(profile["full_name"], timeout=3000)
                _mark_filled(report, "full_name")
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


def _click_submit_control(page) -> bool:
    """Click the form's submit control. False when there is not one to click.

    Only reached via ``submit=True``. Buttons are matched on their visible
    label, and a disabled or hidden one is skipped rather than forced — an
    unclickable submit usually means the form still has a validation error, and
    forcing it would send something incomplete.
    """
    controls = page.locator("button, input[type='submit']")
    for i in range(min(controls.count(), 40)):
        control = controls.nth(i)
        try:
            if not control.is_visible() or not control.is_enabled():
                continue
            label = (control.inner_text(timeout=500) or "").strip()
            if not label:
                label = (control.get_attribute("value") or "").strip()
        except Exception:
            continue
        if label and _SUBMIT_PATTERNS.search(label):
            control.click()
            page.wait_for_timeout(3000)
            return True
    return False


def fill_application_form(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45_000,
    company: str = "",
    cv_pdf_path: str | None = None,
    submit: bool = False,
    screenshot_path: str | None = None,
) -> dict[str, Any]:
    """
    Open job URL and fill known fields from profile.yml.

    Returns a report dict. ``submit_blocked`` stays True unless the caller
    passed ``submit=True`` and the click actually landed — only
    ``apply/submit.py`` does that, and only for an approved job with a tailored
    CV and cover letter behind it.
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
            # Each step is guarded so one unhappy locator does not tear down the
            # `with` block. When the run is headed that took the window with it,
            # which is the worst possible outcome: the user is left with nothing
            # to finish by hand on a posting they already approved.
            for step, fn in (
                ("reveal", lambda: _reveal_application_form(page, ats)),
                ("fill", lambda: fill_ats_fields(page, ats, profile, report)),
                # Custom ATS questions (CTC, notice period, website, …) are
                # matched by visible label, not name/id — run on every page.
                ("labels", lambda: _fill_by_labels(page, profile, report)),
                # Last: the posting's own screening questions, which are the
                # ones that actually block submission on Greenhouse.
                ("screening", lambda: _answer_screening_questions(
                    page, profile, report, _cv_text())),
            ):
                try:
                    fn()
                except Exception as exc:
                    logger.warning("Apply assist %s step failed: %s", step, exc)
                    report["errors"].append(f"{step}: {exc}")

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
                try:
                    upload_resume(page, pdf_path, report)
                except Exception as exc:
                    logger.warning("Apply assist resume upload failed: %s", exc)
                    report["errors"].append(f"resume: {exc}")
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
            report["form_detected"] = _application_form_present(page)

            if submit:
                # Photograph before clicking: afterwards the page is a
                # confirmation or an error, and neither shows what was actually
                # entered — which is the thing there is otherwise no record of.
                if screenshot_path:
                    try:
                        page.screenshot(path=screenshot_path, full_page=True)
                        report["screenshot"] = screenshot_path
                    except Exception as exc:
                        logger.warning("submission screenshot failed: %s", exc)
                        report["errors"].append(f"screenshot: {exc}")
                if report.get("screenshot") or not screenshot_path:
                    try:
                        report["submitted"] = _click_submit_control(page)
                        report["submit_blocked"] = not report["submitted"]
                    except Exception as exc:
                        logger.warning("submit click failed: %s", exc)
                        report["errors"].append(f"submit: {exc}")
                else:
                    # No photograph means no record of what was sent, and that
                    # is the one thing auto-apply must not do quietly.
                    report["errors"].append("submit skipped: no screenshot captured")
            if not headless:
                if report["filled"]:
                    report["message"] = "Browser open — review fields and click Submit yourself."
                elif report["form_detected"]:
                    report["message"] = (
                        "Browser open — the form is here but nothing matched your profile "
                        "fields. Fill it in and click Submit yourself."
                    )
                else:
                    report["message"] = (
                        "Browser open — no application form on this page. It may be behind "
                        "a login or an Apply button this run could not reach. Continue "
                        "manually; nothing was submitted."
                    )
                # Keep the window open so the user can review (API headed assist).
                page.wait_for_timeout(120_000)
            browser.close()
    except Exception as e:
        logger.warning("Apply assist failed: %s", e)
        report["errors"].append(str(e))

    return report


def apply_assist_for_job(
    job_id: str,
    *,
    headless: bool = True,
    submit: bool = False,
    screenshot_path: str | None = None,
) -> dict[str, Any]:
    """Load job from SQLite, verify approved pipeline, run fill.

    ``submit`` defaults False: this is the manual assist path, which stops at a
    filled form. ``apply/submit.py`` passes True after its own checks.
    """
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
            "SELECT url, company, title, source, metadata_json FROM jobs WHERE id = ?",
            (jid,),
        ).fetchone()
    if not row or not row["url"]:
        raise ValueError(f"Job {jid} has no URL")

    from apply.channels import (
        LINK_ONLY_MESSAGE, NotFillableError, application_url, is_link_only,
    )

    # Aggregators list a job under their own address and carry the employer's
    # real application link alongside it. Filling the listing page fills
    # nothing, so prefer the employer's link whenever the source gave us one.
    target_url = application_url(row)
    if is_link_only(target_url, str(row["source"] or "")):
        raise NotFillableError(LINK_ONLY_MESSAGE)

    from apply.ats_strategies import resolve_resume_pdf
    from processors.generate_cv import generate_cv_for_job

    company = str(row["company"] or "")
    job_payload = {
        "url": target_url,
        "company": company,
        "title": row["title"] or "",
        "jd_snippet": "",
        "job_id": jid,
    }

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
        cv_pdf = resolve_resume_pdf(company, job_id=jid)
    if not cv_pdf:
        try:
            gen = generate_cv_for_job(job_payload)
            if gen.get("success"):
                cv_pdf = gen.get("path")
        except Exception as exc:
            logger.debug("CV PDF generation skipped: %s", exc)

    report = fill_application_form(
        target_url,
        headless=headless,
        company=company,
        cv_pdf_path=cv_pdf,
        submit=submit,
        screenshot_path=screenshot_path,
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
