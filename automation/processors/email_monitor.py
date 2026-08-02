"""
Email Monitor — Gmail API
Watches inbox for:
  1. Job alert emails (Naukri, LinkedIn, Indeed, Remotive, etc.)
     → extracts job URLs → feeds into shortlistr pipeline.md
  2. Recruiter direct messages
     → drafts a personalised reply → saves to data/recruiter_drafts.md

Run standalone:
    python3 processors/email_monitor.py

Or called from run_daily.py as: monitor_inbox()
"""

import base64
import logging
import os
import pickle
import re
import json
import sys
from datetime import datetime, timezone
from email import message_from_bytes

# Ensure automation/ is on the path regardless of how the script is invoked
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CANDIDATE, GMAIL_SCOPES, GMAIL_TOKEN_PATH, PIPELINE_PATH, DATA_DIR

logger = logging.getLogger(__name__)

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH  = GMAIL_TOKEN_PATH
DRAFTS_PATH = os.path.join(DATA_DIR, "recruiter_drafts.md")
STATE_PATH  = os.path.join(DATA_DIR, "email_monitor_state.json")

SCOPES = GMAIL_SCOPES

# ── Sender patterns that indicate job alerts ──────────────────────────────────
JOB_ALERT_SENDERS = [
    "naukri.com", "linkedin.com", "indeed.com", "glassdoor.com",
    "remotive.com", "himalayas.app", "remoteok.com", "weworkremotely.com",
    "workingnomads.com", "remote.co", "nodesk.co", "jobspresso.co",
    "simplyhired.com", "monster.com", "careerbuilder.com",
    "wellfound.com", "angellist.com", "instahyre.com", "cutshort.io",
    "otta.com", "ziprecruiter.com", "dice.com",
    # India digests that were missing from the original list
    "hirist.tech", "hirist.com", "iimjobs.com", "foundit.in",
    "timesjobs.com", "shine.com", "freshersworld.com",
]

# ── Recruiter signals in subject/body ────────────────────────────────────────
RECRUITER_SIGNALS = [
    "i came across your profile", "i found your profile", "i noticed your profile",
    "i wanted to reach out", "we have an opening", "we have a role",
    "exciting opportunity", "great opportunity", "perfect fit",
    "would you be interested", "are you open to", "open to new opportunities",
    "your background caught", "your experience aligns", "recruiter",
    "talent acquisition", "sourcing", "headhunter", "staffing",
    "i'd love to connect", "i would love to connect",
    "on behalf of", "hiring for", "currently hiring",
]

# ── URL extractor ─────────────────────────────────────────────────────────────
# Prefer broad host patterns — digests wrap links in trackers we unwrap later.
_URL_RE = re.compile(
    r'https?://[^\s"\'<>)\\]]+',
    re.IGNORECASE,
)
_HREF_RE = re.compile(
    r'''href=["'](https?://[^"']+)["']''',
    re.IGNORECASE,
)

# Path-ish patterns that look like a real posting (not homepage / settings).
_JOB_URL_PATTERNS = (
    r"naukri\.com/.*/?jd/job-listings",
    r"naukri\.com/job-listings",
    r"linkedin\.com/jobs/view",
    r"indeed\.com/(viewjob|rc/clk|pagead/clk)",
    r"cts\.indeed\.com/",  # Indeed click tracker — keep; enrich may follow
    r"glassdoor\.[a-z.]+/.+joblisting",
    r"hirist\.(tech|com)/j/",
    r"cutshort\.io/(job|jobs)/",
    r"instahyre\.com/job",
    r"wellfound\.com/jobs/",
    r"angel\.co/company/.+/jobs",
    r"angellist\.com/.+/jobs",
    r"greenhouse\.io/.+",
    r"lever\.co/.+",
    r"ashbyhq\.com/.+",
    r"ashby\.io/.+",
    r"myworkdayjobs\.com/.+",
    r"workable\.com/(view|jobs)/",
    r"smartrecruiters\.com/.+",
    r"remotive\.(com|io)/remote-jobs/",
    r"himalayas\.app/jobs/",
    r"remoteok\.com/remote-jobs/",
    r"weworkremotely\.com/remote-jobs/",
    r"otta\.com/jobs/",
    r"dice\.com/job-detail/",
    r"ziprecruiter\.com/jobs/",
    r"foundit\.in/job/",
    r"iimjobs\.com/j/",
    r"postoffice\.hirist\.[a-z]+/CL0/",  # unwrapped later
    r"pstmrk\.it/",  # unwrapped later
)
_JOB_URL_RE = re.compile("|".join(f"(?:{p})" for p in _JOB_URL_PATTERNS), re.I)


def _is_plausible_job_url(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http"):
        return False
    skip = (
        "unsubscribe",
        "mailto:",
        "/logo",
        "pixel",
        "brand-views",
        "favicon",
        "/assets/email",
        "media.glassdoor",
        "mnjuser",
        "/settings",
        "/course/",
        "/jobfeed",
        "feedback.php",
        "termscondition",
        "fakejobtrend",
        "onelink.me",
        "engage.indeed.com",
        "u003e",
    )
    if any(s in u for s in skip):
        return False
    # Bare board homepages (no path beyond /)
    from urllib.parse import urlparse

    path = (urlparse(u).path or "").strip("/")
    if not path and "cts.indeed.com" not in u and "pstmrk.it" not in u:
        return False
    return bool(_JOB_URL_RE.search(u))


def _unwrap_tracking_url(url: str) -> str:
    """Turn digest/tracker wrappers into the underlying job URL when possible."""
    from html import unescape
    from urllib.parse import unquote

    u = unescape((url or "").strip())
    if not u:
        return u

    # Hirist / iimjobs click wrappers: .../CL0/https:%2F%2Fwww.hirist.tech%2Fj%2F...
    if "/CL0/" in u:
        encoded = u.split("/CL0/", 1)[1]
        encoded = re.split(r"/\d+/[0-9a-f-]{8,}", encoded, maxsplit=1)[0]
        decoded = unquote(encoded)
        if decoded.startswith("http"):
            return decoded.split("?")[0] if "/j/" in decoded else decoded

    # Remotive Postmark: track.pstmrk.it/3s/<urlencoded-dest>/...
    if "pstmrk.it" in u and "/3s/" in u:
        dest = u.split("/3s/", 1)[1]
        dest = dest.split("/eHy2/")[0].split("/Ag7HAQ/")[0]
        dest = unquote(dest)
        if not dest.startswith("http"):
            dest = "https://" + dest.lstrip("/")
        return dest

    return u


def _canonicalize_job_url(url: str) -> str:
    u = _unwrap_tracking_url(url).strip().rstrip(".,);]>\"'")
    if not u:
        return ""
    # Glassdoor partner links need query params; Naukri /jd/ links keep id in path.
    if "joblisting.htm" in u.lower() or "partner/joblisting" in u.lower():
        return u.split("#")[0]
    if "/jd/job-listings" in u.lower() or "hirist.tech/j/" in u.lower():
        return u.split("#")[0]
    return u.split("?")[0].split("#")[0]


_HREF_TEXT_RE = re.compile(
    r'''href=["'](https?://[^"']+)["'][^>]*>(.*?)</a>''',
    re.IGNORECASE | re.DOTALL,
)


def _clean_anchor_text(raw: str) -> str:
    from html import unescape

    t = unescape(raw or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Digests often use "Apply" / "View job" as the only link text.
    if len(t) < 8 or t.lower() in {
        "apply",
        "apply now",
        "view job",
        "view",
        "click here",
        "here",
        "see job",
        "open role",
        "role",
        "x",
    }:
        return ""
    # Glassdoor: "Kaseya 3.7 ★ Site Reliability Engineer Bengaluru Easy Apply 2d"
    t = re.sub(r"^[A-Za-z0-9 .,&+'()-]{1,40}?\d\.\d\s*★\s*", "", t)
    t = re.sub(
        r"\s*(?:Easy Apply|Just posted|\d+d)\s*$",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s*₹[\d.LCrK+\s\-–]+(?:\(\s*Glassdoor[^)]*\))?\s*$", "", t, flags=re.I)
    return t.strip(" -–|:")[:160]


def _title_from_url_slug(url: str) -> str:
    u = url or ""
    if "hirist.tech/j/" in u:
        slug = u.rstrip("/").split("/")[-1]
        return slug.replace("-", " ")[:120]
    if "/jd/job-listings-" in u:
        slug = u.split("/jd/job-listings-", 1)[-1].split("?")[0]
        return slug.replace("-", " ")[:120]
    if "job-listings-" in u and "naukri.com" in u:
        slug = u.split("job-listings-", 1)[-1].split("?")[0]
        return slug.replace("-", " ")[:120]
    return ""


def _subject_title_hint(subject: str) -> str:
    """Pull the lead role from digest subjects like 'SRE at Shell and 11 more…'."""
    s = (subject or "").strip()
    if not s:
        return ""
    s = re.sub(r"^(re:\s*)+", "", s, flags=re.I)
    s = re.sub(r"\s+and\s+\d+\s+more\b.*$", "", s, flags=re.I)
    s = re.sub(r"\s+for you\.?$", "", s, flags=re.I)
    s = re.sub(r"\s+in\s+[A-Za-z][A-Za-z\s/,-]{2,40}\.?$", "", s, flags=re.I)
    return s.strip(" -–|:.")[:160]


def _subject_location_hint(subject: str) -> str:
    m = re.search(
        r"\bin\s+([A-Za-z][A-Za-z\s/,-]{1,40}?)(?:\s+for\s+you)?\.?\s*$",
        subject or "",
        re.I,
    )
    if not m:
        return ""
    return m.group(1).strip(" .,")[:80]


def _extract_job_links(text: str) -> list[tuple[str, str]]:
    """Return [(canonical_url, anchor_title_hint), ...] de-duplicated by URL."""
    from html import unescape

    blob = unescape(text or "")
    url_titles: dict[str, str] = {}
    ordered_urls: list[str] = []

    def _note(raw_url: str, hint: str = "") -> None:
        u = _canonicalize_job_url(raw_url)
        if not u or not _is_plausible_job_url(u):
            return
        key = u.lower()
        if key not in url_titles:
            ordered_urls.append(u)
            url_titles[key] = hint
        elif hint and not url_titles[key]:
            url_titles[key] = hint

    for raw_url, raw_text in _HREF_TEXT_RE.findall(blob):
        _note(raw_url, _clean_anchor_text(raw_text))
    for raw in _HREF_RE.findall(blob) + _URL_RE.findall(blob):
        _note(raw)

    return [(u, url_titles.get(u.lower(), "")) for u in ordered_urls]


def _extract_urls_from_text(text: str) -> list[str]:
    return [u for u, _ in _extract_job_links(text)]

# ── Gmail auth ────────────────────────────────────────────────────────────────

def _get_gmail_service():
    """Return authenticated Gmail API service, or None if not set up."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(TOKEN_PATH, "wb") as f:
                    pickle.dump(creds, f)
            else:
                logger.warning("Gmail token missing or expired. Run: python3 setup_oauth.py")
                return None

        granted = set(creds.scopes or [])
        if not granted.intersection({"https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"}):
            logger.warning(
                "Gmail token lacks inbox read scope (send-only token). "
                "Re-run: python3 setup_oauth.py"
            )
            return None

        return build("gmail", "v1", credentials=creds)
    except ImportError:
        logger.warning("google-api-python-client not installed. Run: pip install google-api-python-client google-auth-oauthlib --break-system-packages")
        return None
    except Exception as e:
        if "insufficient" in str(e).lower():
            logger.warning("Gmail insufficient scopes. Re-run: python3 setup_oauth.py")
        else:
            logger.warning(f"Gmail auth error: {e}")
        return None


# ── State: track processed message IDs ────────────────────────────────────────

def _load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"processed_ids": [], "last_run": ""}

def _save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ── Message helpers ───────────────────────────────────────────────────────────

def _decode_body(msg_data: dict) -> str:
    """Extract plain + HTML bodies from a Gmail message payload.

    Job digests are often HTML-only (no text/plain). Older code ignored HTML,
    so Glassdoor/Naukri/Hirist alerts looked like they had zero links.
    """
    payload = msg_data.get("payload", {})
    plains: list[str] = []
    htmls: list[str] = []

    def _decode_data(data: str) -> str:
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        data = (part.get("body") or {}).get("data") or ""
        if data:
            text = _decode_data(data)
            if mime == "text/plain":
                plains.append(text)
            elif mime == "text/html":
                htmls.append(text)
            elif not mime and text:
                plains.append(text)
        for sub in part.get("parts") or []:
            _walk(sub)

    _walk(payload)
    # Single-part messages put data on the root payload.
    root_data = (payload.get("body") or {}).get("data") or ""
    root_mime = (payload.get("mimeType") or "").lower()
    if root_data and not plains and not htmls:
        text = _decode_data(root_data)
        if root_mime == "text/html":
            htmls.append(text)
        else:
            plains.append(text)
    return "\n".join(plains + htmls)


def _get_header(msg_data: dict, name: str) -> str:
    headers = msg_data.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ── Job alert handler ─────────────────────────────────────────────────────────

# How far back to look for job-alert digests (read + unread).
GMAIL_ALERT_DAYS = 7
GMAIL_ALERT_QUERY = f"newer_than:{GMAIL_ALERT_DAYS}d"
# Digests are noisy; pull enough that a busy week of alerts is covered.
GMAIL_ALERT_MAX_MESSAGES = 100

# Bump when link extraction changes. Messages previously recorded as "checked,
# nothing in it" are re-examined whenever this moves, so a decode or regex bug
# can never permanently bury a digest — which is the reason those ids were not
# remembered at all before.
EXTRACTOR_VERSION = 1

# Invites carry the named role plus a few related openings (observed max 5);
# digests carry 12+. Above this, the mail is a list whatever its headline.
SINGLE_ROLE_LINK_LIMIT = 6


def _alert_sender_query() -> str:
    """Filter by sender in the Gmail query, not after downloading the message.

    The scan used to ask for everything in the window and then read the `From`
    header of each full message to decide whether it was an alert — paying a
    round-trip per message for mail it was about to discard. Gmail's `q` does
    this server-side for free.
    """
    if not JOB_ALERT_SENDERS:
        return GMAIL_ALERT_QUERY
    senders = " OR ".join(f"from:{s}" for s in JOB_ALERT_SENDERS)
    return f"{GMAIL_ALERT_QUERY} ({senders})"


def fetch_alert_job_records(max_messages: int | None = None, *, reader=None) -> list:
    """
    Scan recent inbox for job-alert senders (read and unread); return JobRecords.

    Used by GmailAdapter and monitor_inbox(). Does not write the pipeline.
    """
    from typing import Any  # noqa: F401  (candidates tuple annotation)

    from models.job import JobRecord
    from processors.email_intent import classify_intent, link_matches_subject
    from scrapers.ats_url_resolver import resolve_job_url

    if max_messages is None:
        max_messages = GMAIL_ALERT_MAX_MESSAGES

    # Injectable so callers and tests can supply any MailboxReader. Reaching into
    # this module to patch the Gmail service instead would depend on which of
    # `processors.email_monitor` / `automation.processors.email_monitor` got
    # imported first — two module objects, one patch, silent live network calls.
    if reader is None:
        from mail import get_reader

        reader = get_reader()
    if reader is None:
        return []

    state = _load_state()
    processed = set(state.get("processed_ids", []))
    # Alert mail that genuinely carries no job link — "verify your address",
    # "questionnaire pending", a digest that is all social buttons. These were
    # never remembered, so every scan re-downloaded the same dead messages in
    # full, forever. Remembered now, but only for the extractor that judged
    # them: bump EXTRACTOR_VERSION and they all get another look.
    empty: set[str] = set()
    if int(state.get("empty_extractor_version", -1)) == EXTRACTOR_VERSION:
        empty = set(state.get("empty_ids", []))
    skip = processed | empty

    try:
        message_ids = reader.search_recent(
            days=GMAIL_ALERT_DAYS, senders=JOB_ALERT_SENDERS
        )[:max_messages]
    except Exception as e:
        logger.warning("%s mailbox list error: %s", reader.name, e)
        return []

    # (url, title_hint, location_hint, intent, about_one_role)
    candidates: list[tuple[str, str, str, Any, bool]] = []
    new_processed = set(processed)
    new_empty = set(empty)
    intents: dict[str, int] = {}
    actionable: list[dict] = []

    for msg_id in message_ids:
        if msg_id in skip:
            continue

        message = reader.fetch(msg_id)
        if message is None:
            continue

        sender = (message.sender or "").lower()
        subject = message.subject
        body = message.body

        # The reader narrows by sender where it can, but that is a hint — a
        # backend may hand back more, so the check stays here too.
        if not message.is_from(JOB_ALERT_SENDERS):
            continue

        # What the message *means*, not just whether it holds links. An employer
        # writing "Reminder: Senior SRE at Blitzy" is inbound interest in this
        # user; "10+ Top Tech Jobs" is a broadcast. Both used to be the same
        # thing here, so the first was indistinguishable from an advert.
        intent = classify_intent(subject, body, sender)
        intents[intent.kind] = intents.get(intent.kind, 0) + 1
        if intent.is_actionable:
            actionable.append({
                "kind": intent.kind,
                "company": intent.company,
                "subject": subject,
                "sender": message.sender,
            })

        links = _extract_job_links(body + " " + subject)
        if links:
            subj_title = _subject_title_hint(subject)
            subj_loc = _subject_location_hint(subject)
            # "SRE 3 role at eBay: you would be a great fit" is an invite about
            # *one* role, but the mail carries a footer of unrelated openings.
            # Only the link that matches the subject is inbound interest; the
            # rest are ordinary discovery. A digest never qualifies.
            for url, anchor in links:
                title = _title_from_url_slug(url) or anchor or subj_title or "Email alert"
                is_the_role = (
                    len(links) <= SINGLE_ROLE_LINK_LIMIT
                    and link_matches_subject(subject, title)
                )
                candidates.append((url, title, subj_loc, intent, is_the_role))
            # Only mark handled when we actually extracted links — otherwise a
            # decode bug would permanently skip these unread digests.
            new_processed.add(msg_id)
        else:
            # An invite or an application update with no link is still worth
            # keeping: the company name is in the subject and the user needs to
            # see it. Marking it "empty" would bury it forever.
            if not intent.is_actionable:
                new_empty.add(msg_id)
            logger.debug(
                "Job alert with no extractable URLs yet: %s | %s",
                sender[:60],
                subject[:80],
            )

    state["processed_ids"] = list(new_processed)[-500:]
    state["empty_ids"] = list(new_empty)[-500:]
    state["empty_extractor_version"] = EXTRACTOR_VERSION
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    if intents:
        logger.info(
            "Email intents: %s%s",
            ", ".join(f"{k}={v}" for k, v in sorted(intents.items())),
            f" — {len(actionable)} need your attention" if actionable else "",
        )
    for item in actionable:
        logger.info(
            "  %s%s: %s",
            item["kind"],
            f" ({item['company']})" if item["company"] else "",
            item["subject"][:80],
        )

    seen: set[str] = set()
    jobs = []
    for url, title_hint, loc_hint, intent, is_the_role in candidates:
        u = _canonicalize_job_url(url)
        if not u or u.lower() in seen:
            continue
        seen.add(u.lower())
        # Carried onto the record so Discover can tell "an employer asked for
        # you" apart from "this was in a list of 60".
        meta = {
            "email_intent": intent.kind,
            "inbound_interest": intent.is_inbound_interest and is_the_role,
        }
        if intent.company:
            meta["email_company_hint"] = intent.company
        resolved = resolve_job_url(u)
        if resolved:
            data = {**resolved, "source": "Gmail"}
            # Prefer slug/anchor/subject when resolver only has a stub title.
            rt = (data.get("title") or "").strip()
            if not rt or rt.lower() in {"email alert", "unknown", "job"}:
                data["title"] = title_hint
            if loc_hint and not (data.get("location") or "").strip():
                data["location"] = loc_hint
            record = JobRecord.from_dict(data)
            record.metadata = {**(record.metadata or {}), **meta}
            jobs.append(record)
        else:
            jobs.append(
                JobRecord(
                    url=u,
                    source="Gmail",
                    company=intent.company or "Unknown",
                    title=title_hint,
                    location=loc_hint or "",
                    notes="From job alert email",
                    metadata=meta,
                )
            )
    return jobs


def process_recruiter_messages(max_messages: int = 50) -> int:
    """Scan inbox for recruiter messages and save drafts. Returns draft count."""
    service = _get_gmail_service()
    if not service:
        return 0

    state = _load_state()
    processed = set(state.get("processed_ids", []))
    saved = 0

    try:
        result = service.users().messages().list(
            userId="me",
            q="is:unread newer_than:2d",
            maxResults=max_messages,
        ).execute()
        messages = result.get("messages", [])
    except Exception as e:
        logger.warning(f"Gmail list error: {e}")
        return 0

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        if msg_id in processed:
            continue

        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
        except Exception as e:
            logger.debug(f"Could not fetch message {msg_id}: {e}")
            continue

        sender = _get_header(msg, "From").lower()
        subject = _get_header(msg, "Subject")
        body = _decode_body(msg)
        full_text = f"{subject} {body}".lower()

        is_alert = any(s in sender for s in JOB_ALERT_SENDERS)
        if is_alert:
            continue

        is_recruiter = any(sig in full_text for sig in RECRUITER_SIGNALS)
        if not is_recruiter:
            continue

        processed.add(msg_id)
        draft = _draft_recruiter_reply(sender, subject, body)
        _save_recruiter_draft(sender, subject, draft)
        try:
            from processors.email_routing import route_recruiter_message

            route_recruiter_message(sender=sender, subject=subject, body=body, dry_run=False)
        except Exception as e:
            logger.debug("Email routing: %s", e)
        saved += 1

    state["processed_ids"] = list(processed)[-500:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)
    return saved


def _feed_pipeline(urls: list[str]):
    """Legacy: feed alert URLs to SQLite pipeline (+ export markdown)."""
    from models.job import JobRecord
    from scrapers.ats_url_resolver import resolve_job_url
    from store.pipeline_feed import feed_jobs

    if not urls:
        return

    jobs = []
    for u in urls:
        resolved = resolve_job_url(u)
        if resolved:
            jobs.append(JobRecord.from_dict({**resolved, "source": "Gmail"}))
        else:
            jobs.append(
                JobRecord(url=u, source="Gmail", company="Unknown", title="Email alert")
            )
    feed_jobs(jobs, export_markdown=True)


# ── Recruiter reply drafter ───────────────────────────────────────────────────

def _draft_recruiter_reply(sender: str, subject: str, body: str) -> str:
    """Generate a polished reply to a recruiter email."""
    name = CANDIDATE["name"]
    # Try to extract recruiter's first name from body
    recruiter_name = "there"
    m = re.search(r"(?:hi|hello|dear|hey)[,\s]+([A-Z][a-z]+)", body, re.IGNORECASE)
    if m:
        recruiter_name = m.group(1)

    # Detect if it mentions a specific role
    role_m = re.search(
        r"(?:role|position|opportunity)[^\n]*?(?:of|for|as)\s+([A-Za-z /]+Engineer|[A-Za-z /]+SRE|[A-Za-z /]+DevOps)",
        body, re.IGNORECASE,
    )
    role_mention = f"the {role_m.group(1).strip()} role" if role_m else "this opportunity"

    draft = f"""Hi {recruiter_name},

Thank you for reaching out — {role_mention} sounds interesting.

I'm currently open to remote-first SRE / Platform / AIOps roles with strong-fit compensation (₹40–60L INR or $80–120K USD for global remote). My background is 9+ years in SRE at payment-grade scale, with a specific focus on AI-driven reliability: LLM-powered runbook automation, predictive anomaly detection, and MLOps observability.

Happy to connect for a quick call to see if there's a mutual fit. My availability (IST): Mon–Fri, 10 AM – 6 PM.

Best,
{name}
LinkedIn: {CANDIDATE['linkedin']}
GitHub:   {CANDIDATE['github']}
"""
    try:
        from writing.sanitize import sanitize

        return sanitize(draft, mode="prose")
    except Exception:
        return draft


def _save_recruiter_draft(sender: str, subject: str, draft: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"""
---
## {today} | From: {sender}
**Subject:** {subject}

**Draft reply:**

```
{draft}
```
"""
    with open(DRAFTS_PATH, "a") as f:
        f.write(entry)
    logger.info(f"Email monitor: recruiter draft saved → {DRAFTS_PATH}")


# ── Main monitor ──────────────────────────────────────────────────────────────

def monitor_inbox(max_messages: int = 50) -> dict:
    """
    Scan inbox for job alerts and recruiter messages.
    Job alerts → SQLite pipeline. Recruiter messages → drafts file.
    """
    summary = {"job_urls_found": 0, "recruiter_drafts_saved": 0, "errors": []}

    try:
        jobs = fetch_alert_job_records(max_messages=max_messages)
        summary["job_urls_found"] = len(jobs)
        if jobs:
            from store.pipeline_feed import feed_jobs
            feed_jobs(jobs, export_markdown=True)
    except Exception as e:
        logger.warning(f"Gmail job alert scan failed: {e}")
        summary["errors"].append(str(e))

    try:
        summary["recruiter_drafts_saved"] = process_recruiter_messages(max_messages=max_messages)
    except Exception as e:
        logger.warning(f"Gmail recruiter scan failed: {e}")
        summary["errors"].append(str(e))

    logger.info(
        f"Email monitor done: {summary['job_urls_found']} job URLs, "
        f"{summary['recruiter_drafts_saved']} recruiter drafts"
    )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    result = monitor_inbox()
    print(f"\n✅  Job URLs found    : {result['job_urls_found']}")
    print(f"✅  Recruiter drafts  : {result['recruiter_drafts_saved']}")
    if result["errors"]:
        print(f"⚠️  Errors: {result['errors']}")
