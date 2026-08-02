"""Neutral first-run / preview sample content.

Identity is never the product: targeting always comes from the user's uploaded
résumé (or onboarding form). These strings are demo placeholders only.
"""

# Markers intentionally match cv.placeholder.PLACEHOLDER_MARKERS so onboarding
# blocks "finish" until a real résumé replaces this file.
PLACEHOLDER_CV = """# Your Name

**email@example.com** | **City, Country** | **linkedin.com/in/you**

## PROFESSIONAL SUMMARY

Your role, years of experience. One measurable win.

## CORE COMPETENCIES

Skill one, skill two, skill three

## PROFESSIONAL EXPERIENCE

### Your Title | Company | Years

- Bullet with a metric
- Bullet with a metric

## EDUCATION

Degree | School | Years
"""

# Structured demo CV for template previews (not written as the live cv.md).
DEMO_SAMPLE_CV = """# Alex Candidate

**Remote** | **alex@example.com** | **+1 555 0100** | **linkedin.com/in/alex-candidate**

## PROFESSIONAL SUMMARY

Software Engineer with 5 years shipping web products. Improved checkout conversion 18% and cut page load time 40% on a high-traffic consumer app.

## CORE COMPETENCIES

Python, TypeScript, React, PostgreSQL, AWS, CI/CD, REST APIs, system design

## PROFESSIONAL EXPERIENCE

### Software Engineer | Example Corp | 2021 – Present

- Shipped billing features used by 200k customers; reduced failed payments 22%.
- Led migration of legacy jobs to a queue workers; cut overnight batch time 35%.

### Junior Software Engineer | Startup Co | 2019 – 2021

- Built internal admin tools in React; saved support team ~8 hours/week.

## EDUCATION

B.S. Computer Science | State University | 2015 – 2019
"""

# Back-compat alias (older imports). Prefer DEMO_SAMPLE_CV / SAMPLE_CV.
LEGACY_SAMPLE_CV = DEMO_SAMPLE_CV
SAMPLE_CV = DEMO_SAMPLE_CV

# First-run profile is NOT seeded with a person — onboarding creates it.
# Kept for tests that still call save_profile_from_ui(STARTER_PROFILE).
STARTER_PROFILE: dict = {
    "name": "Demo User",
    "email": "demo@example.com",
    "phone": "",
    "location": "Remote",
    "linkedin": "",
    "github": "",
    "years_exp": 0,
    "min_salary_inr_lpa": 0,
    "min_salary_usd": 0,
    "target_titles": ["Software Engineer"],
    "preferred_locations": ["Remote"],
    "llm_provider": "auto",
    "llm_model": "qwen2.5:0.5b",
}

DEFAULT_TEMPLATE_ID = "ats-single"
