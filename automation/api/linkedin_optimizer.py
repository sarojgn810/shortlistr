"""LinkedIn Profile Optimizer API routes."""

from __future__ import annotations

from typing import Any, Optional

try:
    from fastapi import HTTPException
    from pydantic import BaseModel
except ImportError:  # pragma: no cover
    BaseModel = object  # type: ignore
    HTTPException = Exception  # type: ignore


class LinkedInAnalyzeBody(BaseModel):
    text: Optional[str] = None
    profile: Optional[dict[str, Any]] = None
    target_role: str = "sre"
    linkedin_url: Optional[str] = None


class LinkedInRewriteBody(BaseModel):
    section: str
    profile: Optional[dict[str, Any]] = None
    target_role: str = "sre"
    use_llm: bool = False


class LinkedInRewriteAllBody(BaseModel):
    profile: Optional[dict[str, Any]] = None
    target_role: str = "sre"
    use_llm: bool = False


class LinkedInSaveBody(BaseModel):
    profile: dict[str, Any]
    target_role: str = "sre"


class LinkedInCoverBody(BaseModel):
    theme_id: str = "ink_lime"
    name: str = ""
    headline: str = ""
    subline: str = ""


class LinkedInImportUrlBody(BaseModel):
    url: Optional[str] = None
    target_role: str = "sre"


class LinkedInImportCvBody(BaseModel):
    target_role: Optional[str] = None


def register_linkedin_optimizer_routes(app, *, auth_dep) -> None:
    @app.get("/linkedin/optimizer/roles")
    def linkedin_roles(user: dict = auth_dep):
        from linkedin_optimizer.roles import list_roles

        return {"roles": list_roles()}

    @app.get("/linkedin/optimizer/state")
    def linkedin_state(user: dict = auth_dep):
        from linkedin_optimizer import get_state

        return get_state()

    @app.post("/linkedin/optimizer/analyze")
    def linkedin_analyze(body: LinkedInAnalyzeBody, user: dict = auth_dep):
        from linkedin_optimizer import analyze

        if not (body.text or body.profile):
            raise HTTPException(400, "Provide pasted text or a structured profile")
        return analyze(
            text=body.text,
            profile=body.profile,
            target_role=body.target_role or "sre",
            linkedin_url=body.linkedin_url,
        )

    @app.post("/linkedin/optimizer/import-cv")
    def linkedin_import_cv(body: LinkedInImportCvBody, user: dict = auth_dep):
        from linkedin_optimizer import import_from_cv

        out = import_from_cv(target_role=body.target_role)
        if not out.get("ok"):
            raise HTTPException(400, out.get("error") or "CV import failed")
        return out

    @app.post("/linkedin/optimizer/import-url")
    def linkedin_import_url(body: LinkedInImportUrlBody, user: dict = auth_dep):
        from linkedin_optimizer import import_from_url

        out = import_from_url(body.url, target_role=body.target_role or "sre")
        # 400 only when URL missing; login-wall returns 200 with ok=false so UI can offer CV
        if out.get("needs_url"):
            raise HTTPException(400, out.get("error") or "LinkedIn URL required")
        return out

    @app.post("/linkedin/optimizer/rewrite")
    def linkedin_rewrite(body: LinkedInRewriteBody, user: dict = auth_dep):
        from linkedin_optimizer import rewrite

        return rewrite(
            section=body.section,
            profile=body.profile,
            target_role=body.target_role or "sre",
            use_llm=bool(body.use_llm),
        )

    @app.post("/linkedin/optimizer/rewrite-all")
    def linkedin_rewrite_all(body: LinkedInRewriteAllBody, user: dict = auth_dep):
        from linkedin_optimizer import rewrite_all

        return rewrite_all(
            profile=body.profile,
            target_role=body.target_role or "sre",
            use_llm=bool(body.use_llm),
        )

    @app.post("/linkedin/optimizer/save")
    def linkedin_save(body: LinkedInSaveBody, user: dict = auth_dep):
        from linkedin_optimizer import save_state

        return save_state(body.profile, body.target_role or "sre")

    @app.get("/linkedin/optimizer/cover/themes")
    def linkedin_cover_themes(user: dict = auth_dep):
        from linkedin_optimizer.cover import list_themes

        return {"themes": list_themes()}

    @app.post("/linkedin/optimizer/cover/render")
    def linkedin_cover_render(body: LinkedInCoverBody, user: dict = auth_dep):
        from linkedin_optimizer import render_cover

        return render_cover(body.model_dump() if hasattr(body, "model_dump") else body.dict())
