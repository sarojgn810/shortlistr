"""ATS-specific apply-assist selectors (Greenhouse / Lever / Ashby)."""

from __future__ import annotations

import glob
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


def uploaded_resume_pdf() -> str | None:
    """The user's original uploaded resume saved at repo root (cv.ingest)."""
    import config

    path = os.path.join(config.SHORTLISTR_ROOT, "resume.pdf")
    return path if os.path.isfile(path) else None


def resolve_resume_pdf(company: str = "", tenant_id: str = "default") -> str | None:
    """Pick the resume to send, honoring cv_settings.resume_source.

    "uploaded" -> the user's original resume.pdf as-is (fallback: tailored).
    "generated" -> latest tailored template PDF (fallback: uploaded original).
    """
    try:
        from store.settings import get_cv_settings

        source = get_cv_settings(tenant_id).get("resume_source", "uploaded")
    except Exception:
        source = "uploaded"

    uploaded = uploaded_resume_pdf()
    tailored = find_cv_pdf(company)
    if source == "generated":
        return tailored or uploaded
    return uploaded or tailored

_RESUME_SELECTORS = [
    "input[type='file'][name*='resume' i]",
    "input[type='file'][id*='resume' i]",
    "input[type='file'][name*='cv' i]",
    "input[type='file'][accept*='pdf' i]",
    "input[type='file']",
]

_ATS_FIELD_PACKS: dict[str, list[tuple[str, str]]] = {
    "greenhouse": [
        ("#first_name, input[name='job_application[first_name]']", "first_name"),
        ("#last_name, input[name='job_application[last_name]']", "last_name"),
        ("#email, input[name='job_application[email]']", "email"),
        ("#phone, input[name='job_application[phone]']", "phone"),
        ("input[name*='linkedin' i]", "linkedin"),
        ("input[name*='github' i]", "github"),
        ("input[name*='location' i], #location", "location"),
    ],
    "lever": [
        ("input[name='name']", "full_name"),
        ("input[name='email']", "email"),
        ("input[name='phone']", "phone"),
        ("input[name*='urls[LinkedIn]' i], input[name*='linkedin' i]", "linkedin"),
        ("input[name*='urls[GitHub]' i], input[name*='github' i]", "github"),
    ],
    "ashby": [
        ("input[name*='firstName' i], input[autocomplete='given-name']", "first_name"),
        ("input[name*='lastName' i], input[autocomplete='family-name']", "last_name"),
        ("input[type='email']", "email"),
        ("input[type='tel']", "phone"),
        ("input[name*='linkedin' i]", "linkedin"),
    ],
}


def field_pack_for_ats(ats: str) -> list[tuple[str, str]]:
    return _ATS_FIELD_PACKS.get(ats, [])


def find_cv_pdf(company: str = "") -> str | None:
    """Latest tailored PDF in output/ — prefer company slug match."""
    import config

    output_dir = config.OUTPUT_DIR  # read dynamically so tests can isolate it
    if not os.path.isdir(output_dir):
        return None
    pdfs = sorted(glob.glob(os.path.join(output_dir, "*.pdf")), key=os.path.getmtime, reverse=True)
    if not pdfs:
        return None
    if company:
        slug = re.sub(r"[^a-z0-9]+", "", company.lower())
        for path in pdfs:
            base = os.path.basename(path).lower()
            if slug and slug[:4] in base.replace("-", "").replace("_", ""):
                return path
    return pdfs[0]


def upload_resume(page, pdf_path: str, report: dict[str, Any]) -> bool:
    if not pdf_path or not os.path.isfile(pdf_path):
        report.setdefault("errors", []).append(f"CV PDF not found: {pdf_path or 'none'}")
        return False
    for selector in _RESUME_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.count() == 0:
                continue
            loc.set_input_files(pdf_path, timeout=5000)
            report.setdefault("filled", []).append("resume_pdf")
            report["resume_path"] = pdf_path
            return True
        except Exception as exc:
            logger.debug("Resume upload %s: %s", selector, exc)
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for selector in _RESUME_SELECTORS[:4]:
            try:
                loc = frame.locator(selector).first
                if loc.count() == 0:
                    continue
                loc.set_input_files(pdf_path, timeout=5000)
                report.setdefault("filled", []).append("resume_pdf")
                report["resume_path"] = pdf_path
                return True
            except Exception:
                continue
    report.setdefault("unfilled", []).append("resume_pdf")
    return False


def fill_ats_fields(page, ats: str, profile: dict[str, str], report: dict[str, Any]) -> None:
    """Fill using ATS-specific selectors, then generic fallback."""
    from apply.ats_fill import _FIELD_CANDIDATES, _fill_known_fields

    pack = field_pack_for_ats(ats)
    if pack:
        _fill_known_fields(page, profile, report, selectors=pack)
    if not report.get("filled"):
        _fill_known_fields(page, profile, report, selectors=_FIELD_CANDIDATES)
    elif len(report.get("filled", [])) < 2:
        # Top up missing generic fields
        _fill_known_fields(page, profile, report, selectors=_FIELD_CANDIDATES)
