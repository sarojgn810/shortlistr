"""Banned words, empty phrases, and generic AI-style pattern detectors.

Merged with local lists from modes/_shared.md and linkedin_optimizer fluff sets.
"""

from __future__ import annotations

import re

# Single words / short tokens — remove when they add nothing.
BANNED_WORDS: frozenset[str] = frozenset(
    {
        "delve",
        "delves",
        "delving",
        "foster",
        "fosters",
        "fostering",
        "leverage",
        "leverages",
        "leveraging",
        "leveraged",
        "utilize",
        "utilizes",
        "utilizing",
        "utilized",
        "facilitate",
        "facilitates",
        "facilitating",
        "facilitated",
        "empower",
        "empowers",
        "empowering",
        "empowered",
        "streamline",
        "streamlines",
        "streamlining",
        "streamlined",
        "robust",
        "cutting-edge",
        "paradigm",
        "tapestry",
        "realm",
        "beacon",
        "multifaceted",
        "meticulous",
        "intricate",
        "paramount",
        "transformative",
        "elevate",
        "elevates",
        "elevating",
        "elevated",
        "embark",
        "embarks",
        "embarking",
        "supercharge",
        "supercharges",
        "supercharging",
        "harness",
        "harnesses",
        "harnessing",
        "harnessed",
        "seamless",
        "synergy",
        "synergies",
        "spearheaded",
        "spearhead",
        "passionate",
        "rockstar",
        "ninja",
        "guru",
    }
)

# Multi-word fluff — strip when found (case-insensitive).
BANNED_PHRASES: tuple[str, ...] = (
    "game changer",
    "game-changer",
    "this is huge",
    "this changes everything",
    "paradigm shift",
    "ever-evolving",
    "cutting edge",
    "driven professional",
    "hard worker",
    "team player",
    "results-oriented",
    "results oriented",
    "self-starter",
    "self starter",
    "proven track record",
    "passionate about",
    "demonstrated ability to",
    "in today's fast-paced world",
    "in today's world",
    "in the age of",
    "in the world of",
    "it's worth noting",
    "it is worth noting",
    "it's important to note",
    "it is important to note",
    "at the end of the day",
    "when it comes to",
    "at its core",
    "the reality is",
    "the truth is",
    "with regard to",
    "in terms of",
    "in order to",
    "going forward",
    "in this article",
    "let's dive in",
    "lets dive in",
    "highly motivated professional",
    "best practices",  # vague — prefer naming the practice
)

# Often-empty adverbs — strip only as whole words when they add nothing.
EMPTY_ADVERBS: frozenset[str] = frozenset(
    {
        "literally",
        "fundamentally",
        "importantly",
        "crucially",
        "inherently",
        "inevitably",
    }
)

# Pattern regexes for prose-mode cleanup.
THROAT_CLEARING = re.compile(
    r"(?i)^\s*(here's the thing|here's what i mean|let me be clear|"
    r"i'll be honest|the uncomfortable truth is|to be honest)[,:\s]+"
)

FAUX_INSIGHT = re.compile(
    r"(?i)\b(this is the part most people skip|what most people get wrong|"
    r"here's what nobody tells you|the part everyone misses|"
    r"what nobody tells you)\s*[:,]?\s*"
)

BINARY_CONTRAST = re.compile(
    r"(?i)\b(?:this is |it's |it is )not\s+([^.!?]+?)[.;]\s*"
    r"(?:it'?s |it is )(?:just\s+)?([^.!?]+[.!?]?)"
)

BINARY_QUESTION = re.compile(
    r"(?i)\bthe question isn'?t\s+([^.!?]+?)[,;]\s*it'?s\s+([^.!?]+[.!?]?)"
)

NOT_JUST_BUT = re.compile(
    r"(?i)\bit'?s not just\s+([^.!?]+?)\s+but(?:\s+also)?\s+([^.!?]+[.!?]?)"
)

COLON_REVEAL = re.compile(
    r"(?i)\b(the best part|the key|the detail that makes it work|"
    r"the secret|the real moat)\s*:\s*([a-z][^.!\n]*)"
)

SUPERFICIAL_ING = re.compile(
    r"(?i),\s*(highlighting|underscoring|reflecting|showcasing|"
    r"demonstrating|emphasizing|illustrating)\s+(?:the\s+)?"
    r"(?:team'?s\s+)?(?:commitment|dedication|importance|significance|"
    r"focus|passion)\s+(?:to|for|of)\s+[^.!?]+[.!]?"
)

IMPORTANCE_PUFFERY = re.compile(
    r"(?i)\b(stands as a testament|marks a pivotal moment|"
    r"plays a vital role|solidifies its position|"
    r"underscores its significance|is a game.?changer)\b[^.!?]*[.!]?"
)

WEASEL_ATTR = re.compile(
    r"(?i)\b(experts agree|industry reports suggest|many argue|"
    r"widely regarded as|studies show|research shows)\b[^.!?]*[.!]?"
)

FAKE_STRONG = re.compile(
    r"(?i)\bserves as a(?:n)?\s+(?:centralized\s+)?(?:hub|platform|solution)\b"
)

NEGATIVE_LISTING = re.compile(
    r"(?i)\bnot a\s+[^.!?]+[.]\s*not a\s+[^.!?]+[.]\s*(?:a\s+)?([^.!?]+[.!?]?)"
)

DRAMATIC_FRAGMENT = re.compile(
    r"(?i)\bthat'?s it[.,]?\s*that'?s the whole thing\.?"
)

RHETORICAL = re.compile(
    r"(?i)\b(what if i told you|think about it|plot twist)\s*[:.]?\s*"
)

SUMMARY_RECAP = re.compile(
    r"(?i)^\s*(in conclusion|ultimately|overall|to summarize|in summary)\s*[,:]?\s*"
)

EMOJI_HEADING = re.compile(r"(?m)^([#*\s]*)[\U0001F300-\U0001FAFF💡🚀✨🔥✅❌➡️]+\s*")

EM_DASH_CLUSTER = re.compile(r"[—–]{1,}")

# Local LinkedIn / modes fluff phrases for detection scoring.
LOCAL_FLUFF: frozenset[str] = frozenset(
    {
        "passionate",
        "synergy",
        "rockstar",
        "ninja",
        "guru",
        "driven professional",
        "hard worker",
        "team player",
        "results-oriented",
        "self-starter",
        "proven track record",
        "passionate about",
    }
)
