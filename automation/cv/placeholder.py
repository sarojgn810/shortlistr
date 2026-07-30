"""Detect default / placeholder cv.md content."""

from __future__ import annotations

PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "# your name",
    "email@example.com",
    "linkedin.com/in/you",
    "your title | company",
    "your role, years of experience",
    "degree | school | years",
    "one measurable win",
    "bullet with a metric",
)


def is_placeholder_cv(md: str) -> bool:
    """True when markdown still looks like the onboarding template."""
    if not md or not md.strip():
        return True
    lower = md.lower()
    hits = sum(1 for m in PLACEHOLDER_MARKERS if m in lower)
    return hits >= 3
