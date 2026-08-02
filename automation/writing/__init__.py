"""Writing quality layer — reduce generic AI-style patterns in generated copy.

This is a specificity / clarity policy — not detector evasion, watermark
stripping, or a claim that text "has no AI traces."
"""

from writing.sanitize import sanitize, sanitize_blocks
from writing.self_check import self_check
from writing.style import STYLE_BLOCK, with_style

__all__ = [
    "STYLE_BLOCK",
    "sanitize",
    "sanitize_blocks",
    "self_check",
    "with_style",
]
