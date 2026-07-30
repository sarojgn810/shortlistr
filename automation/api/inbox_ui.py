#!/usr/bin/env python3
"""Minimal web inbox UI — HTMX-friendly HTML served by FastAPI."""

from __future__ import annotations

from store import db as store


def render_inbox_html() -> str:
    store.init_db()
    rows = []
    with store.db() as conn:
        cur = conn.execute(
            """
            SELECT j.id, j.url, j.company, j.title, j.fit_score, j.source, p.status
            FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            WHERE p.status = 'pending'
            ORDER BY j.fit_score DESC, p.added_at DESC
            LIMIT 50
            """
        )
        rows = cur.fetchall()

    items = []
    for r in rows:
        items.append(
            f"<tr>"
            f"<td>{r['company'] or '—'}</td>"
            f"<td>{r['title'] or '—'}</td>"
            f"<td>{r['fit_score'] or 0}</td>"
            f"<td>{r['source'] or '—'}</td>"
            f"<td><a href=\"{r['url']}\" target=\"_blank\">Open</a></td>"
            f"<td><button hx-post=\"/jobs/{r['id']}/evaluate\" hx-target=\"#{r['id']}-score\">Evaluate</button>"
            f"<span id=\"{r['id']}-score\"></span></td>"
            f"</tr>"
        )

    body = "\n".join(items) if items else "<tr><td colspan=\"6\">No pending jobs</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>shortlistr inbox</title>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <h1>shortlistr inbox</h1>
  <p>Pending jobs from SQLite pipeline. Use API token if configured.</p>
  <table>
    <thead><tr><th>Company</th><th>Role</th><th>Fit</th><th>Source</th><th>URL</th><th>Actions</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</body>
</html>"""
