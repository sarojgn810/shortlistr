# Contributing

Thanks for helping improve Shortlistr. This repo is a **single-user, local-first**
job search engine. Keep changes focused, tested, and free of personal data.

## Before you start

1. Read [AGENTS.md](../AGENTS.md) (data contract) and the ethics section of
   [README.md](../README.md).
2. **Never auto-submit** applications. Prefill-only apply-assist is fine;
   Submit-clicking bots are not.
3. Do not commit `cv.md`, `.env`, `config/profile.yml`, `portals.yml`,
   `data/*`, `reports/*`, `output/*`, or real PII in fixtures — use
   `Alex Candidate` / `Jane Doe` / `example.com`.

## Development setup

```bash
make install
make dashboard-install
make test
cd dashboard && npx tsc --noEmit
```

Day-to-day: `make api` + `make dashboard-dev`, or `make start`.

## Pull requests

- Branch off `main`; one focused change per PR.
- Explain **why** in the PR body (1–3 bullets).
- Include a short test plan (`make test`, manual smoke if UI).
- Follow the design tokens in the dashboard when touching UI
  ([docs/UI_DESIGN_STANDARDS.md](UI_DESIGN_STANDARDS.md)).
- Do not add telemetry, outbound “phone home”, or multi-tenant / referral
  platform concepts here.

## Adding a SourceAdapter

Job discovery sources implement `SourceAdapter` in `automation/sources/base.py`.
Adapters return **raw, unfiltered** `JobRecord` lists. Filtering happens in
`automation/pipeline/filter.py`.

### 1. Create an adapter

```python
# automation/sources/adapters/myboard_adapter.py
from models.job import JobRecord
from sources.base import FetchStats, SourceAdapter

class MyBoardAdapter(SourceAdapter):
    name = "myboard"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        stats = FetchStats(source=self.name)
        jobs: list[JobRecord] = []
        # fetch from API — do NOT filter by title here
        stats.raw_count = len(jobs)
        return jobs, stats
```

Use `sources/fetcher.py` → `cached_get_json()` for HTTP with disk cache and retries.

### 2. Register in the registry

Add to `_ADAPTERS` in `automation/sources/registry.py`.

### 3. Enable in profile (example)

```yaml
# config/profile.yml (local, gitignored)
sources:
  enabled:
    - watchlist_ats
    - aggregators
    - myboard
```

### 4. Tests

Add tests under `tests/` with mocks or recorded fixtures. Never hit live APIs in CI.

```bash
make test
python3 -m pytest tests/test_discovery.py -q
```

## Rules

- **No `_matches()` inside scrapers** — use pipeline / discovery filter helpers.
- **No duplicate company lists** — watchlist companies live in `portals.yml` only.
- **Circuit breaker** — failures tracked in `sources/circuit.py`.
- **Background jobs never apply** — discover / refresh / archive only.

## Code of conduct

See [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
