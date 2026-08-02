"""Turn résumé markdown into renderable blocks, joining hard-wrapped lines.

Why this exists
---------------
A `cv.md` that came out of a PDF is hard-wrapped: the extractor emits one
source line per *visual* line of the original, around 130 characters each. Both
renderers used to treat one source line as one paragraph, which produced:

    \\begin{itemize}\\item AIOps Platform: ... reducing alert noise\\end{itemize}
    by 55\\% and dramatically improving on-call signal-to-noise ratio.\\par

— every bullet its own single-item list, with the rest of the sentence dumped
underneath it at zero indent. Seven bullets became seven lists and seven
orphan paragraphs. That, not the templates, is why the output ran to four
pages and looked unaligned.

Both the LaTeX builder and the HTML preview parse through here, so the preview
and the PDF now disagree about nothing structural.

Joining rules
-------------
* **Inside a bullet** any following plain line continues that bullet, until a
  blank line, another bullet, or a heading. This is plain markdown ("lazy
  continuation") and is never ambiguous.
* **In prose** consecutive lines join into one paragraph only when the previous
  line looks *machine-wrapped* — at least 85% of the block's widest line. A
  block whose longest line is under 70 characters is a list of short lines
  (certifications, degrees), not wrapped prose, and is left alone.

The 85% threshold is deliberately conservative. Below it, distinct items start
merging into run-on paragraphs; above it, a genuine continuation occasionally
stays on its own line. A stray fragment is a blemish, a merged pair of skill
categories is wrong information, so the failure mode is chosen rather than
minimised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_BULLET = re.compile(r"^[-*•]\s+(.+)$")
_ITALIC_ONLY = re.compile(r"^\*(.+?)\*$")

# Under this, a block is a list of short lines rather than wrapped prose.
MIN_WRAP_WIDTH = 70
CONTINUATION_RATIO = 0.85


# An entry title is a noun phrase — a degree, an employer, a project. The
# longest real one seen is around 140 characters ("Executive PhD — Artificial
# Intelligence & Machine Learning (Pursuing), National Institute of Technology
# (NIT) Rourkela, India"). Anything longer, or anything containing a sentence
# boundary, is prose that happens to close on a year range, and promoting it
# would turn a summary into a job entry.
MAX_ENTRY_CHARS = 160


def _trailing_date(text: str) -> tuple[str, str]:
    """Split "Some Degree, Some College 2007 – 2011" into title and dates."""
    if len(text) > MAX_ENTRY_CHARS or ". " in text:
        return text, ""
    from cv.normalize import _DATE_RANGE

    match = None
    for match in _DATE_RANGE.finditer(text):
        pass
    if not match or match.end() < len(text.rstrip()):
        return text, ""
    what = text[: match.start()].strip(" ,;:-–—([{")
    return (what or text), match.group(0).strip()


def join_wrapped(prefix: str, suffix: str) -> str:
    """Join two halves of a line the wrapper split.

    A trailing hyphen keeps its word attached: this class of extractor breaks
    at spaces, never mid-syllable, so "on cloud-" + "native Kubernetes" is the
    compound "cloud-native" and not a hyphenated "cloudnative". Joining on a
    plain space instead printed "cloud- native" and "Cross- functional".
    """
    if prefix.endswith("-") and suffix[:1].isalpha():
        return prefix + suffix
    return f"{prefix} {suffix}"


@dataclass
class Block:
    """One renderable unit. `kind` is entry | meta | bullets | para."""

    kind: str
    text: str = ""
    when: str = ""
    items: list[str] = field(default_factory=list)


def _wrap_threshold(lines: list[str]) -> float | None:
    """Length above which a prose line is assumed to have been wrapped."""
    widths = [
        len(s) for s in (l.strip() for l in lines)
        if s and not s.startswith(("#", "-", "*", "•"))
    ]
    if not widths:
        return None
    widest = max(widths)
    return widest * CONTINUATION_RATIO if widest >= MIN_WRAP_WIDTH else None


def parse_blocks(text: str, *, split_when=None) -> list[Block]:
    """Markdown for one résumé section → blocks.

    `split_when` is the date-lifting helper; passing it in keeps this module
    free of LaTeX-side imports. Without it, dates stay inside the heading.
    """
    if not text or not text.strip():
        return []

    lines = [l.rstrip() for l in text.splitlines()]
    threshold = _wrap_threshold(lines)

    blocks: list[Block] = []
    items: list[str] = []
    para: list[str] = []
    expect_meta = False

    def flush_para() -> None:
        nonlocal expect_meta
        if not para:
            return
        joined = para[0]
        for part in para[1:]:
            joined = join_wrapped(joined, part)
        para.clear()
        what, when = _trailing_date(joined)
        if when:
            # "B.Tech — Electronics Engineering, … India 2007 – 2011" and
            # "Enterprise RAG Chat Engine — Capstone Project 2025 – Present"
            # are entries that never got a `###` because they came out of a
            # PDF. Rendered as prose they lose the flush-right date column
            # that Experience has, and Education and Projects end up looking
            # like a different document from the section above them.
            blocks.append(Block("entry", text=what, when=when))
            expect_meta = True
            return
        blocks.append(Block("para", joined))

    def flush_items() -> None:
        if items:
            blocks.append(Block("bullets", items=list(items)))
            items.clear()

    def add_prose(s: str) -> None:
        nonlocal expect_meta
        # Start a new paragraph unless the line before it was full-width, i.e.
        # unless it was broken by a wrapper rather than by the author.
        if para and (threshold is None or len(para[-1]) < threshold):
            flush_para()
        if expect_meta and not para:
            # The line straight under a role heading is the employer and
            # location. Rendering it as body text loses the one visual cue
            # telling a reader which company a set of bullets belongs to.
            #
            # Unless it closes on its own date range — then it is the *next*
            # entry, not a subtitle for the last one. Education is two degrees
            # in a row, and demoting the second one made the B.Tech read as the
            # institution that awarded the PhD.
            expect_meta = False
            if not _trailing_date(s)[1]:
                blocks.append(Block("meta", text=s))
                return
        para.append(s)

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped or stripped == "---":
            flush_items()
            flush_para()
            expect_meta = False
            i += 1
            continue

        if stripped.startswith("### "):
            flush_items()
            flush_para()
            what = stripped[4:].strip()
            when = ""
            if split_when:
                what, when = split_when(what)
            # The metadata line the normaliser writes directly underneath.
            if i + 1 < len(lines):
                m = _ITALIC_ONLY.fullmatch(lines[i + 1].strip())
                if m:
                    if not when:
                        when = m.group(1).strip()
                    i += 1
            blocks.append(Block("entry", text=what, when=when))
            expect_meta = True
            i += 1
            continue

        if stripped.startswith("## "):
            flush_items()
            flush_para()
            blocks.append(Block("meta", text=stripped[3:].strip()))
            expect_meta = False
            i += 1
            continue

        m = _BULLET.match(stripped)
        if m:
            flush_para()
            expect_meta = False
            items.append(m.group(1).strip())
            i += 1
            continue

        if items:
            items[-1] = join_wrapped(items[-1], stripped)
            i += 1
            continue

        m = _ITALIC_ONLY.fullmatch(stripped)
        if m:
            flush_para()
            blocks.append(Block("meta", text=m.group(1).strip()))
            expect_meta = False
            i += 1
            continue

        add_prose(stripped)
        i += 1

    flush_items()
    flush_para()
    return blocks
