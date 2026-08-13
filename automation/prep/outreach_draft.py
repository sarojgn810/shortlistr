"""Outreach written from the posting's own requirements.

The previous draft said "happy to share a short note on fit", which is true of
every candidate for every job and therefore tells the reader nothing. Evaluation
now records which of a posting's hard requirements the CV answers, and quotes
the CV line that answers each one, so a message can name two or three instead of
gesturing at fit in general.

Two rules hold. Nothing is claimed that the evidence does not carry — this goes
out under the user's name to someone who can check it in the first screen. And
an unmet requirement is never dressed up as met: with nothing solid to say the
draft stays short and general rather than inventing a specific.
"""

from __future__ import annotations

import re
from typing import Any

# Three is the point where a note still reads as a person writing and not as a
# CV pasted into an email.
MAX_SPECIFICS = 3
# Requirements in the wild are long — "Deep understanding of Site Reliability
# Engineering (SRE), SLOs, Error Budgets and Incident Management" is one line of
# one posting. Three of those unedited made a 300-character sentence nobody
# would finish, so each is trimmed to its first clause and the line as a whole
# is capped.
MAX_PHRASE_CHARS = 52
MAX_SPECIFICS_CHARS = 170


def _met_requirements(must_haves: Any) -> list[dict[str, Any]]:
    if not isinstance(must_haves, list):
        return []
    return [
        row for row in must_haves
        if isinstance(row, dict) and row.get("met") and str(row.get("req") or "").strip()
    ]


# Named technologies and practices. Short proper nouns survive being quoted;
# requirement prose does not — truncating it produced "site Reliability
# Engineering (SRE)" and "(Python and experience designing APIs", which is worse
# than saying nothing.
_SKILL_TERMS = (
    "Kubernetes", "Docker", "Terraform", "Ansible", "Helm", "Jenkins", "ArgoCD",
    "Prometheus", "Grafana", "Datadog", "ELK", "OpenTelemetry", "Splunk",
    "AWS", "GCP", "Azure", "EKS", "GKE", "Linux", "Python", "Go", "Bash",
    "SLOs", "SLIs", "error budgets", "incident management", "on-call",
    "CI/CD", "observability", "site reliability engineering", "infrastructure as code",
    "MLOps", "Kafka", "PostgreSQL", "Redis", "Spark", "Airflow",
)


def _skills_in(text: str) -> list[str]:
    """Named skills mentioned in a requirement, in the source's own casing."""
    found = []
    for term in _SKILL_TERMS:
        if re.search(rf"(?<![\w+#]){re.escape(term)}(?![\w+#])", text, re.I):
            found.append(term)
    return found


def _specifics_line(met: list[dict[str, Any]]) -> str:
    """Name what the posting asked for and the CV evidences, nothing else."""
    skills: list[str] = []
    for row in met:
        requirement = str(row.get("req") or "")
        evidence = str(row.get("evidence") or "")
        for skill in _skills_in(requirement):
            # Both sides must name it: the posting asked, and the CV line the
            # model quoted backs it up. That is what keeps this checkable.
            if skill not in skills and (not evidence or _skills_in(evidence)):
                skills.append(skill)
        if len(skills) >= MAX_SPECIFICS:
            break

    skills = skills[:MAX_SPECIFICS]
    if not skills:
        return ""
    if len(skills) == 1:
        listed = skills[0]
    elif len(skills) == 2:
        listed = f"{skills[0]} and {skills[1]}"
    else:
        listed = f"{skills[0]}, {skills[1]} and {skills[2]}"
    # A full stop, not an em-dash: the prose sanitiser rewrites dashes into
    # commas, which turned this into a comma splice.
    return f"{listed} is what I have been working on day to day."


def draft_grounded_outreach(
    *,
    company: str,
    role: str,
    contact_name: str = "",
    candidate_name: str = "",
    must_haves: Any = None,
) -> str:
    """A short note citing requirements the CV actually answers."""
    company = (company or "your team").strip() or "your team"
    role = (role or "the role").strip() or "the role"
    greeting = f"Hi {contact_name.strip().split()[0]}," if contact_name.strip() else "Hi,"
    signature = (candidate_name or "").strip()

    met = _met_requirements(must_haves)
    specifics = _specifics_line(met)

    opening = f"I saw the {role} opening at {company}."
    # With no evidence, say less. An invented specific is worse than a plain note.
    closing = (
        "Happy to send a short note on where I would fit, or talk it through."
        if specifics
        else "Happy to share why I think I would fit, if that is useful."
    )

    body = "\n\n".join(part for part in (greeting, opening, specifics, closing) if part)
    if signature:
        body += f"\n\nThanks,\n{signature}"

    try:
        from writing.sanitize import sanitize

        return sanitize(body, mode="prose")
    except Exception:
        return body
