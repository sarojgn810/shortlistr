"""Pre-built LinkedIn cover (banner) themes as SVG — no LLM required."""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

# LinkedIn desktop banner aspect ~ 1584 × 396
WIDTH = 1584
HEIGHT = 396

THEMES: list[dict[str, Any]] = [
    {
        "id": "ink_lime",
        "label": "Ink & Lime",
        "description": "High-contrast product look — strong for engineering brands.",
        "bg": "#1A1A1A",
        "accent": "#DFFF5E",
        "text": "#F3F6F2",
        "muted": "#A8A8A8",
    },
    {
        "id": "sage_forest",
        "label": "Sage Forest",
        "description": "Calm, professional — good default for GCCs and enterprises.",
        "bg": "#1B4332",
        "accent": "#D8F3DC",
        "text": "#F3F6F2",
        "muted": "#95D5B2",
    },
    {
        "id": "midnight_blue",
        "label": "Midnight Blue",
        "description": "Classic recruiter-friendly blue with crisp type.",
        "bg": "#0B1F33",
        "accent": "#4CC9F0",
        "text": "#F8FAFC",
        "muted": "#94A3B8",
    },
    {
        "id": "warm_slate",
        "label": "Warm Slate",
        "description": "Neutral slate with an orange signal for leadership profiles.",
        "bg": "#2B2D31",
        "accent": "#FF6B4A",
        "text": "#FAFAF9",
        "muted": "#A8A29E",
    },
    {
        "id": "cloud_light",
        "label": "Cloud Light",
        "description": "Light banner for dense headlines — readable on any display.",
        "bg": "#ECEFE9",
        "accent": "#1A1A1A",
        "text": "#1A1A1A",
        "muted": "#666666",
    },
]


def list_themes() -> list[dict[str, Any]]:
    return [
        {
            "id": t["id"],
            "label": t["label"],
            "description": t["description"],
            "preview_colors": {"bg": t["bg"], "accent": t["accent"], "text": t["text"]},
        }
        for t in THEMES
    ]


def _theme(theme_id: str) -> dict[str, Any]:
    for t in THEMES:
        if t["id"] == theme_id:
            return t
    return THEMES[0]


def render_cover_svg(
    *,
    theme_id: str = "ink_lime",
    name: str = "",
    headline: str = "",
    subline: str = "",
) -> str:
    t = _theme(theme_id)
    name = escape((name or "").strip()[:60])
    headline = escape((headline or "").strip()[:110])
    subline = escape((subline or "").strip()[:90])
    if not headline:
        headline = "Site Reliability · Platform · Cloud"
    if not subline:
        subline = "Open to opportunities · Reliable systems at scale"

    # Decorative shapes — keep simple so SVG downloads cleanly.
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{t['bg']}"/>
  <circle cx="1380" cy="60" r="180" fill="{t['accent']}" fill-opacity="0.18"/>
  <circle cx="1500" cy="320" r="120" fill="{t['accent']}" fill-opacity="0.12"/>
  <rect x="0" y="0" width="18" height="{HEIGHT}" fill="{t['accent']}"/>
  <text x="72" y="150" font-family="Urbanist, Helvetica, Arial, sans-serif" font-size="28" font-weight="700" fill="{t['muted']}" letter-spacing="4">{(name or "YOUR NAME").upper()}</text>
  <text x="72" y="220" font-family="Urbanist, Helvetica, Arial, sans-serif" font-size="44" font-weight="700" fill="{t['text']}">{headline}</text>
  <text x="72" y="280" font-family="Urbanist, Helvetica, Arial, sans-serif" font-size="26" font-weight="500" fill="{t['muted']}">{subline}</text>
  <rect x="72" y="320" width="120" height="8" rx="4" fill="{t['accent']}"/>
</svg>
'''


def render_cover_data_uri(**kwargs) -> dict[str, Any]:
    svg = render_cover_svg(**kwargs)
    # Prefer returning SVG text — clients can download as .svg or rasterize.
    return {
        "theme_id": kwargs.get("theme_id") or "ink_lime",
        "width": WIDTH,
        "height": HEIGHT,
        "svg": svg,
        "mime": "image/svg+xml",
        "hint": "Download the SVG and upload it as your LinkedIn banner (1584×396).",
    }
