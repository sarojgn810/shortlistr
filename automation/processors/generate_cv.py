"""
shortlistr — apply-time CV PDF generator.

Compiles the user's cv.md through the same LaTeX pipeline as the Resume page,
with the same template and the same page target, so the PDF an employer
receives is the document the user reviewed and approved. Falls back to the
HTML renderer only when no LaTeX engine is installed.

That fallback used to be the *only* path here, which meant the résumé the user
downloaded and the résumé actually attached to an application were rendered by
two different engines from two different layout systems — same words, visibly
different document, and nothing in the UI said so.

Output: output/{Company}-{YYYY-MM-DD}.pdf
Called by apply_queue.submit_approved(), apply/ats_fill.py, and api/prep_bundle.py.
"""

import logging
import os
import re
from datetime import datetime

from config import CV_MD_PATH, OUTPUT_DIR

logger = logging.getLogger(__name__)


def _read_cv_md() -> str:
    if not os.path.exists(CV_MD_PATH):
        logger.warning(f"cv.md not found at {CV_MD_PATH}")
        return ""
    with open(CV_MD_PATH, encoding="utf-8") as f:
        return f.read()


def _cv_preferences() -> tuple[str, str]:
    """(template_id, page_target) as chosen on the Resume page."""
    try:
        from store.settings import get_cv_settings

        settings = get_cv_settings()
        return (settings.get("template_id") or "ats-single",
                settings.get("page_target") or "auto")
    except Exception:
        return "ats-single", "auto"


def generate_cv_for_job(job: dict) -> dict:
    """
    Generate a CV PDF for a single job using the user's selected template.

    Returns:
        {"success": bool, "path": str, "html_path": str, "error": str}
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    md = _read_cv_md()
    if not md.strip():
        return {"success": False, "path": "", "error": "cv.md is empty — complete onboarding first"}

    template_id, page_target = _cv_preferences()
    company = re.sub(r"[^\w\s-]", "", job.get("company", "Company")).strip().replace(" ", "_") or "Company"
    date_str = datetime.now().strftime("%Y-%m-%d")
    job_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(job.get("job_id") or job.get("id") or ""))[:64]
    basename = f"{job_id}-{company}-{date_str}" if job_id else f"{company}-{date_str}"
    html_path = os.path.join(OUTPUT_DIR, f"{basename}.html")
    pdf_path = os.path.join(OUTPUT_DIR, f"{basename}.pdf")
    tex_path = os.path.join(OUTPUT_DIR, f"{basename}.tex")

    try:
        from cv.latex_builder import fit_to_pages, latex_available

        if latex_available():
            fit = fit_to_pages(md, template_id, tex_path, pdf_path,
                               page_target=page_target)
            if fit.get("ok"):
                logger.info(f"CV PDF -> {pdf_path} "
                            f"({template_id}, {fit['pages']}p, {fit.get('density_name')})")
                _record(job, tex_path, pdf_path)
                return {"success": True, "path": pdf_path, "tex_path": tex_path,
                        "pages": fit.get("pages")}
            logger.warning(f"LaTeX compile failed ({fit.get('error')}); using HTML renderer")

        from cv.preview import render_cv_html
        from generate_pdf import generate_pdf_from_html

        html_doc = render_cv_html(md, template_id, single_page=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_doc)
        generate_pdf_from_html(html_doc, pdf_path, fmt="A4", full_sheet=True)
    except Exception as e:
        # Keep the HTML so the user can print-to-PDF manually if Chromium is unavailable.
        logger.warning(f"CV PDF render failed ({e}); HTML at {html_path}")
        return {
            "success": False,
            "path": html_path if os.path.isfile(html_path) else "",
            "error": f"PDF render failed; HTML available for manual export ({e})",
        }

    _record(job, html_path, pdf_path)
    logger.info(f"CV PDF -> {pdf_path} (template: {template_id}, html renderer)")
    return {"success": True, "path": pdf_path, "html_path": html_path}


def _record(job: dict, source_path: str, pdf_path: str) -> None:
    """Pointer for the résumé diff / prep layer. Never fatal."""
    try:
        from models.job import job_id_from_url
        from prep.diff import record_tailored_artifact

        url = job.get("url") or ""
        if url:
            record_tailored_artifact(job_id_from_url(url), source_path, pdf_path)
    except Exception:
        pass


def generate_cv_batch(jobs: list[dict]) -> list[dict]:
    """Generate CV PDFs for a list of approved jobs."""
    results = []
    for job in jobs:
        result = generate_cv_for_job(job)
        result["job"] = job
        results.append(result)
    return results


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Generate CV PDF for a job")
    parser.add_argument("--company", default="Company", help="Company name")
    parser.add_argument("--role", default="", help="Role title")
    parser.add_argument("--url", default="", help="Job URL (optional)")
    args = parser.parse_args()

    job = {"company": args.company, "title": args.role, "url": args.url}
    result = generate_cv_for_job(job)
    if result["success"]:
        print(f"Generated: {result['path']}")
    else:
        print(f"Failed: {result.get('error', '')}")
