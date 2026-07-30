"""HTML → plain text for job descriptions."""

from __future__ import annotations

import html
import re


def html_to_plain(text: str, *, max_len: int = 8000) -> str:
    if not text or not str(text).strip():
        return ""
    decoded = html.unescape(str(text))
    decoded = re.sub(r"<script[\s\S]*?</script>", "", decoded, flags=re.I)
    decoded = re.sub(r"<style[\s\S]*?</style>", "", decoded, flags=re.I)
    decoded = re.sub(r"<br\s*/?>", "\n", decoded, flags=re.I)
    decoded = re.sub(r"</p>", "\n\n", decoded, flags=re.I)
    plain = re.sub(r"<[^>]+>", "", decoded)
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    if max_len and len(plain) > max_len:
        return plain[:max_len]
    return plain
