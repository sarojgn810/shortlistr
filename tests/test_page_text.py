"""HTML page compression keeps SSR JSON payloads and drops chrome."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

NEXT_HTML = """
<html><head><title>SRE — Acme Careers</title></head>
<body>
  <div id="__next"></div>
  <script id="__NEXT_DATA__" type="application/json">%s</script>
  <style>.x{color:red}</style>
  <p>Enable JavaScript to view this page.</p>
</body></html>
""" % json.dumps(
    {
        "props": {
            "pageProps": {
                "job": {
                    "title": "Site Reliability Engineer",
                    "location": "Bengaluru, India",
                    "description": "Own Kubernetes, Terraform and on-call for Acme India. "
                    * 5,
                    "company": "Acme",
                }
            }
        }
    }
)


def test_mines_next_data_into_markdown():
    from scrapers.html_text import html_to_markdown, mine_script_json

    blobs = mine_script_json(NEXT_HTML)
    assert blobs
    md = html_to_markdown(NEXT_HTML)
    assert "Site Reliability Engineer" in md
    assert "Bengaluru" in md
    assert "Kubernetes" in md
    assert "<script" not in md.lower()
    assert "color:red" not in md


def test_html_to_plain_still_works_on_markup():
    from scrapers.html_text import html_to_plain

    plain = html_to_plain("<p>Hello <b>world</b></p><br/>Next")
    assert "Hello" in plain
    assert "world" in plain
