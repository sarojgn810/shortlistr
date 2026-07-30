"""
shortlistr — Configuration loader

Reads from {repo}/config/profile.yml (shared with the AI evaluation layer).
Run setup:  cd automation && python setup.py
"""

import os
import re

# Load .env from repo root and automation/ (setup.py may write either location).
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in (os.path.join("automation", ".env"), ".env"):
            path = os.path.join(root, rel)
            if os.path.isfile(path):
                load_dotenv(path, override=False)
    except ImportError:
        pass


_load_dotenv()

# ── Secrets (OS keychain, with .env fallback) ──────────────────────────────────
# One-time migration of any plaintext secrets in .env into the keychain, then read
# everything through secrets_store. Falls back to env if keyring is unavailable.
try:
    from secrets_store import get_secret as _secret
    from secrets_store import migrate_env_to_keyring as _migrate_secrets

    _r = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _rel in (os.path.join("automation", ".env"), ".env"):
        try:
            _migrate_secrets(os.path.join(_r, _rel))
        except Exception:
            pass
except Exception:  # secrets_store import failure — degrade to env reads
    def _secret(name: str, default: str = "") -> str:
        return os.environ.get(name, default)

# ── Roots ─────────────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
SHORTLISTR_ROOT = os.path.dirname(BASE_DIR)
PROFILE_PATH = os.path.join(SHORTLISTR_ROOT, "config", "profile.yml")
LEGACY_PROFILE_PATH = os.path.join(BASE_DIR, "config", "profile.yml")


def _load_profile() -> dict:
    """Load config/profile.yml. Prefer repo root; fall back to legacy automation/config/."""
    for path in (PROFILE_PATH, LEGACY_PROFILE_PATH):
        if not os.path.exists(path):
            continue
        try:
            import yaml  # type: ignore
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            return _minimal_yaml_load(path)
        except Exception:
            return {}
    return {}


def _minimal_yaml_load(path: str) -> dict:
    root: dict = {}
    stack: list = [(-1, root)]
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            content = line.strip()
            while len(stack) > 1 and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1]
            if ":" in content:
                key, _, val = content.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if "#" in val:
                    val = val[: val.index("#")].strip()
                if val == "" or val in ("~", "null"):
                    parent[key] = {}
                    stack.append((indent, parent[key]))
                else:
                    parent[key] = val
    return root


_PROFILE = _load_profile()


def _p(*keys, default=""):
    node = _PROFILE
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
    return node if node != "" else default


def _as_list(node) -> list:
    if isinstance(node, list):
        return [str(x) for x in node if x]
    return []


# Boards spell the same role several ways ("MLOps" / "ML Ops" / "Machine
# Learning Operations"). The discovery filter matches titles literally, so a
# profile that lists one spelling silently drops the others. Each family lists
# every spelling that means the same job — keep these tight, since anything
# broader here (e.g. bare "machine learning") floods the inbox with adjacent
# research roles.
_TITLE_FAMILIES: dict[str, tuple[str, ...]] = {
    "sre": ("site reliability", "sre"),
    "mlops": ("mlops", "ml ops", "machine learning operations"),
    "aiops": ("aiops", "ai ops", "ai operations"),
    "devops": ("devops", "dev ops"),
    "platform": ("platform engineer", "platform engineering"),
    "infrastructure": ("infrastructure engineer", "infra engineer"),
    "cloud": ("cloud engineer", "cloud infrastructure"),
}

# Words that describe rank rather than the job itself — stripped when grouping
# titles into families so five seniority variants of one role don't eat every
# search slot.
_TITLE_NOISE = {
    "senior", "sr", "staff", "principal", "lead", "junior", "jr", "associate",
    "chief", "head", "of", "engineer", "engineering", "developer", "manager",
    "specialist", "consultant", "architect", "i", "ii", "iii", "1", "2", "3",
}


def _phrase_in(phrase: str, text: str) -> bool:
    """Word-boundary match for short phrases, substring for longer ones."""
    if len(phrase) <= 4:
        return bool(re.search(r"\b" + re.escape(phrase) + r"\b", text))
    return phrase in text


def title_family(title: str) -> str:
    """Group a title with its synonyms ('Senior SRE' and 'SRE II' → 'sre')."""
    t = re.sub(r"[^a-z0-9 ]+", " ", str(title).lower()).strip()
    for family, spellings in _TITLE_FAMILIES.items():
        if any(_phrase_in(s, t) for s in spellings):
            return family
    return " ".join(w for w in t.split() if w not in _TITLE_NOISE) or t


def _alias_spellings(titles: list[str]) -> list[str]:
    """Alternate spellings of the families the given titles belong to.

    The bare form is kept even when a listed title already contains it
    ("AIOps Engineer" still yields "aiops"), because the discovery filter
    matches whole keywords — without it, "AIOps Specialist" is dropped.
    """
    out: list[str] = []
    have = {str(t).lower() for t in titles}
    for family in {title_family(t) for t in titles}:
        for spelling in _TITLE_FAMILIES.get(family, ()):
            if spelling not in have:
                out.append(spelling)
                have.add(spelling)
    return out


def _expand_titles(items: list) -> list[str]:
    """Split comma-separated title strings into individual keywords.

    Alternate spellings of each role family are appended so the discovery
    filter recognises "Senior ML Ops Engineer" for a profile that wrote
    "MLOps Engineer". Profile spellings stay first — sources use that order
    when choosing which terms to actually search.
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        for part in re.split(r"[,;|]", str(item)):
            part = part.strip()
            if part and part.lower() not in seen:
                out.append(part)
                seen.add(part.lower())
    return out + _alias_spellings(out)


def search_titles(limit: int = 5) -> list[str]:
    """Query terms covering every role family the profile targets.

    Sources can only afford a handful of searches per scan, and
    `SEARCH_KEYWORDS[:limit]` spends them all on seniority variants of the
    first role — the reason an SRE-plus-MLOps profile only ever searched SRE.
    """
    by_family: dict[str, list[str]] = {}
    for kw in SEARCH_KEYWORDS or []:
        term = str(kw).strip()
        if len(term) < 3:
            continue
        by_family.setdefault(title_family(term), []).append(term)

    ordered: list[str] = []
    for rank in range(max((len(v) for v in by_family.values()), default=0)):
        for terms in by_family.values():
            if rank < len(terms) and len(ordered) < limit:
                ordered.append(terms[rank])
    return ordered[:limit]


def _parse_filters() -> dict:
    """Extract filter settings from profile.yml."""
    f = _PROFILE.get("filters") if isinstance(_PROFILE.get("filters"), dict) else {}

    loc_block = f.get("location") if isinstance(f.get("location"), dict) else {}
    comp_block = f.get("compensation") if isinstance(f.get("compensation"), dict) else {}

    if loc_block or comp_block or f.get("titles"):
        min_inr = int(comp_block.get("min_inr_lpa", f.get("min_salary_inr_lpa", 0)) or 0)
        min_usd = int(comp_block.get("min_usd", f.get("min_salary_usd", 0)) or 0)
        titles = _expand_titles(_as_list(f.get("titles")) or _as_list(f.get("target_titles")))
        deal_breakers = _as_list(f.get("deal_breakers"))
    else:
        min_inr = int(f.get("min_salary_inr_lpa", 0) or 0)
        min_usd = int(f.get("min_salary_usd", 0) or 0)
        titles = _expand_titles(_as_list(f.get("target_titles")))
        deal_breakers = _as_list(f.get("deal_breakers"))

    # Fall back to target_roles from legacy AI profile
    if not titles:
        tr = _PROFILE.get("target_roles")
        if isinstance(tr, dict):
            titles = _expand_titles(_as_list(tr.get("primary")))
        elif isinstance(tr, list):
            titles = _expand_titles(tr)

    return {
        "min_salary_inr_lpa": min_inr,
        "min_salary_usd": min_usd,
        "target_titles": titles,
        "deal_breakers": deal_breakers,
    }


_FILTERS = _parse_filters()

# ── Candidate ─────────────────────────────────────────────────────────────────

def _resolve_resume_path() -> str:
    raw = _p("files", "resume_pdf", default="")
    candidates: list[str] = []
    if raw:
        candidates.append(
            raw if os.path.isabs(raw) else os.path.join(SHORTLISTR_ROOT, raw)
        )
    candidates.extend([
        os.path.join(SHORTLISTR_ROOT, "resume.pdf"),
        os.path.join(BASE_DIR, "user", "resume.pdf"),
    ])
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[0] if candidates else os.path.join(SHORTLISTR_ROOT, "resume.pdf")


# ── Application answers (apply-assist fills ATS custom questions) ───────────────
_APPLICATION_KEYS = (
    "website",
    "notice_period",
    "current_ctc",
    "expected_ctc",
    "how_heard",
    "work_authorization",
    "preferred_name",
    "cover_letter_snippet",
    "willing_to_relocate",
)


def _application_from_profile(data: dict | None = None) -> dict[str, str]:
    src = data if isinstance(data, dict) else _PROFILE
    app = src.get("application") if isinstance(src.get("application"), dict) else {}
    return {k: str(app.get(k, "") or "") for k in _APPLICATION_KEYS}


def _candidate_from_profile(data: dict | None = None) -> dict:
    src = data if isinstance(data, dict) else _PROFILE
    cand = src.get("candidate") if isinstance(src.get("candidate"), dict) else {}
    if not cand and src.get("full_name"):
        cand = {
            "name": src.get("full_name", ""),
            "email": src.get("email", ""),
            "phone": src.get("phone", ""),
            "location": src.get("location", ""),
            "linkedin": src.get("linkedin", ""),
            "github": src.get("github", ""),
            "years_exp": src.get("years_exp", 0),
        }
    return {
        "name": cand.get("name") or cand.get("full_name") or "",
        "email": cand.get("email", ""),
        "phone": cand.get("phone", ""),
        "location": cand.get("location", ""),
        "linkedin": cand.get("linkedin", ""),
        "github": cand.get("github", ""),
        "years_exp": int(cand.get("years_exp", 0) or 0),
        "resume_path": _resolve_resume_path(),
    }


CANDIDATE = _candidate_from_profile()
APPLICATION = _application_from_profile()

# ── Gmail SMTP ────────────────────────────────────────────────────────────────

EMAIL_CONFIG = {
    "smtp_host":    _p("email", "smtp_host", default="smtp.gmail.com"),
    "smtp_port":    int(_p("email", "smtp_port", default=587) or 587),
    "email":        _p("email", "sender", default=CANDIDATE.get("email", "")),
    "app_password": _secret("GMAIL_APP_PASSWORD") or _secret("SHORTLISTR_EMAIL_PASSWORD"),
}

# ── Search / location (from unified filters) ───────────────────────────────────

# Fallback search terms when the profile has no target_titles yet — deliberately
# broad and field-neutral (not SRE-specific), so an untargeted first scan isn't biased.
_DEFAULT_SEARCH_KEYWORDS = [
    "software engineer", "data analyst", "product manager",
    "project manager", "business analyst",
]

SEARCH_KEYWORDS = _FILTERS["target_titles"] or list(_DEFAULT_SEARCH_KEYWORDS)

_REMOTE_TERMS = {"remote", "anywhere", "worldwide", "global", "work from home", "wfh"}

# City names on Indian boards often differ from what users type in the profile
# (Bangalore vs Bengaluru). Expand at build time so every consumer of
# LOCATION_KEYWORDS — discovery filter, Naukri query, fit scorer — agrees.
_LOCATION_ALIASES: dict[str, tuple[str, ...]] = {
    "bangalore": ("bengaluru", "blr"),
    "bengaluru": ("bangalore", "blr"),
    "mumbai": ("bombay",),
    "bombay": ("mumbai",),
    "delhi": ("new delhi", "ncr", "gurgaon", "gurugram", "noida"),
    "gurgaon": ("gurugram", "delhi", "ncr"),
    "gurugram": ("gurgaon", "delhi", "ncr"),
    "hyderabad": ("hyd",),
    "chennai": ("madras",),
    "madras": ("chennai",),
    "kolkata": ("calcutta",),
    "calcutta": ("kolkata",),
    "pune": ("pnq",),
}


# Spelling variants of one city — used to avoid paying for the same search
# twice ("Bangalore" and "Bengaluru" are one query). Metro adjacency from
# _LOCATION_ALIASES (Delhi ⊃ Noida) is deliberately not collapsed here: those
# are different cities a user may want searched separately.
_CITY_SPELLINGS: tuple[frozenset[str], ...] = (
    frozenset({"bangalore", "bengaluru", "blr"}),
    frozenset({"mumbai", "bombay"}),
    frozenset({"delhi", "new delhi"}),
    frozenset({"gurgaon", "gurugram"}),
    frozenset({"hyderabad", "hyd"}),
    frozenset({"chennai", "madras"}),
    frozenset({"kolkata", "calcutta"}),
    frozenset({"pune", "pnq"}),
)


def search_locations(limit: int = 3) -> list[str]:
    """City query terms, one per city, abbreviations only when nothing better."""
    keys = [
        str(loc).lower().strip()
        for loc in LOCATION_KEYWORDS or []
        if str(loc).lower().strip() and str(loc).lower().strip() not in _REMOTE_TERMS
    ]
    out: list[str] = []
    claimed: set[frozenset[str]] = set()
    for key in sorted(keys, key=lambda k: (len(k) <= 3, keys.index(k))):
        group = next((g for g in _CITY_SPELLINGS if key in g), frozenset({key}))
        if group in claimed:
            continue
        claimed.add(group)
        out.append(key)
    return out[:limit]


def _expand_location_keywords(preferred: list[str]) -> list[str]:
    """Lowercase preferred locations and add known city aliases."""
    locs: list[str] = []
    seen: set[str] = set()
    for loc in preferred:
        key = str(loc).lower().strip()
        if not key or key in seen:
            continue
        locs.append(key)
        seen.add(key)
        for alias in _LOCATION_ALIASES.get(key, ()):
            if alias not in seen:
                locs.append(alias)
                seen.add(alias)
    return locs or ["remote"]


def _build_location_keywords() -> list[str]:
    """Derive LOCATION_KEYWORDS from preferred_locations in the profile."""
    f = _PROFILE.get("filters") if isinstance(_PROFILE.get("filters"), dict) else {}
    return _expand_location_keywords(_as_list(f.get("preferred_locations")))


LOCATION_KEYWORDS: list[str] = _build_location_keywords()

# REMOTE_STRICT is True when preferred_locations contains ONLY remote terms
# (no city names). If the user listed any city, allow non-remote jobs too.
REMOTE_STRICT = bool(LOCATION_KEYWORDS) and all(
    kw in _REMOTE_TERMS for kw in LOCATION_KEYWORDS
)
WANTS_REMOTE = any(kw in _REMOTE_TERMS for kw in LOCATION_KEYWORDS)
MIN_SALARY_INR_LPA = _FILTERS["min_salary_inr_lpa"]
MIN_SALARY_USD = _FILTERS["min_salary_usd"]
DEAL_BREAKERS = _FILTERS["deal_breakers"]
FILTER_DEAL_BREAKERS = DEAL_BREAKERS  # alias

_salary_unlisted = (
    _PROFILE.get("filters", {}).get("salary_unlisted")
    if isinstance(_PROFILE.get("filters"), dict)
    else "include"
)
if not _salary_unlisted and isinstance(_PROFILE.get("filters"), dict):
    comp = _PROFILE["filters"].get("compensation")
    if isinstance(comp, dict):
        _salary_unlisted = comp.get("unlisted", "include")
SALARY_UNLISTED = str(_salary_unlisted or "include").lower()

_scoring = _PROFILE.get("scoring") if isinstance(_PROFILE.get("scoring"), dict) else {}
MIN_FIT_SCORE = int(_scoring.get("min_fit_score", 40) or 40)

# ── Discovery (hybrid: aggregators + search + watchlist) ─────────────────────

_discovery = _PROFILE.get("discovery") if isinstance(_PROFILE.get("discovery"), dict) else {}
DISCOVERY_MODE = str(_discovery.get("mode", "hybrid")).lower()
DISCOVERY_SEARCH_QUERIES = str(_discovery.get("search_queries", "true")).lower() not in (
    "false", "0", "no", "off",
)
DISCOVERY_RESOLVE_PIPELINE = str(_discovery.get("resolve_pipeline_urls", "true")).lower() not in (
    "false", "0", "no", "off",
)

# ── Source registry (Phase 1.3) ───────────────────────────────────────────────

_sources = _PROFILE.get("sources") if isinstance(_PROFILE.get("sources"), dict) else {}
_default_enabled = ["watchlist_ats", "aggregators", "naukri", "search", "url_resolver", "gmail"]
SOURCE_ENABLED = _as_list(_sources.get("enabled")) or _default_enabled

_linkedin_src = _sources.get("linkedin") if isinstance(_sources.get("linkedin"), dict) else {}
LINKEDIN_SOURCE_CONFIG = {
    "enabled": str(_linkedin_src.get("enabled", "false")).lower() in ("true", "1", "yes"),
    "mode": str(_linkedin_src.get("mode", "scrape_only")),
    "easy_apply": str(_linkedin_src.get("easy_apply", "false")).lower() in ("true", "1", "yes"),
}

_apify_src = _sources.get("apify") if isinstance(_sources.get("apify"), dict) else {}
_apify_exp = _apify_src.get("experience")
_apify_boards = _as_list(_apify_src.get("boards")) or [
    "naukri",
    "linkedin",
    "indeed",
]
APIFY_SOURCE_CONFIG = {
    "boards": _apify_boards,
    "naukri_actor": str(_apify_src.get("naukri_actor") or "valig/naukri-jobs-scraper"),
    "linkedin_actor": str(_apify_src.get("linkedin_actor") or "valig/linkedin-jobs-scraper"),
    "indeed_actor": str(_apify_src.get("indeed_actor") or "valig/indeed-jobs-scraper"),
    "limit": int(_apify_src.get("limit") or 40),
    "timeout_secs": int(_apify_src.get("timeout_secs") or 180),
    "max_pairs": int(_apify_src["max_pairs"]) if _apify_src.get("max_pairs") not in (None, "") else None,
    "experience": int(_apify_exp) if _apify_exp not in (None, "") else None,
    "date_posted": str(_apify_src.get("date_posted") or "14"),
}

DISABLED_LEGACY_SOURCES = set(
    _as_list(_sources.get("disabled_legacy"))
    or [
        "workday",
        "smartrecruiters",
        "wellfound",
        "icims",
        "weworkremotely",
        "workingnomads",
        "nodesk",
        "jobspresso",
        "monster",
        "careerbuilder",
        "glassdoor",
        "simplyhired",
        "skipthedrive",
        "remoteco",
    ]
)

# Company ATS slugs: portals.yml only — see automation/portals_config.py

# ── Paths (repo root data/ — same as scan_portals and /shortlistr inbox) ─────────

LOG_DIR            = os.path.join(BASE_DIR, "logs")
DATA_DIR           = os.path.join(SHORTLISTR_ROOT, "data")
OUTPUT_DIR         = os.path.join(SHORTLISTR_ROOT, "output")
INTERVIEW_PREP_DIR = os.path.join(SHORTLISTR_ROOT, "interview-prep")
PREP_DIR           = INTERVIEW_PREP_DIR
PIPELINE_PATH      = os.path.join(DATA_DIR, "pipeline.md")
TRACKER_PATH       = os.path.join(DATA_DIR, "Job_Application_Tracker.xlsx")

_cv_raw = _p("files", "cv_markdown", default="cv.md")
CV_MD_PATH = _cv_raw if os.path.isabs(_cv_raw) else os.path.join(SHORTLISTR_ROOT, _cv_raw or "cv.md")

_llm = _PROFILE.get("llm") if isinstance(_PROFILE.get("llm"), dict) else {}
LLM_CONFIG = {
    "provider":   str(_llm.get("provider", "none")),
    "model":      str(_llm.get("model", "")),
    "api_key":    str(_llm.get("api_key", "")),
    "ollama_url": str(_llm.get("ollama_url", "http://localhost:11434")),
}

# ── Platform credentials ──────────────────────────────────────────────────────

LINKEDIN_CONFIG = {
    "email":    os.environ.get("LINKEDIN_EMAIL",    CANDIDATE.get("email", "")),
    "password": _secret("LINKEDIN_PASSWORD") or _secret("SHORTLISTR_LINKEDIN_PASSWORD"),
}

NAUKRI_CONFIG = {
    "email":    os.environ.get("NAUKRI_EMAIL", CANDIDATE.get("email", "")),
    "password": _secret("NAUKRI_PASSWORD") or _secret("SHORTLISTR_NAUKRI_PASSWORD"),
}

# ── Gmail OAuth ───────────────────────────────────────────────────────────────

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
GMAIL_TOKEN_PATH = os.path.join(BASE_DIR, "gmail_token.pickle")
GMAIL_CREDS_PATH = os.path.join(BASE_DIR, "gmail_credentials.json")

# ── MCP servers (outbound connectors) ──────────────────────────────────────────
# List of {name, transport, command/args | url, secret_ref?, side_effect_overrides?}.
_mcp_servers = _PROFILE.get("mcp_servers")
MCP_SERVERS = _mcp_servers if isinstance(_mcp_servers, list) else []


def reload_discovery_config() -> None:
    """Re-read profile.yml and update all discovery/filter globals so the next
    scan picks up profile changes without a restart.

    A missing or empty profile must reset to the field-neutral defaults — leaving
    the previous titles in place would keep a deleted profile's targeting alive
    for the rest of the process lifetime, and a first-run API that imported
    against a leftover profile would never fall back.
    """
    global SEARCH_KEYWORDS, LOCATION_KEYWORDS
    global REMOTE_STRICT, WANTS_REMOTE, MIN_SALARY_INR_LPA, MIN_SALARY_USD, DEAL_BREAKERS
    global CANDIDATE, APPLICATION, _PROFILE
    global LINKEDIN_CONFIG, NAUKRI_CONFIG, MCP_SERVERS, EMAIL_CONFIG
    import yaml

    profile_path = os.path.join(SHORTLISTR_ROOT, "config", "profile.yml")
    data: dict = {}
    if os.path.isfile(profile_path):
        try:
            with open(profile_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}

    _PROFILE = data

    filt = data.get("filters") if isinstance(data.get("filters"), dict) else {}

    titles = _as_list(filt.get("target_titles"))
    SEARCH_KEYWORDS = _expand_titles(titles) if titles else list(_DEFAULT_SEARCH_KEYWORDS)

    MIN_SALARY_INR_LPA = int(filt.get("min_salary_inr_lpa", 0) or 0)
    MIN_SALARY_USD = int(filt.get("min_salary_usd", 0) or 0)
    DEAL_BREAKERS = _as_list(filt.get("deal_breakers"))

    preferred = _as_list(filt.get("preferred_locations"))
    locs = _expand_location_keywords(preferred) if preferred else ["remote"]
    LOCATION_KEYWORDS = locs
    REMOTE_STRICT = bool(locs) and all(kw in _REMOTE_TERMS for kw in locs)
    WANTS_REMOTE = any(kw in _REMOTE_TERMS for kw in locs)

    # Apply-assist reads these at fill time — keep them live after profile save.
    CANDIDATE = _candidate_from_profile(data)
    APPLICATION = _application_from_profile(data)

    platforms = data.get("platforms") if isinstance(data.get("platforms"), dict) else {}
    li = platforms.get("linkedin") if isinstance(platforms.get("linkedin"), dict) else {}
    nk = platforms.get("naukri") if isinstance(platforms.get("naukri"), dict) else {}
    LINKEDIN_CONFIG = {
        "email": str(li.get("email") or CANDIDATE.get("email") or "").strip(),
        "password": _secret("LINKEDIN_PASSWORD") or _secret("SHORTLISTR_LINKEDIN_PASSWORD"),
    }
    NAUKRI_CONFIG = {
        "email": str(nk.get("email") or "").strip(),
        "password": _secret("NAUKRI_PASSWORD") or _secret("SHORTLISTR_NAUKRI_PASSWORD"),
    }
    mcp = data.get("mcp_servers")
    MCP_SERVERS = mcp if isinstance(mcp, list) else []

    email_cfg = data.get("email") if isinstance(data.get("email"), dict) else {}
    EMAIL_CONFIG = {
        "smtp_host": str(email_cfg.get("smtp_host") or "smtp.gmail.com"),
        "smtp_port": int(email_cfg.get("smtp_port") or 587),
        "email": str(email_cfg.get("sender") or CANDIDATE.get("email") or "").strip(),
        "app_password": _secret("GMAIL_APP_PASSWORD") or _secret("SHORTLISTR_EMAIL_PASSWORD"),
    }
