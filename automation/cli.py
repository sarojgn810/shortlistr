#!/usr/bin/env python3
"""Unified CLI for shortlistr Python tools."""

from __future__ import annotations

import os
import sys

_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and raise UnicodeEncodeError on the ✓/emoji
    # characters used throughout our output. Force UTF-8 so every command is safe.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    args = list(argv or sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print(__doc__ or "")
        print(
            "Commands: doctor, verify, normalize, normalize-pipeline, dedup, merge,\n"
            "          pdf, sync-check, liveness, scan, resolve-url, status, tracker,\n"
            "          migrate-markdown, export-pipeline, export-applications, bundle, worker, seed, reset,\n"
            "          uninstall, api, start, dev, scheduler, evaluate, explain, diff, inbox, resolve-jobs,\n"
            "          prep-backfill,\n"
            "          apply-assist, email-routing, ingest, jobs-sweep, test\n"
        )
        return 0

    cmd, rest = args[0], args[1:]

    if cmd == "doctor":
        from doctor import main as run
        return run()
    if cmd == "verify":
        from tracker_tools.verify_pipeline import main as run
        return run()
    if cmd == "normalize":
        from tracker_tools.normalize_statuses import main as run
        return run(rest)
    if cmd == "normalize-pipeline":
        from tracker_tools.normalize_pipeline import main as run
        return run()
    if cmd == "dedup":
        from tracker_tools.dedup_tracker import main as run
        return run(rest)
    if cmd == "merge":
        from tracker_tools.merge_tracker import main as run
        return run(rest)
    if cmd == "pdf":
        from generate_pdf import main as run
        return run(rest)
    if cmd == "sync-check":
        from tracker_tools.cv_sync_check import main as run
        return run()
    if cmd == "liveness":
        from check_liveness import main as run
        return run(rest)
    if cmd == "scan":
        from processors.scan_portals import main as run
        return run(rest)
    if cmd == "resolve-url":
        from scrapers.ats_url_resolver import resolve_job_url
        if not rest:
            print("Usage: resolve-url <job-url>", file=sys.stderr)
            return 1
        job = resolve_job_url(rest[0])
        if not job:
            print("Not a supported ATS URL or job not found.", file=sys.stderr)
            return 1
        print(f"{job['company']} | {job['title']} | {job.get('location', '')}")
        print(job["url"])
        return 0
    if cmd == "status":
        from tools.status import main as run
        return run()
    if cmd == "ingest":
        from jobs.ingest import main as run
        return run(rest)
    if cmd == "jobs-sweep":
        from jobs.cli import main as run
        return run(rest)
    if cmd == "tracker":
        from tools.status import format_status
        print(format_status())
        return 0
    if cmd == "explain":
        from eval.explain import explain_job, explain_job_by_url, format_explain_text
        job_id = url = ""
        for a in rest:
            if a.startswith("JOB_ID="):
                job_id = a[7:]
            elif a.startswith("URL="):
                url = a[4:]
            elif a.startswith("http"):
                url = a
        try:
            if job_id:
                data = explain_job(job_id)
            elif url:
                data = explain_job_by_url(url)
            else:
                print("Usage: explain JOB_ID=<id> OR explain URL=<url>", file=sys.stderr)
                return 1
            print(format_explain_text(data))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0
    if cmd == "evaluate":
        # Runs exactly what POST /jobs/{id}/evaluate runs, and prints the whole
        # traceback instead of a 500. A browser only ever shows "Internal Server
        # Error" when an exception escapes to the ASGI layer — the response is
        # aborted, so the detail the API meant to send never arrives, and the
        # cause is only in the server console. This puts it in front of you.
        import traceback

        job_id = ""
        for a in rest:
            if a.startswith("JOB_ID="):
                job_id = a[7:].strip()
            elif a and not a.startswith("-"):
                job_id = a.strip()
        if not job_id:
            print("Usage: evaluate JOB_ID=<id>", file=sys.stderr)
            return 1

        from api.jobs_api import prepare_job_for_eval
        from eval.service import evaluate_job_text
        from store import db as store

        try:
            store.init_db()
            with store.db() as conn:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                print(f"No job with id {job_id}", file=sys.stderr)
                return 1
            jd, company, role, url = prepare_job_for_eval(dict(row))
            print(f"job     : {company} — {role}")
            print(f"jd_chars: {len(jd or '')}")
            try:
                import llm as _llm

                prov = _llm.get_llm()
                print(f"provider: {type(prov).__name__ if prov else 'none'}"
                      f"  model={getattr(prov, 'model', '?')}"
                      f"  available={prov.is_available() if prov else False}")
            except Exception as _e:
                print(f"provider: could not resolve ({_e})")
            result = evaluate_job_text(
                jd, url=url, company=company or "", role=role or "", job_id=job_id
            )
            print(f"score   : {result.score}")
            print(f"mode    : {result.eval_mode}"
                  f"{'  (Basic score — no LLM was used)' if result.eval_mode != 'llm' else ''}")
            print(f"blocks  : {sorted((result.blocks or {}).keys())}")
            if result.eval_mode != "llm":
                # The reason the LLM path was abandoned is written into block G.
                # Printing it here means one command produces the whole answer,
                # instead of a status line that says only "it did not work".
                reason = str((result.blocks or {}).get("G") or "").strip()
                print("\nwhy it fell back to Basic score:")
                print("  " + (reason or "(no reason recorded)"))
        except Exception:
            print("\nEvaluation failed. Full traceback:\n", file=sys.stderr)
            traceback.print_exc()
            return 1
        return 0
    if cmd == "diff":
        from prep.diff import compute_diff, format_diff_text
        from models.job import job_id_from_url
        job_id = url = ""
        for a in rest:
            if a.startswith("JOB_ID="):
                job_id = a[7:]
            elif a.startswith("URL="):
                url = a[4:]
            elif a.startswith("http"):
                url = a
        try:
            jid = job_id or (job_id_from_url(url) if url else "")
            if not jid:
                print("Usage: diff JOB_ID=<id> OR diff URL=<url>", file=sys.stderr)
                return 1
            print(format_diff_text(compute_diff(jid)))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0
    if cmd == "prep-backfill":
        # Approved roles used to be left without materials whenever the browser
        # tab that approved them failed the follow-up call. This repairs them.
        from api.prep_bundle import ensure_prep_bundle, prep_exists
        from store import db as store

        dry = any(a in ("--dry-run", "-n") for a in rest)
        store.init_db()
        with store.db() as conn:
            rows = conn.execute(
                """
                SELECT j.id, j.company, j.title
                FROM pipeline p JOIN jobs j ON j.id = p.job_id
                WHERE p.status IN ('approved', 'submitted')
                ORDER BY p.added_at DESC
                """
            ).fetchall()

        missing = [dict(r) for r in rows if not prep_exists(dict(r)["id"])]
        print(f"{len(rows)} approved/submitted role(s), {len(missing)} without prep")
        if not missing:
            return 0
        if dry:
            for m in missing:
                print(f"  would generate: {m['company']} — {m['title']}")
            return 0

        failed = 0
        for m in missing:
            label = f"{m['company']} — {m['title']}"
            try:
                ensure_prep_bundle(m["id"])
                print(f"  ok   {label}")
            except Exception as e:
                failed += 1
                print(f"  FAIL {label}: {e}", file=sys.stderr)
        print(f"\n{len(missing) - failed} generated, {failed} failed")
        return 1 if failed else 0
    if cmd == "migrate-markdown":
        from store.migrate import main as run
        return run()
    if cmd == "export-pipeline":
        from store.export import main as run
        return run()
    if cmd == "export-applications":
        from store.export import export_applications
        path = export_applications()
        print(f"Exported applications to {path}")
        return 0
    if cmd == "bundle":
        from tools.bundle import main as run
        return run(rest)
    if cmd == "worker":
        from workers.discovery_worker import main as run
        return run()
    if cmd == "seed":
        from bootstrap.seed import main as run
        return run()
    if cmd == "reset":
        from bootstrap.reset import main as run
        return run()
    if cmd == "uninstall":
        from bootstrap.uninstall import main as run
        return run(rest)
    if cmd == "migrate-job-ids":
        from store.migrate_job_ids import main as run
        return run()
    if cmd == "scheduler":
        from scheduler.run_scheduler import main as run
        return run(rest)
    if cmd == "scan-scheduled":
        from scheduler.scan_scheduler import run_scheduled_scan
        dry = "--dry-run" in rest
        result = run_scheduled_scan(dry_run=dry)
        print(result)
        return 0
    if cmd == "api":
        from api.main import main as run
        run()
        return 0
    if cmd in ("start", "dev"):
        from launcher import dev, start
        return (start if cmd == "start" else dev)(rest)
    if cmd == "telegram":
        from connectors.telegram import main as run
        return run(rest)
    if cmd == "reevaluate-stale":
        # Repairs evaluations that fell back to the heuristic while the AI was
        # unreachable — otherwise a bad score looks identical to a good one.
        from scheduler.scan_scheduler import reevaluate_stale

        limit = 100
        for a in rest:
            if a.startswith("LIMIT="):
                try:
                    limit = int(a[6:])
                except ValueError:
                    pass
        res = reevaluate_stale(limit=limit)
        if res.get("skipped_no_provider"):
            print(f"{res['candidates']} stale evaluations found, but no AI provider "
                  "is available — set one up in Connections, then re-run.")
            return 1
        print(f"Re-evaluated {res['candidates']}: {res['repaired']} repaired, "
              f"{res['still_template']} still template")
        return 0

    if cmd == "evaluate":
        from eval.service import evaluate_job_text
        url = jd = ""
        for i, a in enumerate(rest):
            if a.startswith("URL="):
                url = a[4:]
            elif a == "--jd-file" and i + 1 < len(rest):
                jd = open(rest[i + 1], encoding="utf-8").read()
            elif not a.startswith("--") and a.startswith("http"):
                url = a
        if not jd and url:
            from scrapers.ats_url_resolver import resolve_job_url
            job = resolve_job_url(url)
            if job:
                jd = job.get("jd_snippet", "")
        if not jd:
            print("Usage: evaluate URL=<url> OR evaluate <url>", file=sys.stderr)
            return 1
        result = evaluate_job_text(jd, url=url)
        print(result.to_dict())
        return 0
    if cmd == "inbox":
        from api.jobs_api import prepare_job_for_eval
        from eval.service import evaluate_job_text
        from store import db as store

        store.init_db()
        with store.db() as conn:
            rows = conn.execute(
                """
                SELECT j.* FROM pipeline p JOIN jobs j ON j.id = p.job_id
                WHERE p.status = 'pending' LIMIT 10
                """
            ).fetchall()
        for row in rows:
            jd, company, role, url = prepare_job_for_eval(dict(row))
            r = evaluate_job_text(jd, url=url, company=company, role=role)
            print(f"{url} → score {r.score}/5")
        return 0
    if cmd == "resolve-jobs":
        from store import db as store
        from store.enrich import backfill_all_jobs

        limit = 50
        for a in rest:
            if a.startswith("--limit="):
                limit = int(a.split("=", 1)[1])
        store.init_db()
        with store.db() as conn:
            n = backfill_all_jobs(conn, max_jobs=limit)
        print(f"Resolved metadata for {n} job(s). Refresh the dashboard inbox.")
        return 0
    if cmd == "apply-assist":
        from apply.ats_fill import apply_assist_for_job

        job_id = ""
        headless = True
        for a in rest:
            if a.startswith("JOB_ID="):
                job_id = a[7:]
            elif a == "--headed":
                headless = False
        if not job_id:
            print("Usage: apply-assist JOB_ID=<id> [--headed]", file=sys.stderr)
            return 1
        try:
            report = apply_assist_for_job(job_id, headless=headless)
            print(report)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0
    if cmd == "email-routing":
        from processors.email_routing import route_from_recruiter_drafts

        dry_run = "--dry-run" in rest
        routed = route_from_recruiter_drafts(dry_run=dry_run)
        print(f"Routed {len(routed)} application(s)" + (" (dry run)" if dry_run else ""))
        for r in routed:
            print(f"  {r.get('company')}: {r.get('from_status')} → {r.get('to_status')}")
        return 0
    if cmd == "test":
        import pytest
        root = os.path.dirname(_BASE)
        return pytest.main(["-q", os.path.join(root, "tests")])
    if cmd == "compile-check":
        import compileall
        ok = compileall.compile_dir(_BASE, quiet=1)
        return 0 if ok else 1

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
