"""Recompute stored evaluation scores from the evidence already on disk.

Every evaluation keeps the requirement list it was judged against, so changing
how a score is calculated does not mean re-reading hundreds of postings with an
LLM. It means redoing arithmetic over rows we already have — no network, no
tokens, no waiting.

Evaluations that predate the requirement list are left alone. There is nothing
to recompute from, and inventing a number for them would be exactly the
guesswork this replaces; they need a genuine re-evaluation instead.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from eval import scoring
from store import db as store

logger = logging.getLogger(__name__)

# What counts as "the top of the list" when reporting the effect of a rescore.
TOP_BAND = 4.5


def rescore_all(*, dry_run: bool = False) -> dict[str, Any]:
    """Rescore every evaluation that carries evidence.

    Returns counts plus before/after top-band sizes, because the reason for
    doing this is that the top band used to hold half the corpus.
    """
    store.init_db()

    rescored = 0
    skipped = 0
    top_before = 0
    top_after = 0
    updates: list[tuple[float, str, int]] = []

    with store.db() as conn:
        rows = conn.execute(
            "SELECT id, job_id, score, result_json FROM eval_results"
        ).fetchall()

        for row in rows:
            try:
                payload = json.loads(row["result_json"] or "{}")
            except Exception:
                skipped += 1
                continue

            old = row["score"]
            if isinstance(old, (int, float)) and old >= TOP_BAND:
                top_before += 1

            derived = scoring.score_from_evidence(payload.get("must_haves"))
            if derived is None:
                skipped += 1
                # Still counts toward the "after" picture: leaving it alone
                # means it keeps whatever band it was already in.
                if isinstance(old, (int, float)) and old >= TOP_BAND:
                    top_after += 1
                continue

            rescored += 1
            if derived >= TOP_BAND:
                top_after += 1

            payload["score"] = derived
            payload["score_source"] = "evidence"
            # Keep the model's original number rather than erasing it — the two
            # rankings should stay comparable after the fact.
            payload.setdefault("model_score", old)
            updates.append((derived, json.dumps(payload), row["id"]))

        if not dry_run and updates:
            conn.executemany(
                "UPDATE eval_results SET score = ?, result_json = ? WHERE id = ?", updates
            )
            # applications.score is what the pipeline and inbox actually read.
            # Leaving it stale would rescore the data and change nothing the
            # user can see.
            conn.execute(
                """
                UPDATE applications
                   SET score = (
                       SELECT e.score FROM eval_results e
                        WHERE e.job_id = applications.job_id
                        ORDER BY e.id DESC LIMIT 1
                   )
                 WHERE EXISTS (
                       SELECT 1 FROM eval_results e WHERE e.job_id = applications.job_id
                   )
                """
            )

    report = {
        "rescored": rescored,
        "skipped": skipped,
        "total": len(rows),
        "top_band_before": top_before,
        "top_band_after": top_after,
        "dry_run": dry_run,
    }
    logger.info("rescore: %s", report)
    return report
