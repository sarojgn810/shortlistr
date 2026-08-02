"""Source registry — enabled adapters from profile config."""

from __future__ import annotations

import config as _cfg
from config import SOURCE_ENABLED, LINKEDIN_SOURCE_CONFIG, DISCOVERY_RESOLVE_PIPELINE, DISCOVERY_SEARCH_QUERIES
from sources.adapters.aggregators_adapter import AggregatorsAdapter
from sources.adapters.apify_adapter import ApifyAdapter
from sources.adapters.gmail_adapter import GmailAdapter
from sources.adapters.hiringcafe_adapter import HiringCafeAdapter
from sources.adapters.linkedin_guest_adapter import LinkedInGuestAdapter
from sources.adapters.naukri_adapter import NaukriAdapter
from sources.adapters.public_feeds_adapter import PublicFeedsAdapter
from sources.adapters.recruitee_adapter import RecruiteeAdapter
from sources.adapters.search_adapter import SearchDiscoveryAdapter
from sources.adapters.smartrecruiters_adapter import SmartRecruitersAdapter
from sources.adapters.teamtailor_adapter import TeamtailorAdapter
from sources.adapters.url_resolver_adapter import UrlResolverAdapter
from sources.adapters.watchlist_ats_adapter import WatchlistATSAdapter
from sources.adapters.workday_adapter import WorkdayAdapter
from sources.base import SourceAdapter
from sources.circuit import is_open

_ADAPTERS: dict[str, type[SourceAdapter]] = {
    "watchlist_ats": WatchlistATSAdapter,
    "workday": WorkdayAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "recruitee": RecruiteeAdapter,
    "teamtailor": TeamtailorAdapter,
    "aggregators": AggregatorsAdapter,
    "search": SearchDiscoveryAdapter,
    "naukri": NaukriAdapter,
    "apify": ApifyAdapter,
    "public_feeds": PublicFeedsAdapter,
    "hiringcafe": HiringCafeAdapter,
    "url_resolver": UrlResolverAdapter,
    "gmail": GmailAdapter,
    "linkedin_guest": LinkedInGuestAdapter,
}

# Legacy / optional sources — not in the default registry adapters().
# Kept as labels for profile toggles / docs; do not re-enable without an adapter.
# Quarantined from happy-path discovery (Karpathy: short happy path).
LEGACY_SOURCES = {
    "wellfound", "icims",
    "weworkremotely", "workingnomads", "nodesk", "jobspresso",
    "skipthedrive", "simplyhired", "monster", "glassdoor",
    "careerbuilder", "remoteco", "linkedin",
}


def _apify_last(names: list[str]) -> list[str]:
    """Keep free sources first; paid Apify always runs after them."""
    free = [n for n in names if n != "apify"]
    paid = [n for n in names if n == "apify"]
    return free + paid


class SourceRegistry:
    def __init__(self, enabled: list[str] | None = None):
        self.enabled = list(enabled if enabled is not None else SOURCE_ENABLED)
        if (
            enabled is None
            and LINKEDIN_SOURCE_CONFIG.get("enabled", True)
            and "linkedin_guest" not in self.enabled
        ):
            self.enabled.append("linkedin_guest")
        # Workday boards are driven by portals.yml — enable whenever the adapter
        # is registered and the profile didn't explicitly disable sources.
        if enabled is None and "workday" not in self.enabled:
            self.enabled.append("workday")
        # Free SmartRecruiters / Recruitee boards from portals.yml.
        if enabled is None and "smartrecruiters" not in self.enabled:
            self.enabled.append("smartrecruiters")
        if enabled is None and "recruitee" not in self.enabled:
            self.enabled.append("recruitee")
        if enabled is None and "teamtailor" not in self.enabled:
            self.enabled.append("teamtailor")
        # Free public job APIs (Arbeitnow, Jobicy, and Adzuna when keyed).
        if enabled is None and "public_feeds" not in self.enabled:
            self.enabled.append("public_feeds")
        # hiring.cafe: sitemap-driven and keyword-first, so it costs a few
        # fetches rather than a crawl.
        if enabled is None and "hiringcafe" not in self.enabled:
            self.enabled.append("hiringcafe")
        # Paid Apify always runs last so free sources fill the inbox first.
        self.enabled = _apify_last(self.enabled)

    def adapters(self) -> list[SourceAdapter]:
        out: list[SourceAdapter] = []
        for name in self.enabled:
            if name == "aggregators" and not _cfg.WANTS_REMOTE:
                continue
            if name == "url_resolver" and not DISCOVERY_RESOLVE_PIPELINE:
                continue
            if name == "search" and not DISCOVERY_SEARCH_QUERIES:
                continue
            if is_open(name):
                continue
            cls = _ADAPTERS.get(name)
            if not cls:
                from plugins.registry import get_plugin
                cls = get_plugin(name)
            if cls:
                out.append(cls())
        return out

    def health(self, live: bool = False) -> dict[str, dict]:
        result = {}
        for name, cls in _ADAPTERS.items():
            if name not in self.enabled:
                result[name] = {"enabled": False}
                continue
            if is_open(name):
                result[name] = {"enabled": True, "circuit": "open"}
                continue
            if live:
                h = cls().health_check()
                result[name] = {"enabled": True, "ok": h.ok, "message": h.message}
            else:
                result[name] = {"enabled": True, "ok": None, "message": "not_checked"}
        result["linkedin"] = {
            "enabled": LINKEDIN_SOURCE_CONFIG.get("enabled", False),
            "mode": LINKEDIN_SOURCE_CONFIG.get("mode", "scrape_only"),
        }
        if "gmail" in self.enabled:
            result.setdefault("gmail", {"enabled": True, "ok": None, "message": "not_checked"})
        return result


def get_registry() -> SourceRegistry:
    return SourceRegistry()
