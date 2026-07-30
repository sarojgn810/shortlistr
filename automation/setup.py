#!/usr/bin/env python3
"""
shortlistr — First-Time Setup Wizard
Run this once before anything else:  python setup.py

What it does:
  1. Asks for your personal details
  2. Guides you on where to place your resume
  3. Sets your job search filters (location, salary, titles)
  4. Asks which LLM provider to use (or none)
  5. Writes config/profile.yml — your single source of truth
  6. Writes .env — your secrets (never committed to git)
  7. Verifies the folder structure is correct
"""

import os
import sys
import shutil
import textwrap

# ── Colours ───────────────────────────────────────────────────────────────────
def _c(text, code): return f"\x1b[{code}m{text}\x1b[0m"
def green(t):  return _c(t, "32")
def yellow(t): return _c(t, "33")
def cyan(t):   return _c(t, "36")
def bold(t):   return _c(t, "1")
def dim(t):    return _c(t, "2")
def red(t):    return _c(t, "31")

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
SHORTLISTR_ROOT = os.path.dirname(BASE_DIR)
CONFIG_DIR   = os.path.join(SHORTLISTR_ROOT, "config")
PROFILE_YML  = os.path.join(CONFIG_DIR, "profile.yml")
ENV_FILE     = os.path.join(SHORTLISTR_ROOT, ".env")
LEGACY_PROFILE = os.path.join(BASE_DIR, "config", "profile.yml")
APPLICATIONS_TEMPLATE = os.path.join(SHORTLISTR_ROOT, "templates", "applications.example.md")
APPLICATIONS_PATH = os.path.join(SHORTLISTR_ROOT, "data", "applications.md")


# ── Helpers ───────────────────────────────────────────────────────────────────

def ask(prompt, default="", required=False):
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"  {prompt}{suffix}: ").strip()
        if not val and default:
            return default
        if not val and required:
            print(red("  ✗ This field is required."))
            continue
        return val or default

def ask_choice(prompt, options, default=None):
    print(f"\n  {prompt}")
    for i, (key, label) in enumerate(options, 1):
        marker = " (default)" if key == default else ""
        print(f"    {dim(str(i) + '.')} {label}{dim(marker)}")
    while True:
        raw = input(f"  Enter number [{default or '1'}]: ").strip()
        if not raw and default:
            return default
        if not raw:
            return options[0][0]
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(red("  ✗ Enter a number from the list."))

def ask_yn(prompt, default="y"):
    suffix = " [Y/n]" if default == "y" else " [y/N]"
    val = input(f"  {prompt}{suffix}: ").strip().lower()
    return (val or default) == "y"

def section(title):
    print(f"\n{bold('─' * 58)}")
    print(bold(f"  {title}"))
    print(bold('─' * 58))


# ── Welcome ───────────────────────────────────────────────────────────────────

def welcome():
    os.system("clear")
    print()
    print(bold(cyan("  ┌─────────────────────────────────────────────────┐")))
    print(bold(cyan("  │           shortlistr — Setup Wizard                │")))
    print(bold(cyan("  │   Smarter job search, fewer applications        │")))
    print(bold(cyan("  └─────────────────────────────────────────────────┘")))
    print()
    print(dim("  This wizard takes ~3 minutes and only runs once."))
    print(dim("  Your answers are saved to config/profile.yml (repo root)"))
    print(dim("  Secrets (passwords, API keys) go to .env (never committed)"))
    print()
    input(dim("  Press Enter to start..."))


# ── Step 1 — Personal details ─────────────────────────────────────────────────

def step_personal():
    section("STEP 1 — Your Details")
    print(dim("  These appear in cover letters and application emails.\n"))

    name    = ask("Full name", required=True)
    email   = ask("Email address", required=True)
    phone   = ask("Phone (with country code, e.g. +91 9876543210)")
    loc     = ask("Your city / country (e.g. Bangalore, India)")
    li      = ask("LinkedIn URL (e.g. https://linkedin.com/in/yourname)")
    gh      = ask("GitHub URL (optional)")
    exp     = ask("Years of experience", default="0")

    return {
        "name": name, "email": email, "phone": phone,
        "location": loc, "linkedin": li, "github": gh,
        "years_exp": int(exp) if exp.isdigit() else 0,
    }


# ── Step 2 — Resume file ──────────────────────────────────────────────────────

def step_resume():
    section("STEP 2 — Your Resume")

    target_pdf = os.path.join(SHORTLISTR_ROOT, "resume.pdf")
    target_md  = os.path.join(SHORTLISTR_ROOT, "cv.md")

    print(textwrap.dedent(f"""
  shortlistr expects your resume at:

    {bold(green('resume.pdf'))}   ← repo root (or any path in profile files.resume_pdf)
    {bold(dim('cv.md'))}                      ← repo root (canonical CV for AI evaluation)

  Both paths are gitignored — your files are never committed.
    """))

    if os.path.exists(target_pdf):
        print(green(f"  ✓ Resume PDF found at repo root."))
    else:
        print(yellow("  Resume PDF not found at repo root yet."))
        print(dim("  Options:"))
        print(dim("    A) Enter the full path to your existing PDF — I'll copy it"))
        print(dim("    B) Skip — place it manually later\n"))

        src = ask("Path to your resume PDF (or press Enter to skip)").strip()
        if src:
            src = os.path.expanduser(src)
            if os.path.exists(src):
                shutil.copy2(src, target_pdf)
                print(green(f"  ✓ Copied to {os.path.basename(target_pdf)}"))
            else:
                print(red(f"  ✗ File not found: {src}"))
        else:
            print(yellow("  → Place your resume PDF in the repo root before running."))

    if os.path.exists(target_md):
        print(green(f"  ✓ cv.md already exists at repo root."))
    else:
        print(dim("\n  Tip: cv.md at repo root is used by /shortlistr evaluation and LLM cover letters."))

    return {
        "resume_pdf": "resume.pdf",
        "cv_markdown": "cv.md",
    }


# ── Step 3 — Job search filters ───────────────────────────────────────────────

def step_filters():
    section("STEP 3 — Job Search Filters")

    print(dim("\n  Preferred locations (press Enter after each, blank line to finish):"))
    print(dim("  Examples: Bangalore, Remote, Hyderabad"))
    locations: list[str] = []
    while True:
        loc = input("    Location: ").strip()
        if not loc:
            break
        locations.append(loc)
    if not locations:
        locations = ["Remote"]
        print(yellow(f"  → Using default: {', '.join(locations)}"))

    print(dim("\n  Salary floor — jobs below this are flagged (0 = no filter):"))
    inr_lpa = ask("Minimum salary in INR LPA (e.g. 35 for ₹35L, 0 to skip)", default="0")
    usd     = ask("Minimum salary in USD/year (e.g. 80000, 0 to skip)", default="0")

    salary_unlisted = ask_choice(
        "Jobs where salary is not listed:",
        [
            ("include", "Include them (most jobs don't list salary)"),
            ("skip",    "Skip them"),
        ],
        default="include",
    )

    print(dim("\n  Job titles to target (press Enter after each, blank line to finish):"))
    print(dim("  Examples: Software Engineer, Product Manager, Data Analyst"))
    titles = []
    while True:
        t = input("    Title: ").strip()
        if not t:
            break
        titles.append(t)
    if not titles:
        print(yellow("  → No titles entered — set them in dashboard onboarding after uploading a résumé."))
        titles = ["Software Engineer"]

    min_score = ask("Minimum fit score to consider a job (0–100, default 40)", default="40")

    return {
        "preferred_locations": locations,
        "min_salary_inr_lpa": int(inr_lpa) if inr_lpa.isdigit() else 0,
        "min_salary_usd": int(usd) if usd.isdigit() else 0,
        "salary_unlisted": salary_unlisted,
        "target_titles": titles,
        "deal_breakers": [],
        "min_fit_score": int(min_score) if min_score.isdigit() else 40,
    }


# ── Step 4 — LLM provider ─────────────────────────────────────────────────────

def step_llm():
    section("STEP 4 — LLM Provider (optional)")

    print(textwrap.dedent("""
  shortlistr uses an LLM for:
    • Personalized cover letters (instead of generic templates)
    • Full A–G job scoring and legitimacy judgment
    • Conversational assistant (dashboard chat / Telegram)

  Interview prep guides, CV PDFs, discovery, and apply-assist work without an LLM.
  You can skip this and use basic scoring — everything still works.
    """))

    provider = ask_choice(
        "Which LLM provider do you want to use?",
        [
            ("none",   "None — use templates (no AI, no API key needed)"),
            ("anthropic", "Anthropic API — recommended"),
            ("openai", "OpenAI (GPT-4o)"),
            ("gemini", "Google Gemini"),
            ("grok", "xAI Grok"),
            ("groq", "Groq (fast Llama inference)"),
            ("ollama", "Ollama — local models, no API key needed"),
        ],
        default="none",
    )

    model = ""
    api_key = ""
    ollama_url = "http://localhost:11434"

    defaults = {
        "anthropic": "claude-3-5-sonnet-20241022",
        "openai": "gpt-4o",
        "gemini": "gemini-1.5-pro",
        "grok": "grok-4",
        "groq": "llama-3.3-70b-versatile",
        "ollama": "llama3",
    }

    env_vars = {
        "anthropic": "SHORTLISTR_LLM_API_KEY",
        "openai": "SHORTLISTR_LLM_API_KEY",
        "gemini": "SHORTLISTR_LLM_API_KEY",
        "grok": "SHORTLISTR_LLM_API_KEY",
        "groq": "SHORTLISTR_LLM_API_KEY",
    }

    if provider not in ("none", "ollama"):
        default_model = defaults.get(provider, "")
        model = ask(f"Model name", default=default_model)
        api_key = ask(f"API key for {provider} (stored in .env, never in profile.yml)", required=True)

    elif provider == "ollama":
        default_model = defaults["ollama"]
        model = ask("Ollama model name", default=default_model)
        ollama_url = ask("Ollama URL", default=ollama_url)

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,  # written to .env only
        "ollama_url": ollama_url,
    }


# ── Step 5 — Email ────────────────────────────────────────────────────────────

def step_email(candidate_email):
    section("STEP 5 — Email (for sending applications)")

    print(textwrap.dedent("""
  shortlistr can email applications directly for jobs with public company emails.
  It uses Gmail SMTP with an App Password (not your regular password).

  To get a Gmail App Password:
    1. Go to https://myaccount.google.com/apppasswords
    2. Enable 2-Step Verification first if not done
    3. Create an App Password named "shortlistr"
    4. Paste the 16-character code below
    """))

    wants_email = ask_yn("Set up email sending now?", default="y")
    if not wants_email:
        return {"sender": candidate_email, "max_per_run": 10, "password": ""}

    sender = ask("Gmail address to send from", default=candidate_email)
    password = ask("Gmail App Password (16 chars, stored in .env only)", required=False)
    max_per_run = ask("Max emails per daily run (safety cap)", default="10")

    return {
        "sender": sender,
        "max_per_run": int(max_per_run) if max_per_run.isdigit() else 10,
        "password": password,
    }


# ── Step 6 — Platforms ────────────────────────────────────────────────────────

def step_platforms(candidate_email):
    section("STEP 6 — Platform Credentials (optional)")

    print(dim("  LinkedIn and Naukri passwords are stored in .env only.\n"))

    li_email  = ask("LinkedIn email", default=candidate_email)
    li_pass   = ask("LinkedIn password (stored in .env, press Enter to skip)")
    nk_email  = ask("Naukri email (press Enter to skip)")
    nk_pass   = ""
    if nk_email:
        nk_pass = ask("Naukri password (stored in .env)")

    return {
        "linkedin": {"email": li_email, "password": li_pass},
        "naukri":   {"email": nk_email or "", "password": nk_pass},
    }


# ── Write files ───────────────────────────────────────────────────────────────

def write_profile_yml(candidate, files, filters, llm, email, platforms):
    os.makedirs(CONFIG_DIR, exist_ok=True)

    llm_for_yml = {k: v for k, v in llm.items() if k != "api_key"}

    titles_yml = "\n".join(f'    - "{t}"' for t in filters["target_titles"])
    locs_yml = "\n".join(f'    - "{loc}"' for loc in filters.get("preferred_locations", ["Remote"]))

    content = f"""# shortlistr — User Profile
# Generated by setup.py on {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}
# To re-run setup: python setup.py

candidate:
  name: "{candidate['name']}"
  email: "{candidate['email']}"
  phone: "{candidate['phone']}"
  location: "{candidate['location']}"
  linkedin: "{candidate['linkedin']}"
  github: "{candidate['github']}"
  years_exp: {candidate['years_exp']}

files:
  resume_pdf: "{files['resume_pdf']}"
  cv_markdown: "{files['cv_markdown']}"

filters:
  min_salary_inr_lpa: {filters['min_salary_inr_lpa']}
  min_salary_usd: {filters['min_salary_usd']}
  salary_unlisted: "{filters['salary_unlisted']}"
  target_titles:
{titles_yml}
  preferred_locations:
{locs_yml}
  deal_breakers: []

llm:
  provider: "{llm['provider']}"
  model: "{llm['model']}"
  api_key: ""   # Set via .env: SHORTLISTR_LLM_API_KEY
  ollama_url: "{llm['ollama_url']}"

email:
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  sender: "{email['sender']}"
  max_per_run: {email['max_per_run']}

platforms:
  linkedin:
    email: "{platforms['linkedin']['email']}"
  naukri:
    email: "{platforms['naukri']['email']}"

scoring:
  min_fit_score: {filters['min_fit_score']}
"""
    with open(PROFILE_YML, "w") as f:
        f.write(content)
    print(green(f"\n  ✓ config/profile.yml written"))


def write_env(llm, email, platforms):
    lines = [
        "# shortlistr — Secrets",
        "# This file is gitignored. Never commit it.",
        "",
    ]

    if llm.get("api_key"):
        lines.append(f"SHORTLISTR_LLM_API_KEY={llm['api_key']}")
    else:
        lines.append("SHORTLISTR_LLM_API_KEY=")

    if email.get("password"):
        lines.append(f"SHORTLISTR_EMAIL_PASSWORD={email['password']}")
    else:
        lines.append("SHORTLISTR_EMAIL_PASSWORD=")

    if platforms["linkedin"].get("password"):
        lines.append(f"SHORTLISTR_LINKEDIN_PASSWORD={platforms['linkedin']['password']}")
    else:
        lines.append("SHORTLISTR_LINKEDIN_PASSWORD=")

    if platforms["naukri"].get("password"):
        lines.append(f"SHORTLISTR_NAUKRI_PASSWORD={platforms['naukri']['password']}")
    else:
        lines.append("SHORTLISTR_NAUKRI_PASSWORD=")

    with open(ENV_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(green(f"  ✓ .env written"))


# ── Final summary ─────────────────────────────────────────────────────────────

def summary(candidate, filters, llm, files):
    section("✅  Setup Complete!")

    resume_ok = os.path.exists(os.path.join(SHORTLISTR_ROOT, files["resume_pdf"]))
    cv_ok     = os.path.exists(os.path.join(SHORTLISTR_ROOT, files["cv_markdown"]))

    print(f"""
  {bold('You:')}         {candidate['name']} ({candidate['email']})
  {bold('Location:')}    {candidate['location']}
  {bold('Titles:')}      {', '.join(filters['target_titles'][:3])}{'...' if len(filters['target_titles']) > 3 else ''}
  {bold('LLM:')}         {llm['provider'].upper() if llm['provider'] != 'none' else 'None (template mode)'}
  {bold('Resume PDF:')}  {'✓ Found' if resume_ok else yellow('✗ Missing — place PDF in repo root')}
  {bold('CV markdown:')} {'✓ Found' if cv_ok else dim('Not set (optional)')}
""")

    print(bold("  Next steps:"))
    if not resume_ok:
        print(yellow("  1. Copy your resume PDF to the repo root (e.g. resume.pdf)"))
    print(f"  {'2' if not resume_ok else '1'}. Test the system:")
    print(cyan("       python run_daily.py --dry-run"))
    print(f"  {'3' if not resume_ok else '2'}. Set up daily automation:")
    print(cyan("       bash setup_cron.sh"))
    print()


def seed_applications_tracker():
    """Create data/applications.md from template if missing."""
    if os.path.exists(APPLICATIONS_PATH):
        return
    os.makedirs(os.path.dirname(APPLICATIONS_PATH), exist_ok=True)
    if os.path.exists(APPLICATIONS_TEMPLATE):
        shutil.copy2(APPLICATIONS_TEMPLATE, APPLICATIONS_PATH)
        print(green(f"  ✓ Created {APPLICATIONS_PATH} from template"))
    else:
        with open(APPLICATIONS_PATH, "w", encoding="utf-8") as f:
            f.write(
                "# Applications Tracker\n\n"
                "| # | Date | Company | Role | Score | Status | PDF | Report | Notes |\n"
                "|---|------|---------|------|-------|--------|-----|--------|-------|\n"
            )
        print(green(f"  ✓ Created {APPLICATIONS_PATH}"))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    welcome()

    if not os.path.exists(PROFILE_YML) and os.path.exists(LEGACY_PROFILE):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copy2(LEGACY_PROFILE, PROFILE_YML)
        print(green(f"  ✓ Migrated {LEGACY_PROFILE} → {PROFILE_YML}"))

    if os.path.exists(PROFILE_YML):
        print(yellow("  config/profile.yml already exists."))
        overwrite = ask_yn("  Overwrite with fresh setup?", default="n")
        if not overwrite:
            print(dim("  Keeping existing profile. Run `python setup.py` anytime to redo.\n"))
            sys.exit(0)

    candidate  = step_personal()
    files      = step_resume()
    filters    = step_filters()
    llm        = step_llm()
    email      = step_email(candidate["email"])
    platforms  = step_platforms(candidate["email"])

    section("Writing config files...")
    write_profile_yml(candidate, files, filters, llm, email, platforms)
    write_env(llm, email, platforms)
    seed_applications_tracker()

    summary(candidate, filters, llm, files)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{dim('  Setup cancelled. Run again anytime: python setup.py')}\n")
        sys.exit(0)
