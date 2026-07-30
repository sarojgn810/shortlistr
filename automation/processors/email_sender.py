"""
Email Sender — Gmail API with OAuth2 (no app password needed).

First-time setup:
    python3 setup_oauth.py
This opens a browser to authorise Gmail access and saves token.json.
All subsequent runs use the saved token (auto-refreshed).
"""

import base64
import logging
import os
import pickle
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from config import CANDIDATE, GMAIL_SCOPES, GMAIL_TOKEN_PATH, TRACKER_PATH

logger = logging.getLogger(__name__)

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH = GMAIL_TOKEN_PATH
SCOPES     = GMAIL_SCOPES

SETUP_MSG = """
╔══════════════════════════════════════════════════════╗
║        GMAIL OAUTH TOKEN NOT FOUND                   ║
╠══════════════════════════════════════════════════════╣
║  Run this once to authorise Gmail:                   ║
║                                                      ║
║    cd automation                                 ║
║    python3 setup_oauth.py                            ║
║                                                      ║
║  This opens a browser, you log in once, done.        ║
║  Token is saved — no re-auth needed after that.      ║
╚══════════════════════════════════════════════════════╝
"""


def _get_gmail_service():
    """Load OAuth credentials and return Gmail API service."""
    try:
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error("Run: pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        return None

    if not os.path.exists(TOKEN_PATH):
        print(SETUP_MSG)
        return None

    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

    if not creds or not creds.valid:
        print(SETUP_MSG)
        return None

    return build("gmail", "v1", credentials=creds)


def _build_message(to_email, subject, body, resume_path=None):
    msg = MIMEMultipart()
    msg["From"]    = CANDIDATE["email"]
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if resume_path and os.path.exists(resume_path):
        with open(resume_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(resume_path)}"')
        msg.attach(part)

    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def send_application_email(
    to_email,
    subject,
    body,
    resume_path=None,
    dry_run=False,
    *,
    job_id=None,
    company="",
    role="",
    cover_letter_text=None,
):
    resume_path = resume_path or CANDIDATE["resume_path"]
    preview = body if isinstance(body, str) else str(body)

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — Would send to: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body preview:\n{preview[:300]}...")
        print(f"Resume: {resume_path}")
        print('='*60)
        if job_id:
            _record_email_receipt(
                job_id=job_id,
                to_email=to_email,
                subject=subject,
                body=preview,
                resume_path=resume_path,
                cover_letter_text=cover_letter_text or preview,
                company=company,
                role=role,
                dry_run=True,
            )
        return True

    service = _get_gmail_service()
    if not service:
        return False

    try:
        message = _build_message(to_email, subject, body, resume_path)
        service.users().messages().send(userId="me", body=message).execute()
        logger.info(f"✓ Email sent to {to_email} | {subject[:50]}")
        if job_id:
            _record_email_receipt(
                job_id=job_id,
                to_email=to_email,
                subject=subject,
                body=preview,
                resume_path=resume_path,
                cover_letter_text=cover_letter_text or preview,
                company=company,
                role=role,
                dry_run=False,
            )
        return True
    except Exception as e:
        logger.error(f"Email send error to {to_email}: {e}")
        return False


def _record_email_receipt(
    *,
    job_id,
    to_email,
    subject,
    body,
    resume_path,
    cover_letter_text,
    company,
    role,
    dry_run,
):
    try:
        from store.receipts import create_receipt
        from store.status import mark_submitted

        channel = "email" if not dry_run else "prep"
        app_id = None
        if not dry_run:
            app_id = mark_submitted(job_id, company=company, role=role, actor="email_sender")

        create_receipt(
            job_id,
            channel,
            fields={
                "to_email": to_email,
                "subject": subject,
                "dry_run": dry_run,
            },
            resume_path=resume_path,
            cover_letter_text=cover_letter_text or body,
            application_id=app_id,
            actor="email_sender",
        )
    except Exception as e:
        logger.warning(f"Receipt not recorded for {job_id}: {e}")


def send_daily_summary(new_jobs, applied, linkedin_manual=None):
    import datetime
    n_new  = len(new_jobs)
    n_sent = sum(1 for j in applied if j.get("email_sent") == "Yes")
    manual = linkedin_manual or []

    lines = [
        f"Daily shortlistr summary — {datetime.date.today()}",
        "",
        f"NEW STRONG-FIT JOBS FOUND: {n_new}",
        f"EMAILS SENT (ATS):         {n_sent}",
        f"LINKEDIN MANUAL APPLY:     {len(manual)}",
        "",
    ]

    # ── LinkedIn manual-apply section (most important — your action needed) ──
    if manual:
        lines += [
            "═══ ACTION REQUIRED — Apply on LinkedIn ═══════════════",
            "These are strong-fit roles. Click each link and apply.",
            "",
        ]
        for j in sorted(manual, key=lambda x: -x.get("fit_score", 0)):
            lines += [
                f"[Score {j.get('fit_score', 0):2d}] {j.get('company', '')} — {j.get('title', '')}",
                f"         Location : {j.get('location', 'Remote')}",
                f"         Apply    : {j.get('url', '')}",
                "",
            ]
        lines.append("────────────────────────────────────────────────────")
        lines.append("")

    # ── All new listings ──
    if new_jobs:
        lines += ["─── All New Strong-Fit Listings ──────────────────────", ""]
        for j in new_jobs[:20]:
            sent_flag = "✓ Email sent" if j.get("email_sent") == "Yes" else \
                        "✓ Easy Applied" if j.get("status") == "Applied" else \
                        "→ Apply yourself"
            lines += [
                f"• [{j.get('source','?')}] {j.get('company','')} — {j.get('title','')}",
                f"  Score: {j.get('fit_score',0)} | {j.get('location','')} | {sent_flag}",
                f"  {j.get('url','')}",
                "",
            ]
    else:
        lines.append("No new strong-fit jobs found today.")

    lines += [
        "────────────────────────────────────────────────────",
        "",
        f"Tracker: {TRACKER_PATH}",
        "— shortlistr",
    ]

    return send_application_email(
        to_email=CANDIDATE["email"],
        subject=f"[shortlistr] {n_new} new jobs | {len(manual)} to apply on LinkedIn — {datetime.date.today()}",
        body="\n".join(lines),
        resume_path=None,
    )
