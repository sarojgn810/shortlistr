"""Contact resolution orchestrator — Stages 0–6 (never auto-sends).

Prep → Resolve contact runs this for one job. Results are scored and labeled
SEND_NOW / VERIFY_FIRST / REVIEW / SKIP for the user to act on.
"""

from __future__ import annotations

import logging
from typing import Any

from contacts.domain import resolve_company_domain
from contacts.email_find import suggest_for_contact, verify_email
from contacts.pattern import (
    generate_emails,
    learn_pattern,
    pairs_from_known_emails,
    _split_name,
)
from contacts.person_discover import (
    apply_url_forensics,
    github_emails_for_login,
    linkedin_search_urls,
    mine_ats_people,
    mine_jd_people,
    search_github_org_members,
    title_ladder_people,
)
from contacts.score import decision_for, final_score, map_verify_status, rank_people
from store import contact_resolution as cr_store
from store import db as store

logger = logging.getLogger(__name__)


def _secrets() -> dict[str, str]:
    out = {"serper": "", "github": "", "email_verify": "", "verify_provider": "hunter"}
    try:
        from secrets_store import get_secret, has_secret

        if has_secret("AUTOJOB_SERPER_API_KEY"):
            out["serper"] = get_secret("AUTOJOB_SERPER_API_KEY") or ""
        if has_secret("AUTOJOB_GITHUB_TOKEN"):
            out["github"] = get_secret("AUTOJOB_GITHUB_TOKEN") or ""
        if has_secret("AUTOJOB_EMAIL_VERIFY_API_KEY"):
            out["email_verify"] = get_secret("AUTOJOB_EMAIL_VERIFY_API_KEY") or ""
    except Exception:
        pass
    try:
        from connections_store import get_connections_for_ui

        ev = get_connections_for_ui().get("email_verify") or {}
        out["verify_provider"] = str(ev.get("provider") or "hunter")
    except Exception:
        pass
    return out


def _load_job(job_id: str) -> dict[str, Any]:
    with store.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise ValueError(f"Job not found: {job_id}")
    job = dict(row)
    meta = {}
    raw = job.get("metadata_json") or "{}"
    try:
        import json

        meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        meta = {}
    job["metadata"] = meta if isinstance(meta, dict) else {}
    return job


def resolve_job_contact(
    job_id: str,
    *,
    use_serp: bool = True,
    use_github: bool = True,
    verify: bool = True,
) -> dict[str, Any]:
    """Run the waterfall and persist an auditable result for Prep UI."""
    store.init_db()
    job = _load_job(job_id)
    company = str(job.get("company") or "").strip() or "Unknown"
    title = str(job.get("title") or "").strip()
    location = str(job.get("location") or "").strip() or "Bangalore"
    jd = str(job.get("jd_text") or "")
    url = str(job.get("url") or "")
    secrets = _secrets()

    cr_store.clear_job_resolution(job_id)

    # ── Stage 1: domain ───────────────────────────────────────────────
    domain_info = resolve_company_domain(
        company,
        website=str(job.get("metadata", {}).get("website") or ""),
        apply_url=url,
        metadata=job.get("metadata"),
        use_autocomplete=True,
    )
    company_id = cr_store.upsert_company(
        company,
        email_domain=domain_info.get("email_domain") or "",
        website_domain=domain_info.get("website_domain") or "",
        mx_provider=domain_info.get("mx_provider") or "",
        is_catch_all=domain_info.get("is_catch_all"),
    )
    mx_provider = str(domain_info.get("mx_provider") or "unknown")
    is_catch_all = bool(domain_info.get("is_catch_all"))
    email_domain = str(domain_info.get("email_domain") or "")

    evidence_buf: list[dict[str, Any]] = [
        {"kind": "domain", "value": email_domain, "url": "", "source": domain_info.get("domain_source")},
        {"kind": "mx", "value": mx_provider, "url": ""},
    ]
    evidence_buf.extend(apply_url_forensics(url))

    # ── Stage 2: people ───────────────────────────────────────────────
    people: list[dict[str, Any]] = []
    people.extend(mine_ats_people(job))
    people.extend(mine_jd_people(jd, url, company=company))

    if use_github and secrets.get("github") is not None:
        # Org member search is noisy without token; still try lightly
        gh_people = search_github_org_members(
            company, token=secrets.get("github") or "", limit=3
        )
        people.extend(gh_people)

    if use_serp and secrets.get("serper") and not any(
        p.get("source") in ("ats_field", "jd_email", "jd_regex") for p in people
    ):
        people.extend(
            title_ladder_people(
                company,
                location,
                title,
                api_key=secrets["serper"],
            )
        )

    people = rank_people(people)

    # Deduplicate by name/email
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in people:
        key = (
            (p.get("email") or "").lower()
            or (p.get("linkedin_url") or "").lower()
            or (p.get("full_name") or "").lower()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(p)
    people = unique[:8]

    # Known emails for pattern learning
    known_emails = [p["email"] for p in people if p.get("email")]
    if job.get("company_email"):
        known_emails.append(str(job["company_email"]))
    known_emails = [e.lower() for e in known_emails if e and "@" in e]
    names = [p["full_name"] for p in people if p.get("full_name")]

    # GitHub emails for people with login
    for p in people:
        if p.get("github_login") and use_github:
            for ge in github_emails_for_login(
                p["github_login"], token=secrets.get("github") or ""
            )[:2]:
                if ge not in known_emails:
                    known_emails.append(ge)
                if not p.get("email") and email_domain and ge.endswith("@" + email_domain):
                    p["email"] = ge
                    p["discovery_conf"] = max(float(p.get("discovery_conf") or 0), 0.8)

    pairs = pairs_from_known_emails(known_emails, names)
    pattern, pat_conf, samples = learn_pattern(pairs)
    if not pattern:
        pattern, pat_conf, samples = "{first}.{last}", 0.4, 0
    cr_store.save_pattern(
        company_id,
        pattern,
        confidence=pat_conf,
        sample_count=samples,
        source_list="jd,github" if samples else "default",
    )

    # ── Stages 4–6: emails + verify + score ────────────────────────────
    email_rows: list[dict[str, Any]] = []
    person_ids: list[int] = []

    for p in people:
        first = p.get("first_name") or _split_name(p.get("full_name") or "")[0]
        last = p.get("last_name") or _split_name(p.get("full_name") or "")[1]
        pid = cr_store.insert_person(
            company_id=company_id,
            job_id=job_id,
            full_name=str(p.get("full_name") or ""),
            first_name=first,
            last_name=last,
            title=str(p.get("title") or ""),
            seniority_rank=p.get("seniority_rank"),
            linkedin_url=str(p.get("linkedin_url") or ""),
            github_login=str(p.get("github_login") or ""),
            source=str(p.get("source") or ""),
            discovery_conf=float(p.get("discovery_conf") or 0),
        )
        person_ids.append(pid)
        cr_store.add_evidence(
            "person",
            pid,
            "source",
            value=str(p.get("source") or ""),
            url=str(p.get("linkedin_url") or ""),
        )

        candidates: list[tuple[str, str, float]] = []
        if p.get("email"):
            candidates.append((str(p["email"]).lower(), "ats_or_jd", 0.9))
        if email_domain and first:
            candidates.extend(
                generate_emails(first, last, email_domain, pattern=pattern, limit=4)
            )
            # Also reuse existing permute helper for coverage
            for s in suggest_for_contact(
                str(p.get("full_name") or ""),
                company,
                domain=email_domain,
                verify=False,
            )[:3]:
                em = str(s.get("email") or "").lower()
                if em and em not in {c[0] for c in candidates}:
                    candidates.append((em, "permute", 0.45))

        # Dedupe candidates
        seen_e: set[str] = set()
        for email, method, pconf in candidates:
            if not email or "@" not in email or email in seen_e:
                continue
            seen_e.add(email)
            vstatus = "unverified"
            vsource = ""
            if verify and secrets.get("email_verify"):
                raw = verify_email(
                    email,
                    api_key=secrets["email_verify"],
                    provider=secrets.get("verify_provider") or "hunter",
                )
                vstatus = map_verify_status(
                    str(raw.get("status") or ""),
                    mx_provider=mx_provider,
                    is_catch_all=is_catch_all,
                )
                vsource = str(raw.get("provider") or "hunter")
            elif is_catch_all:
                vstatus = "accept_all"
                vsource = "mx_fingerprint"

            score = final_score(
                pconf,
                vstatus,
                source_count=1 + (1 if p.get("linkedin_url") else 0) + (1 if samples else 0),
                discovery_conf=float(p.get("discovery_conf") or 0),
            )
            decision = decision_for(
                score,
                verify_status=vstatus,
                is_catch_all=is_catch_all,
                mx_provider=mx_provider,
            )
            eid = cr_store.insert_email(
                person_id=pid,
                job_id=job_id,
                email=email,
                gen_method=method,
                pattern_conf=pconf,
                verify_status=vstatus,
                verify_source=vsource,
                source_count=1,
                final_score=score,
                decision=decision,
            )
            email_rows.append(
                {
                    "email_id": eid,
                    "person_id": pid,
                    "email": email,
                    "gen_method": method,
                    "verify_status": vstatus,
                    "final_score": score,
                    "decision": decision,
                    "person_name": p.get("full_name"),
                    "linkedin_url": p.get("linkedin_url"),
                }
            )

    email_rows.sort(key=lambda r: float(r.get("final_score") or 0), reverse=True)
    best_email = email_rows[0] if email_rows else None
    best_person_id = int(best_email["person_id"]) if best_email else (person_ids[0] if person_ids else None)
    best_email_id = int(best_email["email_id"]) if best_email else None

    status = "resolved" if people else "no_person"
    if people and not email_rows:
        status = "person_no_email"
    if not email_domain:
        status = "no_domain" if not people else status

    summary = {
        "company": company,
        "role": title,
        "domain": domain_info,
        "pattern": {"pattern": pattern, "confidence": pat_conf, "samples": samples},
        "people_count": len(people),
        "emails_count": len(email_rows),
        "best": best_email,
        "linkedin_searches": linkedin_search_urls(company, location),
        "notes": _notes(status, mx_provider, is_catch_all, secrets),
        "evidence": evidence_buf,
    }
    cr_store.save_job_resolution(
        job_id,
        company_id=company_id,
        status=status,
        best_person_id=best_person_id,
        best_email_id=best_email_id,
        summary=summary,
    )
    store.audit(
        "contact_resolved",
        "job",
        job_id,
        {"status": status, "people": len(people), "emails": len(email_rows)},
    )

    result = cr_store.get_job_resolution(job_id) or {}
    result["summary"] = summary
    return result


def _notes(
    status: str,
    mx_provider: str,
    is_catch_all: bool,
    secrets: dict[str, str],
) -> list[str]:
    notes: list[str] = [
        "Never auto-sent — copy into email or LinkedIn yourself.",
    ]
    if status == "no_person":
        notes.append(
            "No named contact found. Open the LinkedIn searches, or add a Serper key on Connections for SERP discovery."
        )
    if not secrets.get("serper"):
        notes.append("Optional: add a Serper API key on Connections to unlock title-ladder SERP discovery.")
    if not secrets.get("email_verify"):
        notes.append("Optional: add Hunter/NeverBounce on Connections to verify candidates.")
    if is_catch_all or mx_provider in ("proofpoint", "mimecast"):
        notes.append(
            f"Mail gateway looks like {mx_provider or 'SEG'} (often accept-all). Prefer LinkedIn + portal; only email at high confidence."
        )
    return notes
