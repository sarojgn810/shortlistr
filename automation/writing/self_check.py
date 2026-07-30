"""Lightweight pass/fail checks for remaining generic AI-style patterns.

Used in tests and as a gate before accepting LLM polish.
Does not claim whether text was written by AI — only whether named
patterns remain.
"""

from __future__ import annotations

import re
from typing import Any

from writing import policy as P


def _hits(text: str) -> list[str]:
    low = (text or "").lower()
    found: list[str] = []
    for w in sorted(P.BANNED_WORDS):
        if re.search(rf"\b{re.escape(w)}\b", low):
            found.append(f"banned_word:{w}")
    for phrase in P.BANNED_PHRASES:
        if phrase.lower() in low:
            found.append(f"banned_phrase:{phrase}")
    for name, rx in (
        ("throat_clearing", P.THROAT_CLEARING),
        ("faux_insight", P.FAUX_INSIGHT),
        ("binary_contrast", P.BINARY_CONTRAST),
        ("colon_reveal", P.COLON_REVEAL),
        ("superficial_ing", P.SUPERFICIAL_ING),
        ("importance_puffery", P.IMPORTANCE_PUFFERY),
        ("weasel_attribution", P.WEASEL_ATTR),
        ("dramatic_fragment", P.DRAMATIC_FRAGMENT),
        ("rhetorical", P.RHETORICAL),
        ("summary_recap", P.SUMMARY_RECAP),
    ):
        if rx.search(text or ""):
            found.append(f"pattern:{name}")
    # Em-dash overuse in short copy
    if len(text or "") < 400 and len(P.EM_DASH_CLUSTER.findall(text or "")) >= 2:
        found.append("pattern:em_dash_overuse")
    return found


def self_check(text: str, *, strict: bool = False) -> dict[str, Any]:
    """Return {ok, hits, summary} for a draft.

    strict=True fails on any hit; default fails only when ≥2 hits or any pattern.
    """
    hits = _hits(text or "")
    if strict:
        ok = not hits
    else:
        pattern_hits = [h for h in hits if h.startswith("pattern:")]
        ok = len(hits) < 2 and not pattern_hits
    return {
        "ok": ok,
        "hits": hits,
        "summary": "pass" if ok else f"fail ({len(hits)} issues)",
    }


def invents_unsupported_tokens(
    draft: str,
    evidence: str,
    *,
    token_min_len: int = 5,
) -> list[str]:
    """Flag long alphabetic tokens in draft that never appear in evidence.

    Conservative: only tokens that look like proper-ish nouns / tech words
    (capitalized in draft OR all-caps acronyms) and are absent from evidence.
    Used to reject LinkedIn LLM polish that invents employers/skills.
    """
    if not draft:
        return []
    evid = (evidence or "").lower()
    invented: list[str] = []
    # Capitalized words (employers, tools) and ALLCAPS acronyms length≥3
    for m in re.finditer(r"\b([A-Z][a-zA-Z0-9+.#-]{2,}|[A-Z]{3,})\b", draft):
        tok = m.group(1)
        if tok.lower() in {
            "i", "i'm", "i've", "i'll", "a", "the", "and", "for", "with",
            "open", "core", "stack", "based", "full", "time", "remote",
        }:
            continue
        if len(tok) < token_min_len and not tok.isupper():
            continue
        if tok.lower() not in evid and tok not in evid:
            # Allow common English starters that aren't evidence-bound
            if tok.lower() in {
                "experienced", "senior", "staff", "principal", "lead",
                "engineer", "manager", "director", "locations", "job",
                "types", "about", "featured", "projects",
            }:
                continue
            if tok not in invented:
                invented.append(tok)
    # Fake % / $ metrics not in evidence
    for m in re.finditer(
        r"\b(\d+\s*%|\d+\s*x|\$\d[\d,]*(?:\.\d+)?[kKmMbB]?)\b", draft
    ):
        metric = m.group(1)
        # Normalize spaces for evidence search
        needle = re.sub(r"\s+", "", metric.lower())
        evid_compact = re.sub(r"\s+", "", evid)
        if needle not in evid_compact and metric.lower() not in evid:
            invented.append(metric)
    return invented[:12]
