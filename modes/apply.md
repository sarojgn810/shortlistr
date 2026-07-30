# Mode: apply — Live Application Assistant

Interactive mode for when the candidate is filling out an application form in the browser. Reads what's on screen, loads prior offer context, and generates personalized answers for each form question.

## Requirements

- **Best with visible Playwright**: In visible mode, you see the browser and the AI agent can interact with the page.
- **Without Playwright**: the candidate shares a screenshot or pastes questions manually.

## Workflow

```
1. DETECT    → Read active browser tab (screenshot/URL/title)
2. IDENTIFY  → Extract company + role from the page
3. SEARCH    → Match against existing reports in reports/
4. LOAD      → Read full report + Section G (if it exists)
5. COMPARE   → Does the on-screen role match the evaluated one? If changed → warn
6. ANALYZE   → Identify ALL visible form questions
7. GENERATE  → For each question, generate a personalized answer
8. PRESENT   → Show answers formatted for copy-paste
```

## Step 1 — Detect the offer

**With Playwright:** Take a snapshot of the active page. Read title, URL, and visible content.

**Without Playwright:** Ask the candidate to:
- Share a screenshot of the form (Read tool reads images)
- Or paste form questions as text
- Or provide company + role so we can search

## Step 2 — Identify and load context

1. Extract company name and role title from the page
2. Search `reports/` by company name (case-insensitive Grep)
3. If there's a match → load the full report
4. If Section G exists → load prior draft answers as a base
5. If NO match → warn and offer a quick evaluate-full run

## Step 3 — Detect role changes

If the on-screen role differs from what was evaluated:
- **Warn the candidate**: "The role changed from [X] to [Y]. Re-evaluate or adapt answers to the new title?"
- **If adapt**: Adjust answers to the new role without re-evaluating
- **If re-evaluate**: Run full A–G evaluation, update report, regenerate Section G
- **Update tracker**: Change role title in applications.md if appropriate

## Step 4 — Analyze form questions

Identify ALL visible questions:
- Free-text fields (cover letter, why this role, etc.)
- Dropdowns (how did you hear, work authorization, etc.)
- Yes/No (relocation, visa, etc.)
- Salary fields (range, expectation)
- Upload fields (resume, cover letter PDF)

Classify each question:
- **Already answered in Section G** → adapt the existing answer
- **New question** → generate from report + cv.md

## Step 5 — Generate answers

For each question, follow:

1. **Report context**: Use proof points from block B, STAR stories from block F
2. **Prior Section G**: If a draft answer exists, use it as base and refine
3. **"I'm choosing you" tone**: Same framework as evaluate-full
4. **Specificity**: Reference something concrete from the JD visible on screen
5. **Portfolio proof point**: Include in "Additional info" if there's a field for it

**Output format:**

```
## Answers for [Company] — [Role]

Based on: Report #NNN | Score: X.X/5 | Archetype: [type]

---

### 1. [Exact form question]
> [Answer ready for copy-paste]

### 2. [Next question]
> [Answer]

...

---

Notes:
- [Any observation about the role, changes, etc.]
- [Personalization suggestions the candidate should review]
```

## Step 6 — Post-apply (optional)

If the candidate confirms they submitted the application:
1. Update status in `applications.md` from `Evaluated` to `Applied`
2. Update report Section G with final answers
3. Suggest next step: review tracker with `/shortlistr tracker`

## Scroll handling

If the form has more questions than are visible:
- Ask the candidate to scroll and share another screenshot
- Or paste remaining questions
- Process in iterations until the full form is covered
