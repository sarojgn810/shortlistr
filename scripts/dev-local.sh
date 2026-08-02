#!/usr/bin/env bash
# Thin shim → the cross-platform Python launcher (automation/launcher.py).
# Kept for muscle memory / older docs; the real logic lives in the CLI now.
exec python3 -m automation.cli dev "$@"
