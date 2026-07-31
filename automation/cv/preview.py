"""HTML resume preview — A4 pages that scale to the iframe and paginate.

The preview used to draw a fixed ``210mm`` sheet inside a ~520px iframe, so
type looked oversized and long CVs were clipped (``overflow: hidden``) instead
of flowing onto page two. Sheets are now viewport-width, typography is
relative to that width, and content that will not fit one page at a readable
size becomes a second (or third) A4 sheet.
"""

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
  html, body {
    width: 100%;
    min-height: 100%;
    background: #d4d4d8;
  }
  body {
    /* Scale type to the iframe width so A4 always fills the frame. */
    font-size: calc(100vw / 52);
    font-family: "Helvetica Neue", Helvetica, Arial, system-ui, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.55em;
    padding: 0.55em;
    color: #1f2937;
  }
  .a4-stack {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.55em;
  }
  .a4-sheet {
    /* Full iframe width; height follows the A4 ratio (210×297). */
    width: 100%;
    height: calc(100vw * 297 / 210);
    background: #fff;
    box-shadow: 0 0.2em 1em rgba(0,0,0,.14);
    overflow: hidden;
    position: relative;
    padding: 5.5% 6%;
  }
  body.force-multi .a4-sheet,
  body.allow-multi .a4-sheet {
    /* Continuous multi-page stack uses one growing sheet + page rules. */
  }
  .a4-sheet.is-flow {
    height: auto;
    min-height: calc(100vw * 297 / 210);
    overflow: visible;
    /* Visual page breaks every A4 height. */
    background-color: #fff;
    background-image: repeating-linear-gradient(
      to bottom,
      #fff 0,
      #fff calc(100vw * 297 / 210 - 1px),
      #94a3b8 calc(100vw * 297 / 210 - 1px),
      #94a3b8 calc(100vw * 297 / 210)
    );
  }
  .cv-fit-root {
    transform-origin: top left;
    width: 100%;
    color: #1f2937;
    --accent: #1d4ed8;
  }
  .cv-name {
    font-size: 1.45em;
    font-weight: 700;
    line-height: 1.15;
    letter-spacing: -0.01em;
    margin-bottom: 0.22em;
    color: #0f172a;
  }
  .cv-contact {
    font-size: 0.72em;
    color: #475569;
    line-height: 1.4;
  }
  .cv-headline {
    font-size: 0.78em;
    font-style: italic;
    color: #334155;
    margin-bottom: 0.12em;
  }
  .cv-contact-line { margin: 0; }
  .cv-section { margin-bottom: 0.55em; }
  .cv-section h2 {
    font-size: 0.68em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin: 0 0 0.28em;
    padding-bottom: 0.1em;
    color: var(--accent);
    border-bottom: 1.5px solid #e2e8f0;
  }
  .cv-section-body {
    font-size: 0.74em;
    line-height: 1.35;
    color: #334155;
  }
  .cv-section-body h4 {
    font-size: 1.02em;
    font-weight: 700;
    margin: 0.32em 0 0.08em;
    color: #0f172a;
  }
  .cv-section-body h4 + p { color: #64748b; font-size: 0.94em; }
  .cv-entry {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.55em;
    margin: 0.32em 0 0.05em;
  }
  .cv-what { font-size: 1.02em; font-weight: 700; color: #0f172a; }
  .cv-when { font-size: 0.92em; color: #64748b; white-space: nowrap; }
  .cv-entry-meta {
    font-size: 0.94em;
    font-style: italic;
    color: #64748b;
    margin-bottom: 0.06em;
  }
  .cv-section-body ul {
    margin: 0.1em 0 0.16em;
    padding-left: 1.15em;
    list-style-type: disc;
  }
  .cv-section-body li { margin-bottom: 0.08em; }
  .cv-section-body p { margin: 0.06em 0; }
  strong { font-weight: 700; color: #0f172a; }
  .cv-page-label {
    position: absolute;
    bottom: 2.2%;
    right: 4%;
    font-size: 0.55em;
    color: #94a3b8;
    letter-spacing: 0.04em;
  }
  .cv-multi-banner {
    display: none;
    width: 100%;
    text-align: center;
    font-size: 0.65em;
    color: #64748b;
    padding: 0 0 0.15em;
  }
  body.allow-multi .cv-multi-banner,
  body.force-multi .cv-multi-banner { display: block; }

  /* Awesome-CV inspired — crimson accents */
  .layout-awesome .cv-name { color: #c0392b; font-size: 1.4em; letter-spacing: 0.01em; }
  .layout-awesome .cv-header {
    margin-bottom: 0.5em;
    padding-bottom: 0.35em;
    border-bottom: 2px solid #c0392b;
  }
  .layout-awesome .cv-section h2 {
    color: #c0392b;
    border-bottom: 1.5px solid #c0392b;
  }

  /* Split header */
  .layout-sidebar .cv-header-split {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 0.9em;
    margin-bottom: 0.45em;
    padding-bottom: 0.35em;
    border-bottom: 2px solid #2c3e50;
  }
  .layout-sidebar .cv-header-split .cv-name {
    margin: 0;
    color: #2c3e50;
    font-size: 1.35em;
  }
  .layout-sidebar .cv-header-split .cv-contact {
    text-align: right;
    max-width: 48%;
  }
  .layout-sidebar .cv-section h2 { color: #2c3e50; }

  /* Reactive-Resume inspired */
  .layout-reactive .cv-header { margin-bottom: 0.45em; }
  .layout-reactive .cv-accent-bar {
    width: 22%;
    height: 0.18em;
    background: linear-gradient(90deg, #6366f1, #8b5cf6);
    border-radius: 2px;
    margin: 0.2em 0 0.35em;
  }
  .layout-reactive .cv-section {
    background: #f8fafc;
    border-radius: 4px;
    padding: 0.3em 0.45em;
    border-left: 3px solid #6366f1;
  }
  .layout-reactive .cv-section h2 { color: #6366f1; margin-bottom: 0.12em; }

  .tpl-classic-ats .cv-fit-root { --accent: #1e3a5f; }
  .tpl-modern-minimal .cv-fit-root { --accent: #111827; }
  .tpl-modern-minimal .cv-name { font-weight: 800; letter-spacing: -0.02em; }
  .tpl-modern-minimal .cv-section h2 {
    color: #111827;
    border-bottom: 2px solid #111827;
    letter-spacing: 0.16em;
  }
  .tpl-tech-compact .cv-fit-root {
    font-family: "SF Mono", "Consolas", "Roboto Mono", monospace;
    font-size: 0.96em;
    --accent: #0d9488;
  }
  .tpl-tech-compact .cv-section { margin-bottom: 0.4em; }
  .tpl-tech-compact .cv-section h2 { color: #0d9488; border-bottom: 1px dashed #99f6e4; }
  .tpl-harvard-ats .cv-fit-root { font-family: Georgia, "Times New Roman", serif; --accent: #1f2937; }
  .tpl-harvard-ats .cv-header { text-align: center; }
  .tpl-harvard-ats .cv-name { text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; font-size: 1.3em; }
  .tpl-harvard-ats .cv-section h2 {
    text-align: center;
    color: #1f2937;
    border-bottom: 1px solid #9ca3af;
  }
  .tpl-executive .cv-fit-root { --accent: #b45309; }
  .tpl-executive .cv-name { color: #1c1917; font-size: 1.5em; }
  .tpl-executive .cv-section h2 { color: #b45309; border-bottom: 2px solid #fcd34d; }
  .tpl-executive .cv-summary {
    background: #fef3c7;
    padding: 0.4em 0.5em;
    border-radius: 3px;
    border-left: 3px solid #b45309;
  }
  .tpl-skills-first .cv-fit-root { --accent: #0284c7; }
  .tpl-skills-first .cv-section h2 { color: #0284c7; }
  .tpl-skills-first .cv-skills-block {
    background: #f0f9ff;
    padding: 0.35em 0.45em;
    border-radius: 3px;
    border: 1px solid #bae6fd;
  }
  .tpl-minimal-plain .cv-fit-root { --accent: #111827; }
  .tpl-minimal-plain .cv-section h2 {
    color: #111;
    border-bottom: none;
    text-decoration: underline;
    text-transform: none;
    letter-spacing: 0;
  }
  .tpl-professional .cv-fit-root { --accent: #0f766e; }
  .tpl-professional .cv-section h2 { color: #0f766e; border-bottom: 1.5px solid #99f6e4; }

  @media print {
    @page { size: A4; margin: 0; }
    body { padding: 0; background: #fff; gap: 0; font-size: 11pt; }
    .a4-sheet {
      box-shadow: none;
      width: 210mm;
      height: 297mm;
      padding: 12mm 14mm;
      page-break-after: always;
    }
    .a4-sheet.is-flow {
      height: auto;
      min-height: 297mm;
      background-image: none;
    }
    .cv-multi-banner, .cv-page-label { display: none !important; }
  }
"""

_FIT_SCRIPT = """
(function () {
  var PAGE_FLOOR = 0.88; // never crush type below ~88% when forcing one page

  function pageHeightPx(sheet) {
    // Prefer the designed A4 ratio over clientHeight (padding included).
    return sheet.clientWidth * 297 / 210;
  }

  function contentHeight(root) {
    return root.scrollHeight;
  }

  function setFlow(sheet, on) {
    if (on) sheet.classList.add('is-flow');
    else sheet.classList.remove('is-flow');
  }

  function pageCountFor(sheet, root) {
    var ph = pageHeightPx(sheet);
    var pad = sheet.clientHeight > 0
      ? Math.max(0, sheet.clientHeight - (sheet.querySelector('.cv-fit-root') ? 0 : 0))
      : 0;
    // Usable content box ≈ sheet height minus vertical padding (~11% total).
    var usable = ph * 0.89;
    return Math.max(1, Math.ceil(contentHeight(root) / usable));
  }

  function updateLabel(sheet, pages) {
    var label = sheet.querySelector('.cv-page-label');
    if (!label) return;
    label.textContent = pages <= 1 ? '1 page' : pages + ' pages';
  }

  function updateBanner(pages) {
    var banner = document.querySelector('.cv-multi-banner');
    if (!banner) return;
    if (pages <= 1) {
      banner.style.display = 'none';
      banner.textContent = '';
      return;
    }
    banner.style.display = 'block';
    banner.textContent = pages + '-page preview · type stays readable (PDF uses the same page target)';
  }

  function fit() {
    var sheet = document.querySelector('.a4-sheet');
    var root = document.querySelector('.cv-fit-root');
    if (!sheet || !root) return;

    var preferSingle = document.body.dataset.singlePage === 'true';
    root.style.transform = 'none';
    root.style.width = '100%';
    root.style.fontSize = '100%';
    setFlow(sheet, false);

    // Measure at natural size against one A4 page.
    var ph = pageHeightPx(sheet);
    sheet.style.height = ph + 'px';
    var overflows = contentHeight(root) > sheet.clientHeight - 2;

    if (!overflows) {
      document.body.classList.remove('allow-multi');
      updateLabel(sheet, 1);
      updateBanner(1);
      // Tell parent how tall one page is (optional; sandbox may block).
      try {
        parent.postMessage({ type: 'cv-preview-pages', pages: 1 }, '*');
      } catch (e) {}
      return;
    }

    if (preferSingle) {
      // Tighten a little, but do not go unreadably small.
      var pct = 100;
      for (var i = 0; i < 20 && contentHeight(root) > sheet.clientHeight - 2 && pct / 100 > PAGE_FLOOR; i++) {
        pct -= 2;
        root.style.fontSize = pct + '%';
      }
      if (contentHeight(root) <= sheet.clientHeight - 2) {
        document.body.classList.remove('allow-multi');
        updateLabel(sheet, 1);
        updateBanner(1);
        try { parent.postMessage({ type: 'cv-preview-pages', pages: 1 }, '*'); } catch (e) {}
        return;
      }
      // Still too long for one page at a readable size → fall through to multi.
    }

    // Multi-page: keep readable type, let the sheet grow, show page rules.
    document.body.classList.add('allow-multi');
    root.style.fontSize = '100%';
    setFlow(sheet, true);
    sheet.style.height = 'auto';
    var pages = pageCountFor(sheet, root);
    updateLabel(sheet, pages);
    updateBanner(pages);
    try { parent.postMessage({ type: 'cv-preview-pages', pages: pages }, '*'); } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fit);
  } else { fit(); }
  window.addEventListener('resize', fit);
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
        header = (
            '<header class="cv-header">'
            f'<h1 class="cv-name">{html.escape(name)}</h1>'
            f'<div class="cv-contact">{contact_html}</div>'
            "</header>"
        )
        return '<div class="cv-fit-root">' + header + render_blocks(blocks) + "</div>"

    if family == "sidebar":
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


def render_cv_html(md: str, template_id: str = "classic-ats", *, single_page: bool = False) -> str:
    """Render resume as self-contained A4 HTML.

    ``single_page=False`` (default for dashboard preview): keep readable type
    and grow onto page 2+ when the CV is long.

    ``single_page=True``: try to tighten onto one page first; if it still will
    not fit above the readable floor, fall back to multi-page rather than
    clipping or microscopic type.
    """
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
    body_attr = (
        'data-single-page="true"' if single_page else 'data-single-page="false"'
    )
    extra_body_class = " force-multi" if not single_page else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(name)} — CV</title>
  <style>{_BASE_CSS}</style>
</head>
<body class="{layout_class} {tpl_class}{extra_body_class}" {body_attr}>
  <p class="cv-multi-banner" hidden></p>
  <div class="a4-stack">
    <div class="a4-sheet">
      {inner}
      <span class="cv-page-label">1 page</span>
    </div>
  </div>
  <script>{_FIT_SCRIPT}</script>
</body>
</html>"""
