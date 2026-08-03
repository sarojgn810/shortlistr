"""FastAPI layer — Phase 2 local API (SQLite-backed, auth-ready)."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import zipfile
from typing import Optional

from store import db as store

try:
    from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Header, UploadFile
    from fastapi.responses import FileResponse, HTMLResponse
    from pydantic import BaseModel
except ImportError:
    FastAPI = None  # type: ignore
    BaseModel = object  # type: ignore
    File = UploadFile = None  # type: ignore

from api.auth import verify_token
from config import SHORTLISTR_ROOT, DATA_DIR

API_TOKEN = os.environ.get("SHORTLISTR_API_TOKEN", "")


class DiscoverRequest(BaseModel):
    dry_run: bool = True


class PipelineStatusBody(BaseModel):
    status: str
    reason: str = ""


class CvSaveBody(BaseModel):
    markdown: str


class CvGenerateBody(BaseModel):
    template_id: str = "ats-single"
    markdown: str | None = None
    # "auto" | "1" | "2" — see cv/latex_builder.fit_to_pages.
    page_target: str | None = None


class ResumeSourceBody(BaseModel):
    resume_source: str  # "uploaded" | "generated"


class CvPreviewBody(BaseModel):
    template_id: str = "ats-single"
    markdown: str | None = None
    use_sample: bool = False
    # False: readable type, paginate when long. True: try one page first.
    single_page: bool = False


def _allowed_cv_path(path: str) -> bool:
    """Only serve files under project root or output dir."""
    if not path:
        return False
    real = os.path.realpath(path)
    root = os.path.realpath(SHORTLISTR_ROOT)
    out = os.path.realpath(os.path.join(SHORTLISTR_ROOT, "output"))
    return real.startswith(root + os.sep) or real.startswith(out + os.sep) or real == root


class AutomationSettingsBody(BaseModel):
    scan_enabled: bool | None = None
    scan_interval_hours: int | None = None
    auto_evaluate: bool | None = None
    auto_evaluate_min_score: float | None = None
    auto_approve_score: float | None = None
    onboarding_complete: bool | None = None


class ProfileSetupBody(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    years_exp: Optional[int] = None
    min_salary_inr_lpa: Optional[int] = None
    min_salary_usd: Optional[int] = None
    salary_unlisted: Optional[str] = None
    target_titles: Optional[list[str] | str] = None
    preferred_locations: Optional[list[str]] = None
    min_fit_score: Optional[int] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_two_stage_triage: Optional[bool] = None
    website: Optional[str] = None
    notice_period: Optional[str] = None
    current_ctc: Optional[str] = None
    expected_ctc: Optional[str] = None
    how_heard: Optional[str] = None
    work_authorization: Optional[str] = None
    preferred_name: Optional[str] = None
    cover_letter_snippet: Optional[str] = None
    willing_to_relocate: Optional[str] = None


class McpServerBody(BaseModel):
    name: str
    type: str = "stdio"
    command: Optional[str] = None
    args: Optional[list[str] | str] = None
    url: Optional[str] = None
    secret_ref: Optional[str] = None


class ConnectionsBody(BaseModel):
    """Partial update — omit a field to leave it unchanged; send "" on a secret to clear it."""
    linkedin_email: Optional[str] = None
    linkedin_password: Optional[str] = None
    naukri_email: Optional[str] = None
    naukri_password: Optional[str] = None
    gmail_sender: Optional[str] = None
    gmail_app_password: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    apify_token: Optional[str] = None
    apify_enabled: Optional[bool] = None
    page_reader_enabled: Optional[bool] = None
    email_verify_api_key: Optional[str] = None
    email_verify_provider: Optional[str] = None
    serper_api_key: Optional[str] = None
    google_cse_api_key: Optional[str] = None
    google_cse_cx: Optional[str] = None
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    github_token: Optional[str] = None
    mcp_servers: Optional[list[McpServerBody]] = None


class PortalsFingerprintBody(BaseModel):
    urls: list[str] = []
    company_name: str = ""


class PortalsApplyBody(BaseModel):
    proposals: list[dict] = []


class SuggestEmailsBody(BaseModel):
    name: str = ""
    company: str = ""
    domain: str = ""
    website: str = ""
    verify: bool = False


class ContactResolveBody(BaseModel):
    use_serp: bool = True
    use_github: bool = True
    verify: bool = True


class InstantlyExportBody(BaseModel):
    job_id: Optional[str] = None
    contacts: Optional[list[dict]] = None
    company: str = ""
    personalization: str = ""


class ApplyAssistBody(BaseModel):
    headless: bool = True
    confirm: bool = False


class ApplyBatchBody(BaseModel):
    job_ids: list[str] = []
    confirm: bool = False


class SendApplicationBody(BaseModel):
    body: str | None = None  # edited cover letter; falls back to generated
    confirm: bool = False


class AgentDiscoverBody(BaseModel):
    dry_run: bool = True


class AgentJobBody(BaseModel):
    job_id: str


class AgentApplyBody(BaseModel):
    job_id: str
    headless: bool = True
    confirm: bool = False  # required for submit-class tools unless on autopilot


class AgentResolveBody(BaseModel):
    limit: int = 50


class AgentCallBody(BaseModel):
    name: str
    args: dict = {}
    confirm: bool = False


class AgentChatBody(BaseModel):
    message: str = ""
    history: list[dict] = []
    confirm_tool: str | None = None
    confirm_args: dict = {}



class PrepCoverLetterBody(BaseModel):
    body: str


class PrepReachOutContact(BaseModel):
    id: str | None = None
    name: str = ""
    title: str = ""
    email: str = ""
    linkedin_url: str = ""
    note: str = ""


class PrepReachOutContactsBody(BaseModel):
    contacts: list[PrepReachOutContact] = []


class PrepOutreachDraftBody(BaseModel):
    body: str


def _auth(authorization: Optional[str] = Header(None)) -> dict:
    if not API_TOKEN and not os.environ.get("SHORTLISTR_JWT_SECRET"):
        return {"sub": "anonymous", "tenant_id": "default", "role": "owner"}
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if API_TOKEN and token == API_TOKEN:
            return {"sub": "api_user", "tenant_id": "default", "role": "owner"}
        payload = verify_token(token)
        if payload:
            return payload
    if API_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")
    # SHORTLISTR_JWT_SECRET set without SHORTLISTR_API_TOKEN used to fall through to an
    # anonymous OWNER here — configuring auth made the API *look* protected while
    # granting everyone full access. Fail closed instead.
    raise HTTPException(
        status_code=401,
        detail="SHORTLISTR_JWT_SECRET is set but no valid bearer token was supplied. "
               "Send a JWT, or set SHORTLISTR_API_TOKEN, or unset the secret for "
               "local-only use.",
    )


def _require_owner(user: dict) -> None:
    if user.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Owner role required")


def _start_background_scheduler() -> None:
    """Launch a daemon thread that runs the scan scheduler + worker queue."""
    import logging
    import threading
    import time

    logger = logging.getLogger("shortlistr.scheduler")

    def _loop() -> None:
        time.sleep(5)
        while True:
            try:
                from scheduler.scan_scheduler import run_scheduled_scan, scan_is_due
                from workers.discovery_worker import process_pending

                # Always honour the schedule. Forcing the first tick meant a fresh
                # clone ran a full multi-portal scan ~5s after boot, against the
                # seeded sample profile, before the user had touched onboarding.
                should_run = scan_is_due()

                if should_run:
                    result = run_scheduled_scan()
                    logger.info(
                        "Background scan: +%s relevant, %s off-target",
                        result.get("discovered"),
                        result.get("rejected"),
                    )
                process_pending()
            except Exception as exc:
                logger.warning("Scheduler tick: %s", exc)
            time.sleep(300)

    t = threading.Thread(target=_loop, daemon=True, name="shortlistr-scheduler")
    t.start()
    logger.info("Background scheduler started (5-minute interval)")


def _start_local_ai_bootstrap() -> None:
    """Download/start the tiny on-device model when the user has not chosen cloud AI."""
    try:
        from llm.local_ai import maybe_autostart_local_ai

        maybe_autostart_local_ai()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Local AI autostart: %s", exc)


def create_app():
    if FastAPI is None:
        raise RuntimeError("Install fastapi and uvicorn: pip install fastapi uvicorn")

    app = FastAPI(title="shortlistr API", version="1.0.0")

    # Best-effort: import tools from any configured MCP servers into the registry.
    try:
        from connectors.importer import import_mcp_tools

        import_mcp_tools()
    except Exception:
        pass

    _start_background_scheduler()
    _start_local_ai_bootstrap()

    try:
        from fastapi.middleware.cors import CORSMiddleware

        # Local dev: dashboard may be localhost:3000 while API is 127.0.0.1:8787
        _local_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"

        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://127.0.0.1:3000",
                "http://localhost:3000",
            ],
            allow_origin_regex=_local_origin_regex,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"],
        )
    except ImportError:
        pass

    @app.exception_handler(Exception)
    async def _unhandled_exception(request, exc):  # type: ignore[no-untyped-def]
        """Always return JSON detail — empty 500s made the dashboard unusable."""
        import logging
        import traceback

        from fastapi.responses import JSONResponse

        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail, "code": "http_error"},
            )
        logging.getLogger(__name__).error(
            "Unhandled API error on %s: %s\n%s",
            getattr(request, "url", ""),
            exc,
            traceback.format_exc(),
        )
        msg = str(exc).strip() or type(exc).__name__
        # Keep short — never dump paths/secrets.
        if len(msg) > 280:
            msg = msg[:277] + "…"
        return JSONResponse(
            status_code=500,
            content={
                "detail": msg,
                "code": "internal_error",
                "hint": "Check API logs. If this persists after restart, open Connections and run doctor.",
            },
        )

    @app.get("/health")
    def health():
        from llm.status import llm_status

        return {"status": "ok", "llm": llm_status()}

    @app.get("/setup/status")
    def setup_status(user: dict = Depends(_auth)):
        """Onboarding readiness — no secrets."""
        from llm.status import llm_status
        from paths import CV_PATH, PROFILE_PATH

        try:
            from doctor import check_playwright
        except ImportError:
            check_playwright = None  # type: ignore

        store.init_db()
        from store.queries import min_fit_threshold
        from store.status import pipeline_status_counts

        threshold = min_fit_threshold()
        with store.db() as conn:
            job_count = conn.execute(
                """
                SELECT COUNT(*) AS c FROM jobs j
                WHERE j.source != 'eval' AND j.archived_at IS NULL
                  AND COALESCE(json_extract(j.metadata_json, '$.discovery_relevance'), 'relevant')
                      != 'off_target'
                  AND COALESCE(j.fit_score, 0) >= ?
                """,
                (threshold,),
            ).fetchone()["c"]
        targeted = pipeline_status_counts(targeted=True)
        pipeline_count = sum(int(v) for v in targeted.values())

        from cv.placeholder import is_placeholder_cv

        cv_ok = False
        if os.path.isfile(CV_PATH):
            try:
                cv_ok = not is_placeholder_cv(open(CV_PATH, encoding="utf-8").read())
            except OSError:
                cv_ok = False

        checks = {
            "cv": cv_ok,
            "profile": os.path.isfile(PROFILE_PATH),
            "sqlite": os.path.isfile(os.path.join(DATA_DIR, "shortlistr.db")),
            "llm": llm_status()["available"],
            "playwright": check_playwright()["pass"] if check_playwright else False,
            "apify": False,
        }
        try:
            from connections_store import get_connections_for_ui

            checks["apify"] = bool(get_connections_for_ui().get("apify", {}).get("ready"))
        except Exception:
            checks["apify"] = False
        ready = checks["cv"] and checks["profile"] and checks["sqlite"]
        from store.settings import (
            effective_onboarding_complete,
            get_automation_settings,
            get_cv_settings,
        )
        from cv.ats_score import score_ats_readiness
        from config import CV_MD_PATH

        automation = get_automation_settings(user.get("tenant_id", "default"))
        cv_settings = get_cv_settings(user.get("tenant_id", "default"))
        ats = {"score": 0, "tier": "needs work", "checks": []}
        if os.path.isfile(CV_MD_PATH):
            md = open(CV_MD_PATH, encoding="utf-8").read()
            tpl = cv_settings.get("template_id", "") or ""
            ats = score_ats_readiness(
                md,
                template_id=tpl,
                include_template=bool(tpl),
            )

        # Sticky wizard flag OR essentials actually done (profile+real CV+db).
        # File existence alone is not enough — that left Today nagging forever
        # for users who finished via /profile and /cv without the wizard Done step.
        onboarding_done, onboarding_gaps = effective_onboarding_complete(
            automation, tenant_id=user.get("tenant_id", "default")
        )

        llm = llm_status()
        # Demo gate: API+DB are implied by this response; LLM is local OR any key.
        demo = {
            "api": True,
            "db_migrated": checks["sqlite"],
            "llm_available": bool(llm.get("available")),
            "playwright_optional": bool(checks.get("playwright")),
            "ready_for_chat": bool(llm.get("available")),
            "hint": (
                None
                if llm.get("available")
                else "Paste a free Groq key on Connections, or set up Local AI, for full chat and scoring."
            ),
        }
        return {
            "ready": ready,
            "checks": checks,
            "llm": llm,
            "demo": demo,
            "counts": {"pipeline": pipeline_count, "jobs": job_count},
            "automation": automation,
            "cv": {**cv_settings, "ats": ats},
            "onboarding_complete": onboarding_done,
            "onboarding_gaps": onboarding_gaps,
        }

    @app.get("/setup/profile")
    def get_setup_profile(user: dict = Depends(_auth)):
        from profile_store import get_profile_for_ui

        return get_profile_for_ui()

    @app.put("/setup/profile")
    def put_setup_profile(body: ProfileSetupBody, user: dict = Depends(_auth)):
        from profile_store import save_profile_from_ui

        try:
            return save_profile_from_ui(body.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/setup/connections")
    def get_setup_connections(user: dict = Depends(_auth)):
        from connections_store import get_connections_for_ui

        return get_connections_for_ui()

    @app.put("/setup/connections")
    def put_setup_connections(body: ConnectionsBody, user: dict = Depends(_auth)):
        from connections_store import save_connections_from_ui

        try:
            return save_connections_from_ui(body.model_dump(exclude_unset=True))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.post("/setup/connections/test-search")
    def test_search_connection(user: dict = Depends(_auth)):
        """Run one real query so a saved key is proved, not assumed.

        "Ready" only ever meant both values were present. A key can be present
        and still be an OAuth client ID, belong to a project without the API
        enabled, or be restricted to other APIs — each of which looks identical
        until a search silently returns nothing hours later.
        """
        from processors.search_discovery import run_search_query, search_backend_available

        backend = search_backend_available()
        if backend not in ("google_cse", "serpapi"):
            return {"ok": False, "backend": backend,
                    "message": "No search key saved — add a Google Custom Search "
                               "key and engine ID above."}
        try:
            results = run_search_query("site reliability engineer", backend=backend, num=3)
        except Exception as e:
            return {"ok": False, "backend": backend, "message": str(e)[:400]}
        if not results:
            return {"ok": False, "backend": backend,
                    "message": "The key works but returned no results. If the "
                               "engine names only a few sites, that is expected "
                               "for this test query."}
        return {"ok": True, "backend": backend,
                "message": f"Working — {len(results)} results for a test query."}

    @app.post("/setup/connections/test-llm")
    def test_llm_connection(user: dict = Depends(_auth)):
        """One tiny completion, so "Ready" means the key works.

        is_available() only checks that a key is present. A key can be present
        and be revoked, out of quota, for the wrong provider, or naming a model
        the account cannot reach — all of which read as Ready until the first
        evaluation quietly falls back to keyword scoring.
        """
        from llm import get_llm
        from llm.status import llm_status

        st = llm_status()
        provider = get_llm()
        if not provider:
            return {"ok": False, "provider": st.get("provider"),
                    "message": st.get("reason")
                               or "No AI provider configured. Add a key above, "
                                  "or set up Local AI."}
        try:
            reply = provider.complete(
                'Reply with exactly: {"ok": true}', max_tokens=40
            )
        except Exception as e:
            return {"ok": False, "provider": st.get("resolved_provider") or st.get("provider"),
                    "model": getattr(provider, "model", ""), "message": str(e)[:400]}

        if not (reply or "").strip():
            return {"ok": False, "provider": st.get("resolved_provider"),
                    "model": getattr(provider, "model", ""),
                    "message": "The model returned nothing. On a small local "
                               "model this usually means the reply was cut off "
                               "before it started — try a larger one."}
        return {"ok": True,
                "provider": st.get("resolved_provider") or st.get("provider"),
                "model": getattr(provider, "model", ""),
                "message": f"Working — {getattr(provider, 'model', 'the model')} "
                           f"answered in {len(reply.strip())} characters."}

    @app.post("/setup/playwright/install")
    def post_playwright_install(user: dict = Depends(_auth)):
        from connections_store import install_playwright_chromium

        result = install_playwright_chromium()
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error") or "Install failed")
        return result

    @app.get("/setup/local-ai")
    def get_local_ai(user: dict = Depends(_auth)):
        from llm.local_ai import local_ai_status

        return local_ai_status()

    @app.post("/setup/local-ai/ensure")
    def post_local_ai_ensure(
        user: dict = Depends(_auth),
        force: bool = False,
        model: str | None = None,
    ):
        from connections_store import ensure_local_ai_from_ui

        return ensure_local_ai_from_ui(force=force, model=model)

    @app.post("/setup/gmail/credentials")
    async def post_gmail_credentials(
        file: UploadFile = File(...),
        user: dict = Depends(_auth),
    ):
        from connections_store import save_gmail_credentials_json

        raw = await file.read()
        if not raw:
            raise HTTPException(400, "Empty file")
        try:
            return save_gmail_credentials_json(raw)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/setup/gmail/connect")
    def post_gmail_connect(user: dict = Depends(_auth)):
        """Opens a browser for Google sign-in. Blocks until the user finishes."""
        from connections_store import connect_gmail_oauth

        try:
            return connect_gmail_oauth()
        except FileNotFoundError as e:
            raise HTTPException(400, str(e)) from e
        except RuntimeError as e:
            raise HTTPException(500, str(e)) from e
        except Exception as e:
            raise HTTPException(500, f"Google sign-in failed: {e}") from e

    @app.post("/setup/gmail/disconnect")
    def post_gmail_disconnect(user: dict = Depends(_auth)):
        from connections_store import disconnect_gmail_oauth

        return disconnect_gmail_oauth()

    @app.get("/inbox", response_class=HTMLResponse)
    def inbox_ui():
        from api.inbox_ui import render_inbox_html
        return render_inbox_html()

    @app.get("/cv/templates")
    def cv_templates(user: dict = Depends(_auth)):
        from cv.templates import list_templates
        return {"templates": list_templates()}

    @app.get("/cv/status")
    def cv_status(user: dict = Depends(_auth)):
        from config import CV_MD_PATH
        from cv.ats_score import score_ats_readiness
        from store.settings import get_cv_settings

        cv_settings = get_cv_settings(user.get("tenant_id", "default"))
        md = ""
        if os.path.isfile(CV_MD_PATH):
            md = open(CV_MD_PATH, encoding="utf-8").read()
        tpl = cv_settings.get("template_id", "") or ""
        ats = score_ats_readiness(
            md,
            template_id=tpl,
            include_template=bool(tpl),
        )
        from apply.ats_strategies import uploaded_resume_pdf

        from cv.latex_builder import latex_available

        return {
            "cv_settings": cv_settings,
            "has_cv": bool(md.strip()),
            "ats": ats,
            "has_uploaded_pdf": bool(uploaded_resume_pdf()),
            # "" when no engine is installed. The UI says so rather than
            # letting the Chromium fallback quietly produce a different
            # document from the .tex the user can download.
            "latex_engine": latex_available(),
        }

    @app.post("/cv/resume-source")
    def cv_resume_source(body: ResumeSourceBody, user: dict = Depends(_auth)):
        from store.settings import set_cv_settings

        if body.resume_source not in ("uploaded", "generated"):
            raise HTTPException(400, "resume_source must be 'uploaded' or 'generated'")
        updated = set_cv_settings(
            {"resume_source": body.resume_source}, tenant_id=user.get("tenant_id", "default")
        )
        return {"cv_settings": updated}

    @app.get("/cv/content")
    def cv_content(user: dict = Depends(_auth)):
        from config import CV_MD_PATH

        if os.path.isfile(CV_MD_PATH):
            return {"markdown": open(CV_MD_PATH, encoding="utf-8").read()}
        return {"markdown": ""}

    @app.post("/cv/save")
    def cv_save(body: CvSaveBody, user: dict = Depends(_auth)):
        from cv.latex_builder import save_cv_markdown
        from cv.ats_score import score_ats_readiness
        from cv.placeholder import is_placeholder_cv

        path = save_cv_markdown(body.markdown)
        ats = score_ats_readiness(body.markdown, include_template=False)
        store.audit("cv_saved", "cv", user.get("sub", "api"), {"path": path})
        return {
            "path": path,
            "ats": ats,
            "is_placeholder": is_placeholder_cv(body.markdown),
        }

    @app.post("/cv/upload")
    async def cv_upload(
        file: UploadFile = File(...),
        user: dict = Depends(_auth),
    ):
        from cv.ingest import ingest_resume_file
        from cv.ats_score import score_ats_readiness
        from cv.placeholder import is_placeholder_cv
        from cv.profile_extract import extract_profile_fields
        from profile_store import update_target_titles_from_resume

        filename = file.filename or "resume.pdf"
        data = await file.read()
        try:
            result = ingest_resume_file(filename, data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except RuntimeError as e:
            raise HTTPException(503, str(e)) from e

        md = result["markdown"]
        ats = score_ats_readiness(md, include_template=False)
        # Best-effort structured fields to pre-fill the onboarding profile form.
        try:
            extracted = extract_profile_fields(md)
        except Exception:
            extracted = {}
        applied_titles: list[str] = []
        if extracted.get("target_titles"):
            try:
                saved = update_target_titles_from_resume(
                    extracted["target_titles"],
                    extracted=extracted,
                )
                applied_titles = list(saved.get("target_titles") or [])
            except Exception:
                applied_titles = []
        store.audit(
            "cv_uploaded",
            "cv",
            user.get("sub", "api"),
            {
                "format": result["source_format"],
                "chars": result["char_count"],
                "target_titles_applied": applied_titles,
            },
        )
        return {
            **result,
            "ats": ats,
            "is_placeholder": is_placeholder_cv(md),
            "profile": extracted,
            "applied_target_titles": applied_titles,
        }

    @app.post("/cv/generate")
    def cv_generate(body: CvGenerateBody, user: dict = Depends(_auth)):
        from cv.latex_builder import generate_cv_artifacts
        from store.settings import get_cv_settings

        tenant = user.get("tenant_id", "default")
        target = body.page_target or get_cv_settings(tenant).get("page_target") or "auto"
        try:
            result = generate_cv_artifacts(
                template_id=body.template_id,
                md=body.markdown,
                tenant_id=tenant,
                page_target=target,
            )
            store.audit("cv_generated", "cv", body.template_id, {"tex": result.get("tex_path")})
            return result
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))

    @app.post("/cv/preview")
    def cv_preview(body: CvPreviewBody, user: dict = Depends(_auth)):
        from config import CV_MD_PATH
        from cv.preview import SAMPLE_CV, render_cv_html
        from cv.templates import get_template

        if not get_template(body.template_id):
            raise HTTPException(404, f"Unknown template: {body.template_id}")

        md = body.markdown
        if body.markdown is None and not body.use_sample and os.path.isfile(CV_MD_PATH):
            md = open(CV_MD_PATH, encoding="utf-8").read()
        if body.use_sample:
            md = SAMPLE_CV
        elif not (md or "").strip():
            if os.path.isfile(CV_MD_PATH):
                md = open(CV_MD_PATH, encoding="utf-8").read()
            else:
                md = SAMPLE_CV

        html_doc = render_cv_html(
            md or SAMPLE_CV,
            body.template_id,
            single_page=body.single_page,
        )
        return {"html": html_doc, "template_id": body.template_id}

    @app.get("/cv/templates/{template_id}/preview")
    def cv_template_preview(
        template_id: str,
        use_sample: bool = True,
        user: dict = Depends(_auth),
    ):
        from cv.preview import SAMPLE_CV, render_cv_html
        from cv.templates import get_template

        if not get_template(template_id):
            raise HTTPException(404, f"Unknown template: {template_id}")

        from config import CV_MD_PATH

        md = SAMPLE_CV
        if not use_sample and os.path.isfile(CV_MD_PATH):
            md = open(CV_MD_PATH, encoding="utf-8").read()
        html_doc = render_cv_html(md, template_id)
        return {"html": html_doc, "template_id": template_id}

    @app.get("/cv/artifacts")
    def cv_artifacts(user: dict = Depends(_auth)):
        from config import CV_MD_PATH
        from store.settings import get_cv_settings

        cv_settings = get_cv_settings(user.get("tenant_id", "default"))
        tex = cv_settings.get("last_generated_tex")
        pdf = cv_settings.get("last_generated_pdf")
        return {
            "cv_path": CV_MD_PATH if os.path.isfile(CV_MD_PATH) else None,
            "template_id": cv_settings.get("template_id"),
            "tex_path": tex if tex and os.path.isfile(tex) else None,
            "pdf_path": pdf if pdf and os.path.isfile(pdf) else None,
            "has_md": os.path.isfile(CV_MD_PATH),
            "has_tex": bool(tex and os.path.isfile(tex)),
            "has_pdf": bool(pdf and os.path.isfile(pdf)),
            "page_target": cv_settings.get("page_target", "auto"),
            "page_count": cv_settings.get("last_page_count", 0),
            "density": cv_settings.get("last_density"),
        }

    @app.get("/cv/file/{file_type}")
    def cv_file(file_type: str, user: dict = Depends(_auth)):
        from fastapi.responses import FileResponse, HTMLResponse

        from config import CV_MD_PATH
        from cv.preview import render_cv_html
        from store.settings import get_cv_settings

        tenant = user.get("tenant_id", "default")
        cv_settings = get_cv_settings(tenant)

        if file_type == "md":
            if not os.path.isfile(CV_MD_PATH):
                raise HTTPException(404, "cv.md not found")
            return FileResponse(CV_MD_PATH, media_type="text/markdown", filename="cv.md")

        if file_type == "tex":
            path = cv_settings.get("last_generated_tex")
            if not path or not os.path.isfile(path) or not _allowed_cv_path(path):
                raise HTTPException(404, "LaTeX file not found — generate your CV first")
            return FileResponse(path, media_type="application/x-tex", filename=os.path.basename(path))

        if file_type == "pdf":
            path = cv_settings.get("last_generated_pdf")
            if not path or not os.path.isfile(path) or not _allowed_cv_path(path):
                raise HTTPException(404, "PDF not found — generate your CV first (needs Playwright: Connections → Install Playwright)")
            return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))

        if file_type == "uploaded":
            from apply.ats_strategies import uploaded_resume_pdf

            path = uploaded_resume_pdf()
            if not path:
                raise HTTPException(404, "No uploaded resume — upload your PDF first")
            return FileResponse(path, media_type="application/pdf", filename="resume.pdf")

        if file_type == "preview":
            md = ""
            if os.path.isfile(CV_MD_PATH):
                md = open(CV_MD_PATH, encoding="utf-8").read()
            if not md.strip():
                raise HTTPException(404, "No CV content to preview")
            html_doc = render_cv_html(md, cv_settings.get("template_id") or "classic-ats")
            return HTMLResponse(html_doc)

        raise HTTPException(400, "file_type must be md, tex, pdf, uploaded, or preview")

    @app.delete("/cv")
    def cv_delete(user: dict = Depends(_auth)):
        from config import CV_MD_PATH
        from store.settings import set_cv_settings

        removed = False
        if os.path.isfile(CV_MD_PATH):
            os.remove(CV_MD_PATH)
            removed = True
        set_cv_settings(
            {
                "last_generated_tex": None,
                "last_generated_pdf": None,
                "ats_score": 0,
            },
            tenant_id=user.get("tenant_id", "default"),
        )
        store.audit("cv_deleted", "cv", user.get("sub", "api"), {})
        return {"deleted": removed}

    @app.get("/settings/automation")
    def get_automation(user: dict = Depends(_auth)):
        from store.settings import get_automation_settings
        from scheduler.scan_scheduler import scan_is_due

        settings = get_automation_settings(user.get("tenant_id", "default"))
        settings["scan_due"] = scan_is_due(user.get("tenant_id", "default"))
        return settings

    @app.post("/settings/automation")
    def post_automation(body: AutomationSettingsBody, user: dict = Depends(_auth)):
        from store.settings import set_automation_settings

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        return set_automation_settings(updates, tenant_id=user.get("tenant_id", "default"))

    @app.post("/scan/scheduled")
    def run_scheduled_scan_endpoint(
        dry_run: bool = False,
        async_run: bool = False,
        user: dict = Depends(_auth),
    ):
        if async_run:
            task_id = store.enqueue_task(
                "scheduled_scan",
                {"tenant_id": user.get("tenant_id", "default"), "dry_run": dry_run},
            )
            return {"enqueued": task_id}
        from scheduler.scan_scheduler import run_scheduled_scan

        return run_scheduled_scan(tenant_id=user.get("tenant_id", "default"), dry_run=dry_run)

    @app.post("/jobs/discover")
    def discover(
        req: DiscoverRequest,
        async_run: bool = False,
        user: dict = Depends(_auth),
    ):
        from orchestrator.discovery import discover_and_filter, persist_discovered

        store.init_db()
        if async_run:
            task_id = store.enqueue_task("discover", {"dry_run": req.dry_run})
            store.audit("api_discover_enqueue", "worker_queue", str(task_id), {"user": user.get("sub")})
            import threading
            threading.Thread(
                target=lambda: __import__("workers.discovery_worker", fromlist=["process_pending"]).process_pending(),
                daemon=True,
                name="discover-immediate",
            ).start()
            return {"enqueued": task_id, "dry_run": req.dry_run}

        run_id = store.start_run(dry_run=req.dry_run)
        passed, rejected, stats = discover_and_filter(log_totals=True)
        if not req.dry_run:
            # User DB only gets profile keepers (relevant + fit floor).
            persist_discovered(passed, run_id)
            from orchestrator.discovery import enrich_thin_matching_jobs
            from scheduler.scan_scheduler import record_scan_result

            stats["jd_enrich"] = enrich_thin_matching_jobs()
            # Same follow-up the orchestrator does. Enrichment only re-scores
            # rows it fetched; a description that arrived by any other route
            # leaves the job scored as though it had none — 69 jobs on a real
            # inbox held a full JD and still read "JD not fetched yet", pinned
            # at 60, which is also why strong_fit was always zero.
            try:
                from processors.enrich_jd import rescore_fetched_jobs

                stats["jd_rescore"] = rescore_fetched_jobs()
            except Exception as exc:
                # This module imports logging inside functions, not at the top,
                # so do the same here rather than leaning on a name that is not
                # actually in scope on the one path this line runs.
                import logging

                logging.getLogger("shortlistr.api").warning(
                    "rescore after discovery failed: %s", exc)
            record_scan_result(stats, added=len(passed))
        from processors.job_filter import count_strong_fit_persisted

        gate = stats.get("persist_gate") or {}
        store.finish_run(
            run_id,
            source_stats=stats,
            discovered=int(gate.get("fetched") or (len(passed) + len(rejected))),
            passed=len(passed),
            strong_fit=count_strong_fit_persisted(passed),
        )
        store.audit("api_discover", "run", run_id, {"user": user.get("sub")})
        return {
            "run_id": run_id,
            "discovered": int(gate.get("fetched") or (len(passed) + len(rejected))),
            "relevant": len(passed),
            "strong_fit": count_strong_fit_persisted(passed),
            "off_target": len(rejected),
            "kept": int(gate.get("kept") or len(passed)),
            "dropped_off_target": int(gate.get("dropped_off_target") or 0),
            "dropped_low_fit": int(gate.get("dropped_low_fit") or 0),
            "stats": stats,
        }

    @app.get("/jobs/discover/status")
    def discover_status(user: dict = Depends(_auth)):
        """Is a scan in flight, and how many jobs exist right now.

        The dashboard polls this instead of re-fetching the whole job list on a
        timer, so a long multi-board scan updates the page without reloading it.
        """
        store.init_db()
        with store.db() as conn:
            # Self-heal: a task whose worker process died stays 'running'
            # forever, and this endpoint is what the Scan button believes. Left
            # alone it spun for a day. Reaping here means simply opening the
            # page clears it, even if no worker loop is alive to do it.
            store.reap_stale_tasks(conn)
            queue = conn.execute(
                """
                SELECT status, COUNT(*) AS c FROM worker_queue
                WHERE task_type = 'discover'
                GROUP BY status
                """
            ).fetchall()
            counts = {str(r["status"]): int(r["c"]) for r in queue}
            last = conn.execute(
                """
                SELECT status, created_at, processed_at FROM worker_queue
                WHERE task_type = 'discover'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            total_jobs = int(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        running = bool(counts.get("running")) or bool(counts.get("pending"))
        return {
            "running": running,
            "queue": counts,
            "last_status": (dict(last).get("status") if last else None),
            "last_started_at": (dict(last).get("created_at") if last else None),
            "last_finished_at": (dict(last).get("processed_at") if last else None),
            "total_jobs": total_jobs,
        }

    @app.post("/jobs/{job_id}/apply-assist")
    def apply_assist_endpoint(
        job_id: str,
        body: ApplyAssistBody,
        user: dict = Depends(_auth),
    ):
        from apply.ats_fill import apply_assist_for_job
        from apply.channels import NotFillableError
        from store.status import StatusError, validate_job_id

        if not body.confirm:
            raise HTTPException(
                403,
                "Apply-assist requires explicit confirmation. "
                "Set confirm=true after reviewing the job.",
            )
        try:
            validate_job_id(job_id)
            report = apply_assist_for_job(job_id, headless=body.headless)
            errors = report.get("errors") or []
            if errors:
                detail = "; ".join(str(e) for e in errors)
                if any("playwright" in str(e).lower() for e in errors):
                    raise HTTPException(503, detail)
                raise HTTPException(422, detail)
            if not report.get("filled"):
                raise HTTPException(
                    422,
                    "No application fields were filled — open the posting manually or run: make resolve-jobs",
                )
            return report
        except NotFillableError as e:
            raise HTTPException(422, str(e))
        except StatusError as e:
            raise HTTPException(400, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.post("/jobs/apply-batch")
    def apply_batch(body: ApplyBatchBody, user: dict = Depends(_auth)):
        """Authorize a batch for guided apply (one confirmation = the F2 gate).

        Approves + queues the selected jobs; the actual per-job pre-fill stays the
        gated /jobs/{id}/apply-assist (which never submits). NOT auto-submit.
        """
        from agent.registry import PermissionDenied, check_permission
        from api.jobs_api import apply_channel_for, prepare_job_for_eval
        from eval.service import evaluate_job_text
        from store.status import StatusError, get_pipeline_row, mark_approved, validate_job_id

        tenant = user.get("tenant_id", "default")
        try:
            check_permission("shortlistr.apply_assist", confirm=body.confirm, tenant_id=tenant)
        except PermissionDenied as e:
            store.audit("tool_denied", "tool", "apply_batch", {"reason": str(e)})
            raise HTTPException(403, str(e))

        store.init_db()
        queued, skipped = [], []
        for jid in body.job_ids:
            try:
                validate_job_id(jid)
                with store.db() as conn:
                    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
                if not row:
                    skipped.append({"job_id": jid, "reason": "not found"})
                    continue
                pipe = get_pipeline_row(jid)
                status_now = pipe["status"] if pipe else None
                # Evaluate-first: bring un-evaluated jobs up to scored before approving.
                if status_now in (None, "pending"):
                    try:
                        jd, company, role, url = prepare_job_for_eval(dict(row))
                        evaluate_job_text(jd, url=url, company=company or "", role=role or "")
                    except Exception as eval_err:
                        skipped.append({"job_id": jid, "reason": f"eval_failed: {eval_err}"})
                        continue
                if status_now in (None, "pending", "evaluated"):
                    mark_approved(jid, actor="apply_batch")
                queued.append({"job_id": jid, "channel": apply_channel_for(dict(row))})
            except (StatusError, ValueError) as e:
                skipped.append({"job_id": jid, "reason": str(e)})
        store.audit("apply_batch", "tenant", tenant, {"queued": len(queued), "skipped": len(skipped)})
        return {"queued": queued, "count": len(queued), "skipped": skipped}

    @app.post("/jobs/{job_id}/mark-submitted")
    def mark_submitted_endpoint(job_id: str, user: dict = Depends(_auth)):
        """Record that the user submitted the application (feeds the outcome loop)."""
        from store.status import StatusError, mark_submitted, validate_job_id

        try:
            validate_job_id(job_id)
            app_id = mark_submitted(job_id, actor=user.get("sub", "user"))
            store.audit("api_mark_submitted", "job", job_id, {"user": user.get("sub")})
            return {"job_id": job_id, "application_id": app_id, "status": "applied"}
        except StatusError as e:
            raise HTTPException(400, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.post("/jobs/{job_id}/send-application")
    def send_application_endpoint(job_id: str, body: SendApplicationBody, user: dict = Depends(_auth)):
        """Email channel: send the personalised cover letter + resume (gated submit)."""
        from agent.registry import PermissionDenied, check_permission
        from processors.cover_letter import generate_cover_letter, generate_subject
        from processors.email_sender import send_application_email
        from store.status import StatusError, mark_submitted, validate_job_id

        tenant = user.get("tenant_id", "default")
        try:
            check_permission("channel.send", confirm=body.confirm, tenant_id=tenant)
        except PermissionDenied as e:
            store.audit("tool_denied", "tool", "send_application", {"job_id": job_id, "reason": str(e)})
            raise HTTPException(403, str(e))
        try:
            validate_job_id(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))

        store.init_db()
        with store.db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        job = dict(row)
        to_email = (job.get("company_email") or "").strip()
        if not to_email:
            raise HTTPException(404, "This job has no company email — use the form channel instead")

        letter = body.body or (generate_cover_letter(job) or {}).get("body", "")
        subject = generate_subject(job)
        from apply.ats_strategies import resolve_resume_pdf

        resume_path = resolve_resume_pdf(job.get("company", ""), tenant, job_id=job_id)
        sent = send_application_email(
            to_email=to_email, subject=subject, body=letter,
            job_id=job_id, company=job.get("company", ""), role=job.get("title", ""),
            cover_letter_text=letter, resume_path=resume_path,
        )
        if not sent:
            raise HTTPException(502, "Email send failed — check Gmail OAuth / app password")
        app_id = mark_submitted(job_id, company=job.get("company", ""), role=job.get("title", ""),
                                actor=user.get("sub", "user"))
        store.audit("send_application", "job", job_id, {"to": to_email})
        return {"sent": True, "job_id": job_id, "application_id": app_id}

    @app.post("/sync/email-routing")
    def sync_email_routing(dry_run: bool = True, user: dict = Depends(_auth)):
        from processors.email_routing import route_from_recruiter_drafts

        routed = route_from_recruiter_drafts(dry_run=dry_run)
        store.audit("email_routing_sync", "tenant", user.get("tenant_id", "default"), {"count": len(routed)})
        return {"routed": routed, "dry_run": dry_run}

    @app.get("/agent/tools")
    def agent_tools(user: dict = Depends(_auth)):
        from connectors.manifest import list_tools

        return {"tools": list_tools()}

    @app.post("/agent/discover")
    def agent_discover(body: AgentDiscoverBody, user: dict = Depends(_auth)):
        return discover(DiscoverRequest(dry_run=body.dry_run), async_run=False, user=user)

    @app.post("/agent/evaluate")
    def agent_evaluate(body: AgentJobBody, user: dict = Depends(_auth)):
        return evaluate_job(body.job_id, user)

    @app.get("/agent/explain/{job_id}")
    def agent_explain(job_id: str, user: dict = Depends(_auth)):
        return explain_job_endpoint(job_id, user)

    @app.post("/agent/queue-apply")
    def agent_queue_apply(body: AgentJobBody, user: dict = Depends(_auth)):
        return set_pipeline_status(
            body.job_id,
            PipelineStatusBody(status="approved"),
            user,
        )

    @app.post("/agent/apply-assist")
    def agent_apply_assist(body: AgentApplyBody, user: dict = Depends(_auth)):
        from agent.registry import PermissionDenied, check_permission

        tenant = user.get("tenant_id", "default")
        try:
            check_permission("shortlistr.apply_assist", confirm=body.confirm, tenant_id=tenant)
        except PermissionDenied as e:
            store.audit("tool_denied", "tool", "shortlistr.apply_assist",
                        {"job_id": body.job_id, "reason": str(e)})
            raise HTTPException(403, str(e))
        store.audit("tool_invoked", "tool", "shortlistr.apply_assist", {"job_id": body.job_id})
        return apply_assist_endpoint(body.job_id, ApplyAssistBody(headless=body.headless), user)

    @app.post("/agent/resolve-jobs")
    def agent_resolve_jobs(body: AgentResolveBody, user: dict = Depends(_auth)):
        from store.enrich import backfill_all_jobs

        store.init_db()
        with store.db() as conn:
            n = backfill_all_jobs(conn, max_jobs=body.limit)
        return {"resolved": n}

    @app.post("/agent/call")
    def agent_call(body: AgentCallBody, user: dict = Depends(_auth)):
        """Unified dispatch for any registered tool (built-in or MCP), gated by F2."""
        from agent.dispatch import call_tool
        from agent.registry import PermissionDenied

        tenant = user.get("tenant_id", "default")
        try:
            result = call_tool(body.name, body.args, confirm=body.confirm, tenant_id=tenant)
        except PermissionDenied as e:
            store.audit("tool_denied", "tool", body.name, {"reason": str(e)})
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))
        store.audit("tool_invoked", "tool", body.name, {"via": "agent_call"})
        return {"tool": body.name, "result": result}

    @app.post("/agent/chat")
    def agent_chat(body: AgentChatBody, user: dict = Depends(_auth)):
        """Conversational control — answers + gated tool calls (CH1 core)."""
        from agent.chat import chat as chat_core

        tenant = user.get("tenant_id", "default")
        result = chat_core(
            body.message,
            body.history,
            tenant_id=tenant,
            confirm_tool=body.confirm_tool,
            confirm_args=body.confirm_args,
        )
        store.audit("agent_chat", "tool", "chat", {"message": (body.message or "")[:120]})
        return result

    @app.get("/jobs")
    def list_jobs(
        status: str = "inbox",
        resolve: bool = False,
        relevance: str = "relevant",
        offset: int = 0,
        user: dict = Depends(_auth),
    ):
        from api.jobs_api import fetch_jobs

        try:
            store.init_db()
            with store.db() as conn:
                return fetch_jobs(
                    conn,
                    status=status,
                    offset=offset,
                    resolve_missing=resolve,
                    slim=True,
                    relevance=relevance,
                )
        except HTTPException:
            raise
        except sqlite3.OperationalError as e:
            # Mid-scan writers briefly lock SQLite; one retry after a short wait.
            if "locked" in str(e).lower():
                import time

                time.sleep(0.35)
                try:
                    with store.db() as conn:
                        return fetch_jobs(
                            conn,
                            status=status,
                            offset=offset,
                            resolve_missing=resolve,
                            slim=True,
                            relevance=relevance,
                        )
                except Exception:
                    pass
            import logging
            import traceback

            logging.getLogger(__name__).error(
                "list_jobs failed: %s\n%s", e, traceback.format_exc()
            )
            raise HTTPException(
                503,
                detail="Database busy (scan in progress). Retry in a moment.",
            ) from e
        except Exception as e:
            import logging
            import traceback

            logging.getLogger(__name__).error(
                "list_jobs failed: %s\n%s", e, traceback.format_exc()
            )
            raise HTTPException(
                500,
                detail=f"Could not load jobs: {e}. Try restarting Shortlistr; if it persists, check data/shortlistr.db migrations.",
            ) from e

    @app.get("/jobs/{job_id}")
    def get_job(
        job_id: str,
        resolve: bool = False,
        user: dict = Depends(_auth),
    ):
        from api.jobs_api import fetch_job
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        store.init_db()
        with store.db() as conn:
            job = fetch_job(conn, job_id, resolve_missing=resolve)
        if not job:
            raise HTTPException(404, "Job not found")
        return job

    @app.post("/jobs/{job_id}/evaluate")
    def evaluate_job(job_id: str, user: dict = Depends(_auth)):
        from api.jobs_api import fetch_job, prepare_job_for_eval
        from eval.explain import explain_job
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))

        store.init_db()
        with store.db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")

        try:
            jd, company, role, url = prepare_job_for_eval(dict(row))
            from eval.service import evaluate_job_text

            result = evaluate_job_text(jd, url=url, company=company or "", role=role or "", job_id=job_id)
            store.audit("api_evaluate", "job", job_id, {"user": user.get("sub"), "score": result.score})

            payload = result.to_dict()
            try:
                payload["explain"] = explain_job(job_id)
            except Exception:
                pass

            with store.db() as conn:
                payload["job"] = fetch_job(conn, job_id)
            return payload
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Evaluation failed: {e}") from e

    @app.get("/jobs/{job_id}/explain")
    def explain_job_endpoint(job_id: str, user: dict = Depends(_auth)):
        from eval.explain import explain_job
        from store.status import StatusError, validate_job_id
        try:
            validate_job_id(job_id)
            return explain_job(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))

    def _prep_after_approve(job_id: str) -> None:
        """Best-effort prep for a freshly approved job.

        The dashboard asks for prep itself right after approving, but approvals
        also arrive from the chat agent, scripts and curl — and mark_approved is
        only a status write, so those used to leave a role with no materials.
        ensure_prep_bundle is idempotent and locked, so running from both ends
        costs nothing when the client already did the work.

        Runs after the response: generation calls an LLM, and approving must not
        block on it.
        """
        try:
            from api.prep_bundle import ensure_prep_bundle

            ensure_prep_bundle(job_id)
        except Exception as e:  # never surface into the approve call
            import logging

            logging.getLogger("shortlistr.api").warning(
                "Background prep for %s failed: %s", job_id, e)

    @app.post("/jobs/{job_id}/pipeline-status")
    def set_pipeline_status(
        job_id: str,
        body: PipelineStatusBody,
        background: BackgroundTasks,
        user: dict = Depends(_auth),
    ):
        from store.status import StatusError, mark_approved, mark_skipped, transition_pipeline, validate_job_id
        try:
            validate_job_id(job_id)
            st = body.status.strip().lower()
            if st == "approved":
                result = mark_approved(job_id, actor=user.get("sub", "api"))
                background.add_task(_prep_after_approve, job_id)
            elif st in ("skipped", "skip"):
                result = mark_skipped(job_id, actor=user.get("sub", "api"))
            elif st in ("pending", "evaluated"):
                result = transition_pipeline(job_id, st, actor=user.get("sub", "api"), reason="user_undo")
            else:
                raise HTTPException(400, "status must be approved, skipped, pending, or evaluated")
            store.audit("api_pipeline_status", "job", job_id, {"status": st, "user": user.get("sub")})
            return result
        except StatusError as e:
            raise HTTPException(400, str(e))

    @app.get("/jobs/{job_id}/diff")
    def job_diff(job_id: str, user: dict = Depends(_auth)):
        from prep.diff import compute_diff
        from store.status import StatusError, validate_job_id
        try:
            validate_job_id(job_id)
            return compute_diff(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.get("/prep")
    def list_prep(limit: int = 100, user: dict = Depends(_auth)):
        """Company cards for the Prep sidebar page — approved/submitted roles."""
        from api.prep_bundle import list_prep_summaries

        return {"items": list_prep_summaries(limit=limit)}

    @app.get("/jobs/{job_id}/prep")
    def job_prep(job_id: str, user: dict = Depends(_auth)):
        from api.prep_bundle import get_prep_bundle
        from store.status import StatusError, validate_job_id
        try:
            validate_job_id(job_id)
            return get_prep_bundle(job_id, generate=False)
        except StatusError as e:
            raise HTTPException(400, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.post("/jobs/{job_id}/prep/ensure")
    def job_prep_ensure(job_id: str, user: dict = Depends(_auth)):
        """Generate prep only if it is missing. Used by the approve flow.

        Distinct from /prep/generate, which always regenerates — that is what
        the Regenerate button means, and approving should not throw away a
        cover letter the user has already edited.
        """
        from api.prep_bundle import ensure_prep_bundle
        from store.status import StatusError, validate_job_id
        try:
            validate_job_id(job_id)
            return ensure_prep_bundle(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.post("/jobs/{job_id}/prep/generate")
    def job_prep_generate(job_id: str, user: dict = Depends(_auth)):
        from api.prep_bundle import generate_prep_bundle
        from store.status import StatusError, validate_job_id
        try:
            validate_job_id(job_id)
            return generate_prep_bundle(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.patch("/jobs/{job_id}/prep/cover-letter")
    def job_prep_cover_letter(
        job_id: str,
        body: PrepCoverLetterBody,
        user: dict = Depends(_auth),
    ):
        from store.prep_drafts import save_cover_letter_draft
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
            save_cover_letter_draft(
                job_id,
                body.body,
                tenant_id=user.get("tenant_id", "default"),
            )
            store.audit("prep_cover_saved", "job", job_id, {"actor": user.get("sub")})
            return {"saved": True, "job_id": job_id}
        except StatusError as e:
            raise HTTPException(400, str(e))

    @app.patch("/jobs/{job_id}/prep/reach-out/contacts")
    def job_prep_reach_out_contacts(
        job_id: str,
        body: PrepReachOutContactsBody,
        user: dict = Depends(_auth),
    ):
        """Save user-added Reach out contacts (merged with JD extracts on read)."""
        from prep.reach_out import normalize_user_contact
        from store.prep_drafts import save_reach_out_contacts
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
            contacts = []
            for raw in body.contacts:
                n = normalize_user_contact(raw.model_dump())
                if n:
                    contacts.append(n)
            save_reach_out_contacts(
                job_id,
                contacts,
                tenant_id=user.get("tenant_id", "default"),
            )
            store.audit(
                "prep_reach_out_contacts_saved",
                "job",
                job_id,
                {"actor": user.get("sub"), "count": len(contacts)},
            )
            return {"saved": True, "job_id": job_id, "count": len(contacts)}
        except StatusError as e:
            raise HTTPException(400, str(e))

    @app.patch("/jobs/{job_id}/prep/reach-out/outreach")
    def job_prep_outreach_draft(
        job_id: str,
        body: PrepOutreachDraftBody,
        user: dict = Depends(_auth),
    ):
        from store.prep_drafts import save_outreach_draft
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
            save_outreach_draft(
                job_id,
                body.body,
                tenant_id=user.get("tenant_id", "default"),
            )
            store.audit("prep_outreach_saved", "job", job_id, {"actor": user.get("sub")})
            return {"saved": True, "job_id": job_id}
        except StatusError as e:
            raise HTTPException(400, str(e))

    @app.get("/jobs/{job_id}/cv-pdf")
    def job_cv_pdf(job_id: str, user: dict = Depends(_auth)):
        from fastapi.responses import FileResponse
        from apply.ats_strategies import find_cv_pdf
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        store.init_db()
        with store.db() as conn:
            row = conn.execute("SELECT company FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        path = find_cv_pdf(str(row["company"] or ""), job_id=job_id)
        if not path or not os.path.isfile(path) or not _allowed_cv_path(path):
            raise HTTPException(404, "No CV PDF yet — generate prep materials first")
        return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))

    @app.get("/reports")
    def list_reports(user: dict = Depends(_auth)):
        rdir = os.path.join(SHORTLISTR_ROOT, "reports")
        if not os.path.isdir(rdir):
            return {"reports": []}
        files = sorted((f for f in os.listdir(rdir) if f.endswith(".md")), reverse=True)
        return {"reports": files}

    @app.get("/reports/{name}")
    def get_report(name: str, user: dict = Depends(_auth)):
        from fastapi.responses import FileResponse

        if "/" in name or ".." in name or not name.endswith(".md"):
            raise HTTPException(400, "Invalid report name")
        path = os.path.join(SHORTLISTR_ROOT, "reports", name)
        if not os.path.isfile(path) or not _allowed_cv_path(path):
            raise HTTPException(404, "Report not found")
        return FileResponse(path, media_type="text/markdown", filename=name)

    @app.get("/tracker/board")
    def tracker_board(relevance: str = "relevant", user: dict = Depends(_auth)):
        from api.tracker_board import fetch_tracker_board

        store.init_db()
        with store.db() as conn:
            return fetch_tracker_board(conn, relevance=relevance)

    @app.post("/evaluations/repair")
    def evaluations_repair(limit: int = 100, user: dict = Depends(_auth)):
        """Repair evaluations that fell back to the heuristic during an outage.

        Not under /jobs/: that prefix has a `{job_id}` route, which claims any
        static sibling declared after it and answers "Invalid job_id format".

        They are stored exactly like real ones, so without this a score produced
        while the AI was unreachable is indistinguishable from a judged one.
        """
        from scheduler.scan_scheduler import reevaluate_stale

        store.init_db()
        return reevaluate_stale(limit=limit)

    @app.get("/evaluations/stale")
    def evaluations_stale(user: dict = Depends(_auth)):
        from scheduler.scan_scheduler import stale_template_evals

        store.init_db()
        ids = stale_template_evals()
        return {"count": len(ids), "job_ids": ids[:200]}

    @app.get("/tracker/follow-ups")
    def tracker_follow_ups(
        include_resolved: bool = False, user: dict = Depends(_auth)
    ):
        """Applications the mailbox says are waiting on you.

        Separate from /tracker/board because the board is job-centric, and the
        case this exists for — an application made outside the tool — has no job
        row to join against.
        """
        from store import follow_ups

        store.init_db()
        return {
            "follow_ups": follow_ups.list_follow_ups(include_resolved=include_resolved),
            "open": follow_ups.open_count(),
        }

    @app.post("/tracker/follow-ups/{follow_up_id}/resolve")
    def tracker_resolve_follow_up(follow_up_id: int, user: dict = Depends(_auth)):
        from store import follow_ups

        store.init_db()
        try:
            return follow_ups.resolve_follow_up(follow_up_id, actor=user.get("sub", "user"))
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/tracker/follow-ups/{follow_up_id}/reopen")
    def tracker_reopen_follow_up(follow_up_id: int, user: dict = Depends(_auth)):
        from store import follow_ups

        store.init_db()
        return follow_ups.reopen_follow_up(follow_up_id, actor=user.get("sub", "user"))

    @app.post("/sync/export-tracker")
    def sync_export_tracker(user: dict = Depends(_auth)):
        """Export SQLite pipeline + applications to markdown files."""
        from store.export import export_applications, export_pipeline
        _require_owner(user)
        pipeline_path = export_pipeline()
        apps_path = export_applications()
        store.audit("sync_export", "tenant", user.get("tenant_id", "default"), {})
        return {"pipeline": pipeline_path, "applications": apps_path}

    @app.post("/portals/fingerprint")
    def portals_fingerprint(body: PortalsFingerprintBody, user: dict = Depends(_auth)):
        """Detect public ATS boards from careers URLs (preview only)."""
        from sources.ats_fingerprint import propose_from_urls

        urls = [u.strip() for u in (body.urls or []) if str(u).strip()]
        if not urls:
            raise HTTPException(400, "Provide at least one careers URL")
        if len(urls) > 25:
            raise HTTPException(400, "Max 25 URLs per scan")
        proposals = propose_from_urls(urls, company_name=body.company_name or "")
        return {"proposals": proposals}

    @app.post("/portals/fingerprint/apply")
    def portals_fingerprint_apply(body: PortalsApplyBody, user: dict = Depends(_auth)):
        """Merge confirmed ATS detections into portals.yml (additive)."""
        _require_owner(user)
        from sources.ats_fingerprint import apply_proposals

        result = apply_proposals(list(body.proposals or []))
        store.audit("portals_fingerprint_apply", "portals", "yml", result)
        return result

    @app.post("/jobs/{job_id}/prep/reach-out/suggest-emails")
    def suggest_reach_out_emails(
        job_id: str,
        body: SuggestEmailsBody,
        user: dict = Depends(_auth),
    ):
        """Permute work emails for a named contact. Verify only with Connections key."""
        from contacts.email_find import suggest_for_contact
        from secrets_store import get_secret
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))

        # Only for approved / evaluated pipeline rows — never blast cold lists.
        with store.db() as conn:
            row = conn.execute(
                "SELECT status FROM pipeline WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        status = str((row["status"] if row else "") or "").lower()
        if status not in ("approved", "evaluated", "submitted", "responded", "interview"):
            raise HTTPException(
                400,
                "Suggest emails only after the role is evaluated or approved — not from Discover.",
            )

        job: dict = {}
        with store.db() as conn:
            jrow = conn.execute(
                "SELECT company FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if jrow:
                job = dict(jrow)
        company = (body.company or job.get("company") or "").strip()
        name = (body.name or "").strip()
        if not name:
            raise HTTPException(400, "A contact name is required")

        api_key = ""
        provider = "hunter"
        try:
            from connections_store import get_connections_for_ui

            ev = get_connections_for_ui().get("email_verify") or {}
            provider = str(ev.get("provider") or "hunter")
            if body.verify and ev.get("api_key_set"):
                api_key = get_secret("SHORTLISTR_EMAIL_VERIFY_API_KEY") or ""
        except Exception:
            pass

        suggestions = suggest_for_contact(
            name,
            company,
            domain=body.domain or "",
            website=body.website or "",
            verify=bool(body.verify and api_key),
            api_key=api_key,
            provider=provider,
        )
        return {
            "job_id": job_id,
            "suggestions": suggestions,
            "verified": bool(body.verify and api_key),
            "note": "Candidates only — review before adding. Never auto-sent.",
        }

    @app.post("/jobs/{job_id}/prep/reach-out/resolve")
    def resolve_job_contact_endpoint(
        job_id: str,
        body: ContactResolveBody | None = None,
        user: dict = Depends(_auth),
    ):
        """Waterfall: domain → person → email candidates + confidence (never sends)."""
        from contacts.resolve import resolve_job_contact
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        opts = body or ContactResolveBody()
        try:
            return resolve_job_contact(
                job_id,
                use_serp=opts.use_serp,
                use_github=opts.use_github,
                verify=opts.verify,
            )
        except ValueError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(500, f"Contact resolve failed: {e}")

    @app.get("/jobs/{job_id}/prep/reach-out/resolve")
    def get_job_contact_resolution(job_id: str, user: dict = Depends(_auth)):
        from store.contact_resolution import get_job_resolution
        from store.status import StatusError, validate_job_id

        try:
            validate_job_id(job_id)
        except StatusError as e:
            raise HTTPException(400, str(e))
        data = get_job_resolution(job_id)
        if not data:
            return {"job_id": job_id, "status": "none", "people": [], "emails": []}
        return data

    @app.post("/export/instantly-csv")
    def export_instantly_csv(body: InstantlyExportBody, user: dict = Depends(_auth)):
        """Download Instantly-compatible CSV. You import it — we never auto-send."""
        from export.instantly_csv import rows_from_contacts, to_csv
        from fastapi.responses import Response
        from prep.reach_out import build_reach_out
        from store.prep_drafts import get_reach_out_saved

        contacts: list[dict] = list(body.contacts or [])
        company = body.company or ""
        personalization = body.personalization or ""
        if body.job_id and not contacts:
            with store.db() as conn:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE id = ?", (body.job_id,)
                ).fetchone()
            if not row:
                raise HTTPException(404, "Job not found")
            job = dict(row)
            company = company or str(job.get("company") or "")
            saved = get_reach_out_saved(body.job_id)
            built = build_reach_out(
                job,
                user_contacts=saved.get("contacts"),
                outreach_draft=saved.get("outreach_draft"),
            )
            contacts = list(built.get("contacts") or [])
            if not personalization:
                personalization = str(built.get("outreach_draft") or "")[:400]
        rows = rows_from_contacts(
            contacts, company=company, personalization=personalization
        )
        if not rows:
            raise HTTPException(400, "No contacts with email addresses to export")
        csv_text = to_csv(rows)
        store.audit(
            "instantly_csv_export",
            "export",
            body.job_id or "manual",
            {"rows": len(rows)},
        )
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="instantly-leads.csv"'
            },
        )

    @app.get("/jobs/{job_id}/receipts")
    def job_receipts(job_id: str, user: dict = Depends(_auth)):
        from store.receipts import ReceiptError, list_receipts_for_job
        from store.status import StatusError, validate_job_id
        try:
            validate_job_id(job_id)
            return list_receipts_for_job(job_id)
        except (StatusError, ReceiptError) as e:
            raise HTTPException(400, str(e))

    @app.get("/pipeline/stats")
    def pipeline_stats(user: dict = Depends(_auth)):
        store.init_db()
        from store.status import application_status_counts, pipeline_status_counts
        return {
            "pipeline": store.pipeline_breakdown(),
            # Same gate as the default job views, so headline counts match what
            # the user can actually open.
            "pipeline_targeted": pipeline_status_counts(targeted=True),
            "applications": application_status_counts(),
        }

    @app.get("/outcomes/insights")
    def outcomes_insights(user: dict = Depends(_auth)):
        """Outcome rates + active learnings — what's working / what to avoid."""
        store.init_db()
        from memory.store import search_learnings
        from store.status import application_status_counts

        tenant = user.get("tenant_id", "default")
        learnings = [
            l for l in search_learnings("", limit=200, tenant_id=tenant)
            if str(l.get("key", "")).startswith("outcome:")
        ]
        return {"rates": application_status_counts(), "learnings": learnings}

    @app.get("/applications")
    def applications(user: dict = Depends(_auth)):
        from store.enrich import is_placeholder
        from store.queries import LATEST_EVAL_JOIN_ON_APPLICATIONS

        store.init_db()
        with store.db() as conn:
            rows = conn.execute(
                f"""
                SELECT a.*,
                       j.company AS job_company,
                       j.title AS job_title,
                       j.url AS job_url,
                       ev.eval_score,
                       ev.eval_legitimacy
                FROM applications a
                LEFT JOIN jobs j ON j.id = a.job_id
                {LATEST_EVAL_JOIN_ON_APPLICATIONS}
                ORDER BY a.id DESC LIMIT 100
                """
            ).fetchall()
        out = []

        for r in rows:
            d = dict(r)
            if is_placeholder(d.get("company")) and d.get("job_company"):
                d["company"] = d["job_company"]
            if is_placeholder(d.get("role")) and d.get("job_title"):
                d["role"] = d["job_title"]
            if d.get("score") is None and d.get("eval_score") is not None:
                d["score"] = d["eval_score"]
            d.pop("job_company", None)
            d.pop("job_title", None)
            out.append(d)
        return out

    @app.get("/tenant/export")
    def export_tenant(user: dict = Depends(_auth)):
        _require_owner(user)
        from tools.bundle import export_bundle
        path = export_bundle()
        store.audit("gdpr_export", "tenant", user.get("tenant_id", "default"), {})
        return {"bundle": path}

    @app.delete("/tenant/data")
    def delete_tenant_data(user: dict = Depends(_auth)):
        _require_owner(user)
        db_file = os.path.join(DATA_DIR, "shortlistr.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        store.audit("gdpr_delete", "tenant", user.get("tenant_id", "default"), {})
        return {"deleted": True}

    @app.get("/audit")
    def audit_log(limit: int = 50, user: dict = Depends(_auth)):
        _require_owner(user)
        store.init_db()
        with store.db() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    from api.linkedin_optimizer import register_linkedin_optimizer_routes

    register_linkedin_optimizer_routes(app, auth_dep=Depends(_auth))

    return app


def main():
    import uvicorn

    # Loopback only: this is a single-user local tool with no per-user identity
    # (see _auth). Nothing here should be reachable off this machine.
    host = "127.0.0.1"
    port = int(os.environ.get("SHORTLISTR_API_PORT", "8787"))
    reload = os.environ.get("SHORTLISTR_API_RELOAD", "").lower() in ("1", "true", "yes")

    if reload:
        # Dev mode: auto-restart on code changes so edits don't silently serve
        # stale code. uvicorn's reloader spawns a fresh subprocess and imports
        # the app by string, so it needs the automation/ dir importable there —
        # pass it via PYTHONPATH + reload_dirs (the parent's sys.path tweak in
        # cli.py does not carry into the reloader subprocess).
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.environ["PYTHONPATH"] = base + os.pathsep + os.environ.get("PYTHONPATH", "")
        uvicorn.run(
            "api.main:create_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
            reload_dirs=[base],
        )
    else:
        uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
