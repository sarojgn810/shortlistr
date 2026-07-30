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
_URL_RE = re.compile(
    r'https?://(?:[a-zA-Z0-9-]+\.)*(?:'
    r'naukri\.com/job-listings|'
    r'linkedin\.com/jobs/view|'
    r'indeed\.com/viewjob|'
    r'remotive\.com/remote-jobs|'
    r'himalayas\.app/jobs|'
    r'remoteok\.com/l|'
    r'weworkremotely\.com/remote-jobs|'
    r'workingnomads\.com/jobs|'
    r'greenhouse\.io|lever\.co|ashby\.io|'
    r'jobs\.smartrecruiters\.com|'
    r'wellfound\.com/jobs|'
    r'otta\.com/jobs|instahyre\.com/job|cutshort\.io'
    r')[^\s"\'<>)]+',
    re.IGNORECASE,
)


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
    """Extract plain text body from Gmail message payload."""
    payload = msg_data.get("payload", {})
    body = ""

    def _walk(part):
        nonlocal body
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                body += base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)
    return body


def _get_header(msg_data: dict, name: str) -> str:
    headers = msg_data.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ── Job alert handler ─────────────────────────────────────────────────────────

def fetch_alert_job_records(max_messages: int = 50) -> list:
    """
    Scan unread inbox for job-alert senders; return JobRecord list (no pipeline write).
    Used by GmailAdapter and monitor_inbox().
    """
    from models.job import JobRecord
    from scrapers.ats_url_resolver import resolve_job_url

    service = _get_gmail_service()
    if not service:
        return []

    state = _load_state()
    processed = set(state.get("processed_ids", []))

    try:
        result = service.users().messages().list(
            userId="me",
            q="is:unread newer_than:2d",
            maxResults=max_messages,
        ).execute()
        messages = result.get("messages", [])
    except Exception as e:
        logger.warning(f"Gmail list error: {e}")
        return []

    all_job_urls: list[str] = []
    new_processed = set(processed)

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

        is_alert = any(s in sender for s in JOB_ALERT_SENDERS)
        if not is_alert:
            continue

        new_processed.add(msg_id)
        urls = _URL_RE.findall(body + " " + subject)
        if urls:
            all_job_urls.extend(urls)

    state["processed_ids"] = list(new_processed)[-500:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    seen: set[str] = set()
    jobs = []
    for url in all_job_urls:
        u = url.split("?")[0].strip()
        if not u or u in seen:
            continue
        seen.add(u)
        resolved = resolve_job_url(u)
        if resolved:
            jobs.append(JobRecord.from_dict({**resolved, "source": "Gmail"}))
        else:
            jobs.append(
                JobRecord(
                    url=u,
                    source="Gmail",
                    company="Unknown",
                    title="Email alert",
                    notes=f"From job alert email",
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
