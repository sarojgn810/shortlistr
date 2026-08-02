"""Deterministic cleanup of generic AI-style patterns — works with or without an LLM.

Does not invent claims; only removes or lightly rewrites known patterns.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Mapping

from writing import policy as P

Mode = Literal["prose", "label"]


def _word_boundary_sub(text: str, word: str, repl: str = "") -> str:
    return re.sub(rf"(?i)\b{re.escape(word)}\b", repl, text)


def _strip_banned_words(text: str) -> str:
    out = text
    for w in sorted(P.BANNED_WORDS, key=len, reverse=True):
        out = _word_boundary_sub(out, w, "")
    for adv in P.EMPTY_ADVERBS:
        out = _word_boundary_sub(out, adv, "")
    return out


def _strip_banned_phrases(text: str) -> str:
    out = text
    for phrase in sorted(P.BANNED_PHRASES, key=len, reverse=True):
        out = re.sub(re.escape(phrase), "", out, flags=re.I)
    return out


def _collapse_ws(text: str) -> str:
    # Preserve paragraph breaks; tidy intra-line spaces and dangling punctuation.
    parts = []
    for para in text.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", para)
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        line = re.sub(r"([(])\s+", r"\1", line)
        line = re.sub(r"\s+([)])", r"\1", line)
        line = re.sub(r"^[,;:\s]+", "", line)
        line = re.sub(r"\s+\.", ".", line)
        parts.append(line.rstrip())
    out = "\n".join(parts)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _apply_prose_patterns(text: str) -> str:
    out = text
    out = P.THROAT_CLEARING.sub("", out)
    out = P.FAUX_INSIGHT.sub("", out)
    out = P.RHETORICAL.sub("", out)
    out = P.SUMMARY_RECAP.sub("", out)
    out = P.DRAMATIC_FRAGMENT.sub("", out)
    out = P.SUPERFICIAL_ING.sub(".", out)
    out = P.IMPORTANCE_PUFFERY.sub("", out)
    out = P.WEASEL_ATTR.sub("", out)
    out = P.FAKE_STRONG.sub("is", out)
    out = P.EMOJI_HEADING.sub(r"\1", out)

    def _bin_contrast(m: re.Match[str]) -> str:
        y = (m.group(2) or "").strip()
        if y and not y.endswith((".", "!", "?")):
            y += "."
        return y

    out = P.BINARY_CONTRAST.sub(_bin_contrast, out)
    out = P.BINARY_QUESTION.sub(
        lambda m: (m.group(2) or "").strip()
        if (m.group(2) or "").strip().endswith((".", "!", "?"))
        else (m.group(2) or "").strip() + ".",
        out,
    )
    out = P.NOT_JUST_BUT.sub(
        lambda m: (m.group(2) or "").strip()
        if (m.group(2) or "").strip().endswith((".", "!", "?"))
        else (m.group(2) or "").strip() + ".",
        out,
    )
    out = P.NEGATIVE_LISTING.sub(lambda m: (m.group(1) or "").strip(), out)

    def _colon_reveal(m: re.Match[str]) -> str:
        label = (m.group(1) or "").strip()
        rest = (m.group(2) or "").strip()
        if not rest:
            return label
        # Prefer a plain sentence: capitalize rest.
        rest = rest[0].upper() + rest[1:] if rest else rest
        return f"{rest}"

    out = P.COLON_REVEAL.sub(_colon_reveal, out)

    # Em dashes: in short copy remove; in longer drafts keep at most two.
    dashes = list(P.EM_DASH_CLUSTER.finditer(out))
    if len(out) < 400 or len(dashes) > 2:
        out = P.EM_DASH_CLUSTER.sub(", ", out)
    elif dashes:
        # Normalize remaining to spaced commas for ATS friendliness when >2 already handled
        pass

    return out


def sanitize(text: str, *, mode: Mode = "prose") -> str:
    """Clean generic AI-style patterns from text.

    mode='prose' — full pattern + banned-word cleanup (cover letters, About, eval blocks).
    mode='label' — banned fluff only (fit reasons, subjects, short status lines).
    """
    if not text:
        return text
    out = str(text)
    out = _strip_banned_phrases(out)
    out = _strip_banned_words(out)
    if mode == "prose":
        out = _apply_prose_patterns(out)
    out = _collapse_ws(out)
    return out


def sanitize_blocks(
    blocks: Mapping[str, Any] | None, *, mode: Mode = "prose"
) -> dict[str, str]:
    """Sanitize string values in an eval-style blocks dict; leave keys intact."""
    if not isinstance(blocks, dict):
        return {}
    return {
        str(k): sanitize(str(v), mode=mode) if v is not None else ""
        for k, v in blocks.items()
    }
