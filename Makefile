.PHONY: doctor verify normalize normalize-pipeline dedup merge pdf sync-check liveness scan test install status tracker migrate-markdown export-pipeline export-applications bundle worker api explain diff resolve-jobs apply-assist email-routing dev start seed reset uninstall

PYTHON ?= python3
CLI := $(PYTHON) -m automation.cli

doctor:
	$(CLI) doctor

verify:
	$(CLI) verify

normalize:
	$(CLI) normalize

normalize-pipeline:
	$(CLI) normalize-pipeline

dedup:
	$(CLI) dedup

merge:
	$(CLI) merge

pdf:
	$(CLI) pdf $(ARGS)

sync-check:
	$(CLI) sync-check

liveness:
	$(CLI) liveness $(ARGS)

scan:
	$(CLI) scan $(ARGS)

status:
	$(CLI) status

tracker:
	$(CLI) tracker

# Cron entry points (see automation/setup_cron.sh)
ingest:
	$(CLI) ingest $(ARGS)

jobs-sweep:
	$(CLI) jobs-sweep $(ARGS)

explain:
	$(CLI) explain $(ARGS)

diff:
	$(CLI) diff $(ARGS)

resolve-jobs:
	$(CLI) resolve-jobs $(ARGS)

apply-assist:
	$(CLI) apply-assist $(ARGS)

email-routing:
	$(CLI) email-routing $(ARGS)

migrate-markdown:
	$(CLI) migrate-markdown

export-pipeline:
	$(CLI) export-pipeline

export-applications:
	$(CLI) export-applications

bundle:
	$(CLI) bundle $(ARGS)

worker:
	$(CLI) worker $(ARGS)

scheduler:
	$(CLI) scheduler $(ARGS)

telegram:
	$(CLI) telegram $(ARGS)

scan-scheduled:
	$(CLI) scan-scheduled $(ARGS)

# Reload is opt-in in api/main.py; turn it on here so `make api` behaves the way
# the docs promise (edit a backend file -> server picks it up). Without this the
# process silently serves whatever code it started with.
api:
	SHORTLISTR_API_RELOAD=1 $(CLI) api $(ARGS)

seed:
	$(CLI) seed

# Wipe user data (jobs, resume, profile, output) to a backup, leaving a blank
# slate for fresh onboarding. Secrets (.env / keychain) and portals.yml are kept.
reset:
	$(CLI) reset

# Remove Shortlistr from this machine (stops ports, clears keychain + crons,
# prints steps to delete the folder). Use ARGS=--purge-data to also wipe
# résumé / profile / DB / .env before you delete the repo.
uninstall:
	$(CLI) uninstall $(ARGS)

# One command (any OS): install deps, seed files, start stack, open /onboarding
start:
	$(CLI) start

# Start stack only (assumes make install already ran)
dev:
	$(CLI) dev

dashboard-install:
	cd dashboard && npm install

dashboard-dev:
	cd dashboard && npm run dev

dashboard-build:
	cd dashboard && npm run build

evaluate:
	$(CLI) evaluate $(ARGS)

test:
	$(CLI) test

# The same suite without the real LaTeX compiles, which are ~2 minutes of the
# ~2.5. For the inner loop only: `make test` is what must be green before a
# commit, because a real compile is what catches a template that no longer
# builds — and that failure is silent in production, falling back to HTML.
test-fast:
	$(PYTHON) -m pytest tests/ -q -m "not slow"

install:
	pip3 install -r automation/requirements.txt
	playwright install chromium
