"""Source adapter protocol — fetch raw jobs without filtering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from models.job import JobRecord


@dataclass
class SourceHealth:
    name: str
    ok: bool
    message: str = ""
    raw_count: int = 0


@dataclass
class FetchStats:
    source: str
    raw_count: int = 0
    error: str = ""
    duration_ms: int = 0


class SourceAdapter(ABC):
    """Pluggable job discovery source. fetch_raw returns unfiltered jobs."""

    name: str = "base"

    @abstractmethod
    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        ...

    def health_check(self) -> SourceHealth:
        try:
            jobs, stats = self.fetch_raw(log_totals=False)
            return SourceHealth(self.name, True, "ok", stats.raw_count)
        except Exception as e:
            return SourceHealth(self.name, False, str(e), 0)
