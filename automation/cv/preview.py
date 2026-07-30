"""HTML resume preview — A4 single page with auto-fit and per-template layouts."""

from __future__ import annotations

import html
import re

from cv.parser import CvSections, parse_cv_markdown
from cv.reflow import parse_blocks
from cv.sample_content import DEMO_SAMPLE_CV
from cv.templates import template_family

SAMPLE_CV = DEMO_SAMPLE_CV

_BASE_CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #d4d4d8;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 12px;
  }
  .a4-sheet {
    width: 210mm;
    height: 297mm;
    background: #fff;
    box-shadow: 0 4px 24px rgba(0,0,0,.15);
    overflow: hidden;
    position: relative;
  }
  .cv-fit-root {
    transform-origin: top left;
    width: 100%;
    height: 100%;
    color: #1f2937;
    --accent: #1d4ed8;
  }
  .cv-name {
    font-size: 1.7rem;
    font-weight: 800;
    line-height: 1.1;
    letter-spacing: -0.01em;
    margin-bottom: 0.28rem;
    color: #0f172a;
  }
  .cv-contact {
    font-size: 0.7rem;
    color: #475569;
    line-height: 1.45;
  }
  .cv-headline {
    font-size: 0.78rem;
    font-style: italic;
    color: #334155;
    margin-bottom: 0.15rem;
  }
  .cv-contact-line { margin: 0; }
  .cv-section { margin-bottom: 0.6rem; }
  .cv-section h2 {
    font-size: 0.64rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.13em;
    margin: 0 0 0.32rem;
    padding-bottom: 0.12rem;
    color: var(--accent);
    border-bottom: 1.5px solid #e2e8f0;
  }
  .cv-section-body {
    font-size: 0.72rem;
    line-height: 1.4;
    color: #334155;
  }
  .cv-section-body h4 {
    font-size: 0.74rem;
    font-weight: 700;
    margin: 0.36rem 0 0.1rem;
    color: #0f172a;
  }
  .cv-section-body h4 + p { color: #64748b; font-size: 0.68rem; }
  /* Role on the left, dates flush right — the same shape the LaTeX entry
     macro draws, so switching between the two previews is not a jump cut. */
  .cv-entry {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.6rem;
    margin: 0.36rem 0 0.06rem;
  }
  .cv-what { font-size: 0.74rem; font-weight: 700; color: #0f172a; }
  .cv-when { font-size: 0.66rem; color: #64748b; white-space: nowrap; }
  .cv-entry-meta {
    font-size: 0.68rem;
    font-style: italic;
    color: #64748b;
    margin-bottom: 0.08rem;
  }
  .cv-section-body ul {
    margin: 0.12rem 0 0.18rem;
    padding-left: 1.05rem;
    list-style-type: disc;
  }
  .cv-section-body li { margin-bottom: 0.1rem; }
  .cv-section-body p { margin: 0.08rem 0; }
  strong { font-weight: 700; color: #0f172a; }
  .cv-multi-page-hint {
    display: none;
    position: absolute;
    bottom: 4mm;
    right: 6mm;
    font-size: 7pt;
    color: #888;
  }
  body.allow-multi .cv-multi-page-hint { display: block; }

  /* Awesome-CV inspired — crimson accents, no filled header band */
  .layout-awesome .a4-sheet { padding: 9mm 12mm; }
  .layout-awesome .cv-name { color: #c0392b; font-size: 1.7rem; letter-spacing: 0.01em; }
  .layout-awesome .cv-header {
    margin-bottom: 0.55rem;
    padding-bottom: 0.4rem;
    border-bottom: 2.5px solid #c0392b;
  }
  .layout-awesome .cv-section h2 {
    color: #c0392b;
    border-bottom: 1.5px solid #c0392b;
    padding-bottom: 0.12rem;
    display: inline-block;
    width: 100%;
  }

  /* Split Header (was a real sidebar — dropped for ATS reading order) */
  .layout-sidebar .a4-sheet { padding: 9mm 12mm; }
  .layout-sidebar .cv-header-split {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 1rem;
    margin-bottom: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid #2c3e50;
  }
  .layout-sidebar .cv-header-split .cv-name {
    margin: 0;
    color: #2c3e50;
    font-size: 1.55rem;
  }
  .layout-sidebar .cv-header-split .cv-contact {
    text-align: right;
    max-width: 48%;
  }
  .layout-sidebar .cv-section h2 { color: #2c3e50; }

  /* Reactive-Resume inspired */
  .layout-reactive .a4-sheet { padding: 9mm 11mm; }
  .layout-reactive .cv-header { margin-bottom: 0.5rem; }
  .layout-reactive .cv-accent-bar {
    width: 22%;
    height: 3px;
    background: linear-gradient(90deg, #6366f1, #8b5cf6);
    border-radius: 2px;
    margin: 0.25rem 0 0.4rem;
  }
  .layout-reactive .cv-section {
    background: #f8fafc;
    border-radius: 6px;
    padding: 0.35rem 0.5rem;
    border-left: 3px solid #6366f1;
  }
  .layout-reactive .cv-section h2 { color: #6366f1; margin-bottom: 0.15rem; }

  /* ── Per-template visual identity: distinct accent + heading treatment ──── */
  /* classic-ats — safe navy, clean rule (the reliable default) */
  .tpl-classic-ats .cv-fit-root { --accent: #1e3a5f; }

  /* modern-minimal — monochrome, heavy rule + wide tracking */
  .tpl-modern-minimal .cv-fit-root { --accent: #111827; }
  .tpl-modern-minimal .cv-name { font-weight: 800; letter-spacing: -0.02em; }
  .tpl-modern-minimal .cv-section h2 { color: #111827; border-bottom: 2px solid #111827; letter-spacing: 0.18em; padding-bottom: 0.14rem; }

  /* tech-compact — monospace, teal, dense */
  .tpl-tech-compact .cv-fit-root { font-family: "SF Mono", "Consolas", "Roboto Mono", monospace; font-size: 95%; --accent: #0d9488; }
  .tpl-tech-compact .cv-section { margin-bottom: 0.45rem; }
  .tpl-tech-compact .cv-section h2 { color: #0d9488; border-bottom: 1px dashed #99f6e4; }

  /* harvard-ats — centered, traditional serif */
  .tpl-harvard-ats .cv-fit-root { font-family: Georgia, "Times New Roman", serif; --accent: #1f2937; }
  .tpl-harvard-ats .cv-header { text-align: center; }
  .tpl-harvard-ats .cv-name { text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
  .tpl-harvard-ats .cv-section h2 { text-align: center; color: #1f2937; border-bottom: 1px solid #9ca3af; letter-spacing: 0.16em; }

  /* executive — charcoal name + amber accent, summary panel */
  .tpl-executive .cv-fit-root { --accent: #b45309; }
  .tpl-executive .cv-name { color: #1c1917; font-size: 1.9rem; }
  .tpl-executive .cv-section h2 { color: #b45309; border-bottom: 2px solid #fcd34d; }
  .tpl-executive .cv-summary { background: #fef3c7; padding: 0.45rem 0.6rem; border-radius: 4px; border-left: 3px solid #b45309; }

  /* skills-first — sky-blue, boxed skills, keyword-forward */
  .tpl-skills-first .cv-fit-root { --accent: #0284c7; }
  .tpl-skills-first .cv-section h2 { color: #0284c7; }
  .tpl-skills-first .cv-skills-block { background: #f0f9ff; padding: 0.4rem 0.55rem; border-radius: 4px; border: 1px solid #bae6fd; }

  /* minimal-plain — pure black, underline headings, zero decoration (strict ATS) */
  .tpl-minimal-plain .cv-fit-root { --accent: #111827; }
  .tpl-minimal-plain .cv-section h2 { color: #111; border-bottom: none; text-decoration: underline; text-transform: none; letter-spacing: 0; }

  /* professional — teal, soft rule, balanced */
  .tpl-professional .cv-fit-root { --accent: #0f766e; }
  .tpl-professional .cv-section h2 { color: #0f766e; border-bottom: 1.5px solid #99f6e4; }

  /* Print / PDF: drop screen chrome so the A4 sheet fills the page (WYSIWYG). */
  @media print {
    @page { size: A4; margin: 0; }
    body { padding: 0; background: #fff; display: block; }
    .a4-sheet { box-shadow: none; margin: 0; width: 210mm; height: 297mm; }
    .cv-multi-page-hint { display: none; }
  }
"""

_FIT_SCRIPT = """
(function () {
  function fitOnePage() {
    var sheet = document.querySelector('.a4-sheet');
    var root = document.querySelector('.cv-fit-root');
    if (!sheet || !root) return;
    var single = document.body.dataset.singlePage !== 'false';
    root.style.transform = 'none';
    root.style.width = '100%';
    root.style.fontSize = '100%';
    if (!single) return;
    var maxH = sheet.clientHeight;
    var pct = 100;
    for (var i = 0; i < 35 && root.scrollHeight > maxH && pct > 72; i++) {
      pct -= 2;
      root.style.fontSize = pct + '%';
    }
    if (root.scrollHeight > maxH) {
      // Cap the shrink so text never becomes unreadably tiny. A CV that still
      // overflows at this floor is genuinely too long for one page — trim it, or
      // render with single_page=false (multi-page).
      var scale = Math.max(maxH / root.scrollHeight, 0.75);
      if (scale < 1) {
        root.style.transform = 'scale(' + scale + ')';
        root.style.width = (100 / scale) + '%';
      }
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fitOnePage);
  } else { fitOnePage(); }
  window.addEventListener('resize', fitOnePage);
})();
"""


def _inline_html(text: str) -> str:
    esc = html.escape(text)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
    return re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", esc)


def _md_block_to_html(text: str) -> str:
    """Render one section, from the same blocks the LaTeX builder uses.

    Parsing markdown a second time, differently, is what let the preview and
    the PDF disagree: this converter emitted one `<p>` per source line, so a
    hard-wrapped bullet became a one-item list plus a stray paragraph. Both
    renderers now walk `cv.reflow.parse_blocks`, so a structural fix lands in
    both at once and the preview is worth trusting.
    """
    if not text.strip():
        return ""
    from cv.latex_builder import _split_when

    out: list[str] = []
    for block in parse_blocks(text, split_when=_split_when):
        if block.kind == "entry":
            when = f'<span class="cv-when">{_inline_html(block.when)}</span>' if block.when else ""
            out.append(
                f'<div class="cv-entry"><span class="cv-what">'
                f"{_inline_html(block.text)}</span>{when}</div>"
            )
        elif block.kind == "meta":
            out.append(f'<div class="cv-entry-meta">{_inline_html(block.text)}</div>')
        elif block.kind == "bullets":
            lis = "".join(f"<li>{_inline_html(i)}</li>" for i in block.items)
            out.append(f"<ul>{lis}</ul>")
        elif block.text:
            out.append(f"<p>{_inline_html(block.text)}</p>")
    return "\n".join(out)


def _title_from_key(key: str) -> str:
    return re.sub(r"\s+", " ", key.replace("_", " ").strip()).title()


def _section_html(title: str, body: str, *, extra_class: str = "") -> str:
    inner = _md_block_to_html(body)
    if not inner:
        return ""
    cls = f"cv-section {extra_class}".strip()
    return (
        f'<section class="{cls}">'
        f"<h2>{html.escape(title)}</h2>"
        f'<div class="cv-section-body">{inner}</div>'
        f"</section>"
    )


def _collect_sections(sections: CvSections, template_id: str) -> list[tuple[str, str, str]]:
    summary_cls = " cv-summary" if template_id == "executive" else ""
    skills_cls = " cv-skills-block" if template_id == "skills-first" else ""
    ordered: list[tuple[str, str, str]] = [
        ("Professional Summary", sections.summary, summary_cls),
        ("Core Competencies", sections.skills, skills_cls),
        ("Professional Experience", sections.experience, ""),
        ("Education", sections.education, ""),
        ("Certifications", sections.certifications, ""),
    ]
    if template_id == "skills-first" and sections.skills.strip():
        ordered = [
            ("Core Competencies", sections.skills, skills_cls),
            ("Professional Summary", sections.summary, summary_cls),
            ("Professional Experience", sections.experience, ""),
            ("Education", sections.education, ""),
            ("Certifications", sections.certifications, ""),
        ]
    # Projects became its own field when the LaTeX path needed to render it as
    # dated entries. Without this line the HTML path silently stopped showing a
    # section it had always shown.
    if sections.projects.strip():
        ordered.append(("Projects", sections.projects, ""))
    if sections.achievements.strip() and sections.achievements not in sections.experience:
        ordered.append(("Key Achievements", sections.achievements, ""))
    seen: set[str] = set()
    for key, body in sections.extra.items():
        body = body.strip()
        if body and body not in seen:
            seen.add(body)
            ordered.append((_title_from_key(key), body, ""))
    return [(t, b, c) for t, b, c in ordered if b.strip()]


def _contact_html(raw: str) -> str:
    """Optional role headline, then the contact details on their own line."""
    lines = [re.sub(r"^\*+|\*+$", "", l.strip()).strip() for l in (raw or "").splitlines()]
    lines = [l for l in lines if l]
    if not lines:
        return ""
    contact_hint = re.compile(
        r"@|https?://|\+?\d[\d\s\-()]{7,}|linkedin\.com|github\.com", re.I
    )
    parts: list[str] = []
    if len(lines) > 1 and not contact_hint.search(lines[0]):
        parts.append(f'<div class="cv-headline">{_inline_html(lines.pop(0))}</div>')
    parts.append(f'<div class="cv-contact-line">{_inline_html(" · ".join(lines))}</div>')
    return "".join(parts)


def _header_html(name: str, contact_html: str) -> str:
    return (
        '<header class="cv-header">'
        f'<h1 class="cv-name">{html.escape(name)}</h1>'
        f'<div class="cv-contact">{contact_html}</div>'
        "</header>"
    )


def _build_inner(md: str, template_id: str) -> str:
    sections = parse_cv_markdown(md)
    name = sections.name.strip() or "Your Name"
    contact_html = _contact_html(sections.contact)
    family = template_family(template_id)
    blocks = _collect_sections(sections, template_id)

    def render_blocks(items: list[tuple[str, str, str]]) -> str:
        return "".join(_section_html(t, b, extra_class=c) for t, b, c in items)

    if family == "awesome":
        # Crimson name + rule — not the original filled header band. White text
        # on a colour box is one of the things ATS parsers drop or reorder.
        header = (
            '<header class="cv-header">'
            f'<h1 class="cv-name">{html.escape(name)}</h1>'
            f'<div class="cv-contact">{contact_html}</div>'
            "</header>"
        )
        return '<div class="cv-fit-root">' + header + render_blocks(blocks) + "</div>"

    if family == "sidebar":
        # Name left / contact right in the header only. A real two-column
        # sidebar is what the LaTeX path dropped: ATS extractors walk the page
        # as one stream and interleave the sidebar into the body.
        header = (
            '<header class="cv-header cv-header-split">'
            f'<h1 class="cv-name">{html.escape(name)}</h1>'
            f'<div class="cv-contact">{contact_html}</div>'
            "</header>"
        )
        return '<div class="cv-fit-root">' + header + render_blocks(blocks) + "</div>"

    if family == "reactive":
        accent = '<div class="cv-accent-bar"></div>'
        header = (
            '<header class="cv-header">'
            f'<h1 class="cv-name">{html.escape(name)}</h1>'
            f"{accent}"
            f'<div class="cv-contact">{contact_html}</div>'
            "</header>"
        )
        return '<div class="cv-fit-root">' + header + render_blocks(blocks) + "</div>"

    return '<div class="cv-fit-root">' + _header_html(name, contact_html) + render_blocks(blocks) + "</div>"


def render_cv_html(md: str, template_id: str = "classic-ats", *, single_page: bool = True) -> str:
    """Render resume as self-contained A4 HTML with auto-fit to one page."""
    source = (md or "").strip() or SAMPLE_CV
    family = template_family(template_id)
    layout_class = {
        "awesome": "layout-awesome",
        "sidebar": "layout-sidebar",
        "reactive": "layout-reactive",
    }.get(family, "layout-classic")
    tpl_class = f"tpl-{template_id}"
    sections = parse_cv_markdown(source)
    name = sections.name.strip() or "Your Name"
    inner = _build_inner(source, template_id)
    body_attr = 'data-single-page="true"' if single_page else 'data-single-page="false" class="allow-multi"'
    hint = "" if single_page else '<p class="cv-multi-page-hint">Multi-page preview</p>'
    padding_style = ""
    if family not in ("awesome", "sidebar"):
        padding_style = ".a4-sheet { padding: 9mm 11mm; }"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(name)} — CV</title>
  <style>{_BASE_CSS}{padding_style}</style>
</head>
<body class="{layout_class} {tpl_class}" {body_attr}>
  <div class="a4-sheet">
    {inner}
    {hint}
  </div>
  <script>{_FIT_SCRIPT}</script>
</body>
</html>"""
