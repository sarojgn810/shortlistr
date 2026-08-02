"""System-prompt style block for LLM generators.

Appended per call site — never wrap LLMProvider.complete() globally
(that would corrupt eval JSON and chat tool-call JSON).
"""

from __future__ import annotations

STYLE_BLOCK = """
Writing style (mandatory):
- Be concrete and specific. Prefer names, numbers, tools, and mechanisms over abstractions.
- Use active voice with human subjects. Prefer direct verbs ("decided", "cut", "built") over "made a decision" / "has the ability to".
- Cut banned words: delve, foster, leverage, utilize, facilitate, empower, streamline, robust, cutting-edge, paradigm, tapestry, realm, beacon, multifaceted, meticulous, intricate, paramount, transformative, elevate, embark, supercharge, harness, seamless, synergy, spearheaded, passionate.
- Cut empty phrases: it's worth noting, at the end of the day, when it comes to, at its core, in today's world, let's dive in, proven track record, highly motivated professional, passionate about, results-oriented.
- No binary contrasts ("It's not X. It's Y."), throat-clearing ("Here's the thing"), faux-insight setups ("What nobody tells you"), colon reveals for drama, or trailing "-ing" clauses that pretend to explain meaning (highlighting/underscoring/showcasing…).
- No importance puffery, weasel attribution ("experts agree"), dramatic fragments, or summary-recap endings ("In conclusion").
- No emoji in headings. Prefer plain sentences over decorative bold or bullet-spam for short claims.
- Use em dashes sparingly (usually none in short copy). Prefer commas, periods, or parentheses.
- Do not invent claims, employers, metrics, skills, quotes, or opinions. Stay grounded in the evidence provided.
- Preserve the user's real voice and meaning. Minimum effective edit — do not polish every sentence into identical tidy prose.
""".strip()


def with_style(system: str = "") -> str:
    """Append STYLE_BLOCK to a system prompt (idempotent)."""
    base = (system or "").rstrip()
    if "Writing style (mandatory):" in base:
        return base
    if not base:
        return STYLE_BLOCK
    return f"{base}\n\n{STYLE_BLOCK}"
