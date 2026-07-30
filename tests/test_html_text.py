"""Tests for HTML → plain text."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from scrapers.html_text import html_to_plain


def test_html_to_plain_strips_tags():
    raw = '<div class="content-intro"><p>Hello <strong>world</strong></p></div>'
    assert "Hello world" in html_to_plain(raw)
    assert "<div" not in html_to_plain(raw)


def test_html_to_plain_decodes_entities():
    raw = "&lt;p&gt;YugabyteDB&lt;/p&gt;"
    assert "YugabyteDB" in html_to_plain(raw)
