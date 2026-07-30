# Changelog

## Unreleased — cross-platform + productization pass

A structured completion pass (see `plan/`) took Shortlistr from "works for the author on macOS/Linux"
to a genuinely cross-platform, download-and-run open-source app. All changes verified live on Windows.

### Added
- **One-command cross-platform launcher** — `python -m automation.cli start` (install + seed + run +
  open) and `dev` (run only), plus `start.bat` / `start.ps1` for Windows. `make start`/`dev` now route
  to it. Handles prereq checks, health polling, port preflight, and clean multi-process shutdown
  (tree-kill on Windows).
- **Bundled cloud LLM SDKs** (`openai`, `anthropic`, `google-genai`) so a pasted API key produces real
  A–G evaluations out of the box — no more silent fallback to keyword mode.
- **Honest LLM status** — `/health` + `/setup/status` now report `sdk_installed` / `reason` / `hint`
  (e.g. "provider set but SDK missing — run: pip install openai"), surfaced in the Connections UI.
- **11 distinct professional résumé designs** (per-template accents, headings, serif/monospace variants).
- **Frontend test harness** (vitest) + CI that guards the frontend (`tsc` / `lint` / `build` / `test`)
  and runs the backend suite on **Windows + Linux**.
- `tests/test_state_machine.py` — ~41 dedicated pipeline/application state-machine unit tests.

### Changed
- **Résumé rendering unified** on one cross-platform path (HTML/CSS → Chromium). What you preview =
  what you download = what gets attached to applications. Apply-time generation is now template-aware.
- **Global-neutral first-run defaults** — starter profile, discovery fallbacks, and cover letters are
  no longer hardcoded to SRE/India; targeting comes from the uploaded résumé.
- Migrated the Gemini adapter from the end-of-life `google-generativeai` to the current `google-genai`.
- Eval calls retry once on a transient error before falling back to template mode.

### Fixed
- **Windows `UnicodeEncodeError`** — CLI output crashed on cp1252 consoles (the `✓`/emoji class of bug).
- **`make test` deleted the user's real `cv.md`** — test isolation didn't cover `CV_MD_PATH`.
- Apply-time résumé generator was broken on Windows (`python3` subprocess) and ignored the chosen template.

### Notes / optional follow-ups
- Docker/compose for a zero-local-deps run is intentionally deferred (the Python launcher covers the
  download-and-run goal; Docker to be added + tested separately).
- Search-provider keys still read from `.env` (fine for the local single-user threat model).
