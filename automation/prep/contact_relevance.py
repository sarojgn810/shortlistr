"""Whether a resolved contact plausibly has anything to do with this role.

LinkedIn's "People you can reach out to" panel suggests whoever you share
history with. On a Site Reliability Engineer opening it offered an "Enterprise
Revenue and Commercial Leader — SaaS & AI", flagged as a company alum from a
former employer: a sales director, surfaced because of a shared past employer
and nothing else.

Writing to him once is an awkward afternoon. Doing it automatically across a
pipeline is a reputation, and the user's name is on every message. So a contact
is scored before a draft is written, and the default when nothing is known is to
stop rather than to send.

Matching on the job's own words is not enough on its own — "Sales Engineer"
contains "engineer". Revenue-side functions are therefore checked first and
disqualify outright.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Checked first: a title in one of these functions is not a hiring contact for
# an engineering role however many technical words it also contains.
_REVENUE_SIDE = re.compile(
    r"\bsales\b|account executive|\bae\b|revenue|commercial|business development|"
    r"\bbd\b|marketing|brand|growth marketing|customer success|\bcsm\b|"
    r"partnerships|procurement|finance|controller|accounting|legal|counsel",
    re.I,
)

# People who hire, manage or do the work.
_HIRING_SIDE = re.compile(
    r"recruit|talent acquisition|\btalent\b|sourcer|people ops|human resources|\bhr\b",
    re.I,
)
_ENGINEERING_SIDE = re.compile(
    r"engineer|engineering|developer|architect|\bsre\b|site reliability|devops|"
    r"infrastructure|platform|technology|technical lead|\bcto\b|\bvp eng|"
    r"head of (engineering|infrastructure|platform|technology)",
    re.I,
)

# Sources that suggest a networking hint rather than someone connected to the
# opening. LinkedIn's alum panel is the one that prompted this module.
_WEAK_SOURCES = {"linkedin_suggestion", "alumni", "people_also_viewed"}
_ALUM_HINT = re.compile(r"company alum|alum from|worked together|shared connection", re.I)


@dataclass(frozen=True)
class ContactVerdict:
    relevant: bool
    reason: str


def assess_contact(contact: dict, *, role: str = "") -> ContactVerdict:
    """Judge a contact before anything is drafted for them."""
    title = str(contact.get("title") or "").strip()

    if not title:
        return ContactVerdict(
            False,
            "No title for this contact, so there is no way to tell whether they "
            "are connected to the role. Send this one by hand if you know them.",
        )

    source = str(contact.get("source") or "").strip().lower()
    note = str(contact.get("note") or "")
    if source in _WEAK_SOURCES or _ALUM_HINT.search(note):
        return ContactVerdict(
            False,
            f"{title} came from a networking suggestion rather than the posting, "
            "so there is no sign they are involved in this hiring.",
        )

    if _REVENUE_SIDE.search(title):
        return ContactVerdict(
            False,
            f"{title} is a revenue or business-side role, not someone hiring for "
            f"{role or 'this position'}.",
        )

    if _HIRING_SIDE.search(title):
        return ContactVerdict(True, f"{title} recruits — a reasonable person to write to.")

    if _ENGINEERING_SIDE.search(title):
        return ContactVerdict(True, f"{title} is on the engineering side of the org.")

    return ContactVerdict(
        False,
        f"{title} does not obviously relate to {role or 'this role'}, so it is "
        "left for you to judge.",
    )
