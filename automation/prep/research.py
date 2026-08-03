"""Web research for company + role interview intel.

Uses free DuckDuckGo by default (same path as Level-3 discovery), then optional
Google CSE / SerpAPI if configured. Serper is optional last-resort only — never
required.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse
from html import unescape

import requests

logger = logging.getLogger(__name__)

# Real write-ups introduce questions in ways the first version did not match:
# "First round: How would you...", '2. What is your approach...', a bullet, or a
# quote. Requiring a preceding . ! ? or newline found zero questions in pages
# that plainly contained them.
_QUESTION_RE = re.compile(
    r"(?:^|[.!?:;]\s+|[\n\r•\-*\u2013\u2014\u201c\u201d\"']\s*|\d+[.)]\s+)"
    r"((?:how|what|why|when|where|which|who|tell me|describe|walk me|walk us|"
    r"explain|design|give me|share|have you|can you|could you|would you|do you|"
    r"did you|if you)[^?]{12,180}\?)",
    re.I,
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; shortlistr/1.0; interview-prep-research)",
}


def _serper_key() -> str:
    try:
        from secrets_store import get_secret, has_secret

        if has_secret("SHORTLISTR_SERPER_API_KEY"):
            return get_secret("SHORTLISTR_SERPER_API_KEY") or ""
    except Exception:
        pass
    return ""


def _env(key: str) -> str:
    import os

    return (os.environ.get(key) or "").strip()


def _normalize_hits(raw: list[dict], query: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw or []:
        title = str(item.get("title") or "").strip()
        link = str(item.get("url") or item.get("link") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not snippet and title:
            snippet = title
        if not title and not snippet:
            continue
        out.append({"title": title, "link": link, "snippet": snippet, "query": query})
    return out


# DuckDuckGo answers a bot challenge in about 12 seconds. Building one prep
# bundle makes six searches, so a backend that is guaranteed to fail cost 72 of
# the 76 seconds — the whole wait, for nothing. Once it challenges us, stop
# asking for a while: the answer will not change within one prep run, and the
# document already explains that the reading list needs a search key.
_DDG_BLOCKED_UNTIL = 0.0
_DDG_COOLDOWN_SECONDS = 900


def _ddg_blocked() -> bool:
    return time.monotonic() < _DDG_BLOCKED_UNTIL


def _mark_ddg_blocked() -> None:
    global _DDG_BLOCKED_UNTIL
    _DDG_BLOCKED_UNTIL = time.monotonic() + _DDG_COOLDOWN_SECONDS


def _duckduckgo_organic(query: str, num: int = 6) -> list[dict[str, str]]:
    """Free HTML search — captures titles + snippets when present."""
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "b": ""},
        headers={**_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=12,
    )
    if resp.status_code == 202 or (
        "anomaly" in resp.text.lower() and 'class="result__a"' not in resp.text
    ):
        raise RuntimeError(f"DuckDuckGo challenged (HTTP {resp.status_code})")
    resp.raise_for_status()
    html = resp.text
    results: list[dict[str, str]] = []
    # Each result block: link + optional snippet
    blocks = re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=class="result__a"|$)',
        html,
        re.I | re.S,
    )
    for href, raw_title, rest in blocks:
        title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            href = unescape(qs.get("uddg", [href])[0])
        snip_m = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)', rest, re.I | re.S)
        snippet = ""
        if snip_m:
            snippet = unescape(re.sub(r"<[^>]+>", " ", snip_m.group(1)))
            snippet = re.sub(r"\s+", " ", snippet).strip()
        if not snippet:
            snippet = title
        if title or snippet:
            results.append(
                {"title": title, "link": href, "snippet": snippet, "query": query}
            )
        if len(results) >= num:
            break
    return results


def _serper_organic(query: str, *, api_key: str = "", num: int = 6) -> list[dict[str, str]]:
    key = api_key or _serper_key()
    if not key:
        return []
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query.strip(), "num": num},
        timeout=18,
    )
    if resp.status_code != 200:
        return []
    out: list[dict[str, str]] = []
    for item in (resp.json() or {}).get("organic") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if title or snippet:
            out.append({"title": title, "link": link, "snippet": snippet, "query": query})
    return out


def web_organic(query: str, *, num: int = 6) -> list[dict[str, str]]:
    """Search the web without requiring a paid Serper key.

    Order: DuckDuckGo (free) → Google CSE / SerpAPI if env keys exist → Serper
    only if a key is already saved.
    """
    q = (query or "").strip()
    if not q:
        return []

    # 1) A configured API first. DuckDuckGo now answers HTTP 202 (a bot
    # challenge) for these queries, so trying it first only added latency
    # before falling through to the backend that actually works.
    try:
        from processors.search_discovery import run_search_query, search_backend_available

        backend = search_backend_available()
        if backend in ("google_cse", "serpapi"):
            hits = _normalize_hits(run_search_query(q, backend=backend, num=num), q)
            if hits:
                return hits
    except Exception as exc:
        logger.debug("CSE/SerpAPI interview search failed: %s", exc)

    # 2) Free DuckDuckGo — skipped entirely while it is challenging us
    if not _ddg_blocked():
        try:
            hits = _duckduckgo_organic(q, num=num)
            if hits:
                return hits
        except Exception as exc:
            _mark_ddg_blocked()
            logger.debug("DDG interview search failed, backing off: %s", exc)

    # 3) Optional Serper (paid) — only if already configured
    try:
        hits = _serper_organic(q, num=num)
        if hits:
            return hits
    except Exception as exc:
        logger.debug("Serper interview search failed: %s", exc)

    return []


# Back-compat alias for older tests / callers
def serper_organic(query: str, *, api_key: str = "", num: int = 8) -> list[dict[str, str]]:
    if api_key:
        try:
            return _serper_organic(query, api_key=api_key, num=num)
        except Exception:
            return []
    return web_organic(query, num=num)


def _extract_questions(text: str, *, limit: int = 12) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    blob = text or ""
    for m in _QUESTION_RE.finditer(blob):
        q = re.sub(r"\s+", " ", m.group(1)).strip()
        key = q.lower()
        if key in seen or len(q) < 16:
            continue
        seen.add(key)
        found.append(q)
        if len(found) >= limit:
            break
    for m in re.finditer(r"(?:^|\n)\s*\d+[.)]\s*([^?\n]{12,180}\?)", blob):
        q = re.sub(r"\s+", " ", m.group(1)).strip()
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(q)
        if len(found) >= limit:
            break
    return found


def _process_bullets(results: list[dict[str, str]], *, limit: int = 6) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for r in results:
        snip = re.sub(r"\s+", " ", (r.get("snippet") or r.get("title") or "").strip())
        if len(snip) < 28:
            continue
        key = snip[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        source = (r.get("title") or "Source").strip()
        bullets.append(f"{snip} _(via {source})_")
        if len(bullets) >= limit:
            break
    return bullets



# ── reading the pages, not just the snippets ─────────────────────────────────
#
# A search snippet is ~160 characters and almost never contains a whole
# question, so extracting from snippets alone yielded nothing usable. The
# questions people were actually asked live in the body of Reddit threads,
# blog write-ups and GitHub prep repos, so those pages have to be read.
#
# Glassdoor and Blind are the obvious sources and are deliberately not fetched:
# both disallow it in robots.txt and put the content behind a login. An MIT
# licence is not permission to break a site's terms, so those results are
# dropped rather than worked around.

_ROBOTS_CACHE: dict[str, Any] = {}
_FETCH_TIMEOUT = 8
_MAX_PAGES = 4

# Hosts that never carry candidate-reported questions, or that forbid fetching.
_SKIP_HOSTS = (
    "glassdoor.", "teamblind.", "linkedin.com", "indeed.", "facebook.",
    "twitter.", "x.com", "youtube.", "instagram.",
)


def _robots_allows(url: str) -> bool:
    """Honour robots.txt. Unreachable robots.txt means do not fetch."""
    import urllib.robotparser as robotparser

    try:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
    except Exception:
        return False

    if origin not in _ROBOTS_CACHE:
        parser = robotparser.RobotFileParser()
        parser.set_url(origin + "/robots.txt")
        try:
            parser.read()
        except Exception:
            # No robots.txt we can read — treat as disallowed rather than
            # assuming permission.
            _ROBOTS_CACHE[origin] = None
        else:
            _ROBOTS_CACHE[origin] = parser

    parser = _ROBOTS_CACHE.get(origin)
    if parser is None:
        return False
    try:
        return bool(parser.can_fetch(_HEADERS["User-Agent"], url))
    except Exception:
        return False


def _page_text(url: str) -> str:
    """Fetch a result page and return its visible text, or ''."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_FETCH_TIMEOUT)
        if resp.status_code != 200:
            return ""
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype and "text" not in ctype:
            return ""
        body = resp.text[:400_000]
    except Exception as exc:
        logger.debug("prep research fetch failed for %s: %s", url, exc)
        return ""

    body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.I | re.S)
    body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.I | re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", unescape(body)).strip()


def questions_from_pages(hits: list[dict[str, str]], *, limit: int = 12) -> tuple[list[str], list[str]]:
    """Read the top allowed result pages and pull real questions out of them.

    Returns ``(questions, sources)`` — sources are the hosts the questions came
    from, so the guide can say where each set was found instead of implying the
    company published them.
    """
    found: list[str] = []
    sources: list[str] = []
    fetched = 0

    for hit in hits:
        if fetched >= _MAX_PAGES or len(found) >= limit:
            break
        url = (hit.get("link") or "").strip()
        if not url.startswith("http"):
            continue
        host = urlparse(url).netloc.lower()
        if any(bad in host for bad in _SKIP_HOSTS):
            continue
        if not _robots_allows(url):
            logger.debug("prep research: robots.txt disallows %s", url)
            continue

        text = _page_text(url)
        fetched += 1
        time.sleep(0.6)          # be a polite client
        if not text:
            continue
        qs = _extract_questions(text, limit=limit)
        new = [q for q in qs if q.lower() not in {f.lower() for f in found}]
        if new:
            found.extend(new)
            sources.append(host)

    return found[:limit], sources


def research_interview(
    company: str,
    role: str,
    *,
    jd: str = "",
    api_key: str | None = None,
) -> dict[str, Any]:
    """Research probable interview process + role questions for company/role.

    ``api_key`` is ignored for the free path (kept for call-site compatibility).
    Always safe to call — empty lists when all backends fail.
    """
    company = (company or "").strip() or "Company"
    role = (role or "").strip() or "Engineer"
    notes: list[str] = []
    _ = api_key  # optional Serper override unused; free search is preferred

    # Keep query count small — DDG rate-limits aggressive bursts.
    short_role = re.split(r"[|/–—-]", role)[0].strip() or role
    queries = [
        f'"{company}" interview process OR hiring process OR "interview rounds"',
        f'"{company}" "{short_role}" interview questions',
        f'"{company}" interview questions Glassdoor OR Blind',
    ]

    all_hits: list[dict[str, str]] = []
    seen_links: set[str] = set()
    backend_note = ""
    for q in queries:
        hits = web_organic(q, num=5)
        if hits and not backend_note:
            backend_note = "web search"
        for hit in hits:
            link = hit.get("link") or ""
            if link and link in seen_links:
                continue
            if link:
                seen_links.add(link)
            all_hits.append(hit)

    process = _process_bullets(
        [
            h
            for h in all_hits
            if re.search(
                r"interview|hiring|round|process|loop",
                f"{h.get('title', '')} {h.get('snippet', '')}",
                re.I,
            )
        ],
        limit=6,
    )
    # Real questions come from the body of the result pages. Snippets are ~160
    # characters and almost never contain a whole question, which is why
    # snippet-only extraction returned nothing usable.
    page_questions, page_sources = questions_from_pages(all_hits, limit=14)

    question_blob = "\n".join(
        f"{h.get('title', '')}. {h.get('snippet', '')}" for h in all_hits
    )
    if jd:
        question_blob += "\n" + jd[:2500]
    snippet_questions = _extract_questions(question_blob, limit=14)

    questions = list(page_questions)
    for q in snippet_questions:
        if q.lower() not in {x.lower() for x in questions}:
            questions.append(q)

    role_bits = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", short_role)][:4]
    ranked: list[str] = []
    rest: list[str] = []
    for q in questions:
        ql = q.lower()
        if company.lower() in ql or any(b in ql for b in role_bits):
            ranked.append(q)
        else:
            rest.append(q)
    questions = (ranked + rest)[:10]

    sources = []
    for h in all_hits[:8]:
        if h.get("link"):
            sources.append({"title": h.get("title") or h["link"], "url": h["link"]})

    mode = "researched" if (process or questions or sources) else "fallback"
    if mode == "fallback":
        notes.append(
            f"No public interview reports found for {company}. The questions "
            "below were written from this job description, not from what "
            "candidates reported being asked."
        )
    elif page_sources:
        notes.append(
            f"Questions read via web search from "
            f"{', '.join(sorted(set(page_sources))[:4])} for {company} · {role}. "
            "Reported by candidates, not published by the company — verify; "
            "processes change."
        )
    elif questions:
        notes.append(
            f"Questions taken from web search result summaries for {company} · "
            f"{role}. Reported by candidates, not published by the company — "
            "verify; processes change."
        )
    else:
        notes.append(
            f"Web search found interview process notes for {company} but no "
            "reported questions. The questions below were written from this "
            "job description."
        )

    if page_questions:
        question_origin = "pages"
    elif questions:
        question_origin = "snippets"
    else:
        question_origin = "none"

    return {
        "mode": mode,
        "question_origin": question_origin,
        "company": company,
        "role": role,
        "process": process,
        "questions": questions,
        "sources": sources,
        "notes": notes,
    }


# Hosts that publish teaching material rather than listings or SEO filler.
_LEARNING_HOSTS = (
    "github.com", "github.io", "sre.google", "kubernetes.io", "prometheus.io",
    "grafana.com", "opentelemetry.io", "aws.amazon.com", "cloud.google.com",
    "learn.microsoft.com", "docs.docker.com", "terraform.io", "hashicorp.com",
    "martinfowler.com", "highscalability.com", "arxiv.org", "coursera.org",
    "edx.org", "udacity.com", "pluralsight.com", "oreilly.com", "manning.com",
    "interviewing.io", "educative.io", "systemdesign", "bigmachine",
)

# Listing and aggregator pages — a job ad is not study material.
_NOT_LEARNING = (
    "indeed.", "naukri.", "glassdoor.", "linkedin.com/jobs", "ziprecruiter.",
    "monster.", "simplyhired.", "/jobs/", "job-openings", "apply",
)


def _looks_like_learning(hit: dict[str, str]) -> bool:
    link = (hit.get("link") or "").lower()
    if not link.startswith("http"):
        return False
    if any(bad in link for bad in _NOT_LEARNING):
        return False
    return any(host in link for host in _LEARNING_HOSTS)


def research_learning_resources(
    role: str, *, jd: str = "", skills: list[str] | None = None, max_items: int = 8
) -> dict[str, Any]:
    """Study material for this role, plus an ordered path through it.

    Deliberately not a generic "top 10 SRE links" list: the queries are built
    from the skills the *job description* actually asks for, so the reading is
    about the gap between this role and the last one rather than the subject in
    general.

    Only hosts that teach are kept — a job board answering "site reliability
    engineer learning path" is another advert, not a resource. Empty is an
    honest answer when the web gives nothing; a fabricated reading list is worse
    than none.
    """
    short_role = re.split(r"[|/–—-]", role or "")[0].strip() or "Engineer"
    topics = [s for s in (skills or []) if s and len(s) > 2][:3]

    queries = [f"{short_role} interview preparation guide"]
    queries += [f"{t} tutorial guide documentation" for t in topics[:2]]

    resources: list[dict[str, str]] = []
    seen: set[str] = set()
    for q in queries:
        try:
            hits = web_organic(q, num=6)
        except Exception:
            # A dead search backend must not take prep generation down with it;
            # the path below is derived from the JD and still worth printing.
            hits = []
        for hit in hits:
            link = hit.get("link") or ""
            if not link or link in seen or not _looks_like_learning(hit):
                continue
            seen.add(link)
            resources.append({
                "title": (hit.get("title") or link)[:120],
                "link": link,
                "snippet": (hit.get("snippet") or "")[:200],
                "topic": q,
            })
            if len(resources) >= max_items:
                break
        if len(resources) >= max_items:
            break

    # The path comes from the JD, not the search results — it is what to study,
    # in order, whether or not the web turned anything up.
    path: list[str] = []
    if topics:
        path.append(f"Refresh the fundamentals this JD leans on: {', '.join(topics)}.")
    path.append(f"Re-read the JD and write one concrete story per requirement ({short_role}).")
    path.append("Run the system-design question below end to end, out loud, on a whiteboard.")
    path.append("Prepare your own questions on on-call load, error budgets and team shape.")

    return {"resources": resources, "path": path, "topics": topics}


def draft_star_answers(
    questions: list[str],
    *,
    company: str,
    role: str,
    cv_excerpt: str,
    jd: str = "",
) -> dict[str, str]:
    """Optional LLM STAR sketches keyed by question. Empty dict on failure."""
    if not questions:
        return {}
    try:
        from llm import get_llm

        llm = get_llm()
    except Exception:
        llm = None
    if not llm:
        return {}

    q_block = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions[:8]))
    prompt = (
        f"You are helping a candidate prep for interviews at {company} for {role}.\n"
        "For each question, draft a concise STAR+R answer skeleton (4–8 lines) "
        "grounded ONLY in the résumé excerpt. Do not invent employers or metrics.\n"
        "If the résumé lacks evidence, write: 'Need personal story — fill from your experience.'\n\n"
        f"RÉSUMÉ EXCERPT:\n{(cv_excerpt or '')[:3500]}\n\n"
        f"JD HINTS:\n{(jd or '')[:1200]}\n\n"
        f"QUESTIONS:\n{q_block}\n\n"
        "Format exactly:\n"
        "Q1:\n<answer>\n\nQ2:\n<answer>\n"
    )
    try:
        raw = llm.complete(
            prompt,
            system=(
                "Interview coach. Ground answers in the résumé. Never fabricate employers, "
                "dates, or metrics. Keep each answer under 120 words."
            ),
            max_tokens=1800,
        )
    except Exception as exc:
        logger.debug("prep LLM answers failed: %s", exc)
        return {}

    out: dict[str, str] = {}
    parts = re.split(r"\nQ(\d+):\s*", raw or "")
    i = 1
    while i + 1 < len(parts):
        try:
            idx = int(parts[i]) - 1
        except ValueError:
            i += 2
            continue
        body = (parts[i + 1] or "").strip()
        if 0 <= idx < len(questions) and body:
            out[questions[idx]] = body
        i += 2
    return out
