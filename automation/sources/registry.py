"""Source registry — enabled adapters from profile config."""

from __future__ import annotations

import config as _cfg
from config import SOURCE_ENABLED, LINKEDIN_SOURCE_CONFIG, DISCOVERY_RESOLVE_PIPELINE, DISCOVERY_SEARCH_QUERIES
from sources.adapters.aggregators_adapter import AggregatorsAdapter
from sources.adapters.apify_adapter import ApifyAdapter
from sources.adapters.gmail_adapter import GmailAdapter
from sources.adapters.naukri_adapter import NaukriAdapter
from sources.adapters.search_adapter import SearchDiscoveryAdapter
from sources.adapters.url_resolver_adapter import UrlResolverAdapter
from sources.adapters.watchlist_ats_adapter import WatchlistATSAdapter
from sources.base import SourceAdapter
from sources.circuit import is_open

_ADAPTERS: dict[str, type[SourceAdapter]] = {
    "watchlist_ats": WatchlistATSAdapter,
    "aggregators": AggregatorsAdapter,
    "search": SearchDiscoveryAdapter,
    "naukri": NaukriAdapter,
    "apify": ApifyAdapter,
    "url_resolver": UrlResolverAdapter,
    "gmail": GmailAdapter,
}

# Legacy / optional sources (disabled by default)
LEGACY_SOURCES = {
    "workday", "smartrecruiters", "wellfound", "icims",
    "weworkremotely", "workingnomads", "nodesk", "jobspresso",
    "skipthedrive", "simplyhired", "monster", "glassdoor",
    "careerbuilder", "remoteco", "linkedin",
}


class SourceRegistry:
    def __init__(self, enabled: list[str] | None = None):
        self.enabled = enabled if enabled is not None else SOURCE_ENABLED

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
