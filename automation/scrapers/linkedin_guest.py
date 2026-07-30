"""LinkedIn public guest job search — scrape-only, no account or cookies.

This uses the same public listing fragments LinkedIn serves to signed-out job
seekers. It never logs in, opens an application form, or submits anything.
"""

from __future__ import annotations

import logging
import random
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

import requests

import config as _cfg
from models.job import JobRecord

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REMOTE_WORKPLACE_TYPE = "2"


class LinkedInGuestBlocked(RuntimeError):
    """The signed-out listings endpoint rejected or challenged the request."""


class _CardsParser(HTMLParser):
    """Extract fields from LinkedIn's server-rendered ``<li>`` job cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, str]] = []
        self._card: dict[str, str] | None = None
        self._field = ""
        self._field_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: v or "" for k, v in attrs}
        classes = set(values.get("class", "").split())

        if tag == "li":
            self._card = {}
            self._field = ""
            self._field_depth = 0
        if self._card is None:
            return

        if "base-card__full-link" in classes and values.get("href"):
            self._card["url"] = values["href"]
        if values.get("data-entity-urn", "").startswith("urn:li:jobPosting:"):
            self._card["source_job_id"] = values["data-entity-urn"].rsplit(":", 1)[-1]

        field = ""
        if "base-search-card__title" in classes:
            field = "title"
        elif "base-search-card__subtitle" in classes:
            field = "company"
        elif "job-search-card__location" in classes:
            field = "location"
        elif tag == "time":
            field = "posted"

        if field:
            self._field = field
            self._field_depth = 1
        elif self._field:
            self._field_depth += 1

    def handle_data(self, data: str) -> None:
        if self._card is not None and self._field and data.strip():
            current = self._card.get(self._field, "")
            self._card[self._field] = f"{current} {data.strip()}".strip()

    def handle_endtag(self, tag: str) -> None:
        if self._card is None:
            return
        if self._field:
            self._field_depth -= 1
            if self._field_depth <= 0:
                self._field = ""
                self._field_depth = 0
        if tag == "li":
            if self._card.get("url") and self._card.get("title"):
                self.cards.append(self._card)
            self._card = None
            self._field = ""
            self._field_depth = 0


def parse_guest_cards(html: str) -> list[dict[str, str]]:
    parser = _CardsParser()
    parser.feed(html or "")
    return parser.cards


def _canonical_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _remote_search_location() -> str:
    """Use the candidate's country for remote search, else worldwide."""
    candidate_location = str((_cfg.CANDIDATE or {}).get("location") or "").strip()
    if "," in candidate_location:
        country = candidate_location.rsplit(",", 1)[-1].strip()
        if country:
            return country
    return candidate_location or "Worldwide"


def build_searches() -> list[tuple[str, str, bool]]:
    """Cover each role family across preferred cities and remote work."""
    titles = _cfg.search_titles(5)
    cities = _cfg.search_locations(3)
    searches: list[tuple[str, str, bool]] = []
    for title in titles:
        for city in cities:
            searches.append((title, city, False))
        if _cfg.WANTS_REMOTE:
            searches.append((title, _remote_search_location(), True))
    if not cities and not _cfg.WANTS_REMOTE:
        searches.extend((title, _remote_search_location(), False) for title in titles)
    return searches


def _request_page(
    title: str,
    location: str,
    remote: bool,
    *,
    start: int,
    session: requests.Session,
    sleep_fn=time.sleep,
) -> str:
    params: dict[str, str | int] = {
        "keywords": title,
        "location": location,
        "start": start,
        "sortBy": "DD",
    }
    if remote:
        params["f_WT"] = REMOTE_WORKPLACE_TYPE

    response = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = min(max(float(retry_after), 2.0), 15.0)
        except ValueError:
            delay = 4.0
        sleep_fn(delay)
        response = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)

    if response.status_code != 200:
        raise LinkedInGuestBlocked(
            f"LinkedIn guest search returned HTTP {response.status_code}"
        )
    return response.text


def fetch_linkedin_guest(
    *,
    max_pages: int = 1,
    page_size: int = 25,
    request_delay: tuple[float, float] = (0.8, 1.4),
    session: requests.Session | None = None,
    sleep_fn=time.sleep,
) -> tuple[list[JobRecord], str]:
    """Fetch public cards for profile title/location pairs, with gentle pacing."""
    client = session or requests.Session()
    jobs: list[JobRecord] = []
    seen: set[str] = set()

    error = ""
    for title, location, remote in build_searches():
        for page in range(max(1, max_pages)):
            try:
                html = _request_page(
                    title,
                    location,
                    remote,
                    start=page * page_size,
                    session=client,
                    sleep_fn=sleep_fn,
                )
            except LinkedInGuestBlocked as exc:
                error = str(exc)
                logger.warning("%s; stopping this scan after %d listings", error, len(jobs))
                break
            cards = parse_guest_cards(html)
            if not cards:
                break
            for card in cards:
                url = _canonical_url(card.get("url", ""))
                if not url or url in seen:
                    continue
                seen.add(url)
                jobs.append(
                    JobRecord(
                        url=url,
                        source="LinkedIn",
                        company=card.get("company", ""),
                        title=card.get("title", ""),
                        location=card.get("location", ""),
                        notes="LinkedIn public listing — apply on LinkedIn",
                        metadata={
                            "source_job_id": card.get("source_job_id", ""),
                            "posted_label": card.get("posted", ""),
                            "guest_search": True,
                        },
                    )
                )
            if page + 1 < max_pages:
                sleep_fn(random.uniform(*request_delay))
        if error:
            break
        sleep_fn(random.uniform(*request_delay))

    logger.info(
        "LinkedIn guest search: %d unique public listings (scrape-only)", len(jobs)
    )
    return jobs, error


def fetch_linkedin_guest_raw(**kwargs) -> list[JobRecord]:
    """Compatibility wrapper for callers that only need listing records."""
    jobs, _ = fetch_linkedin_guest(**kwargs)
    return jobs
