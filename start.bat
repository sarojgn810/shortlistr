@echo off
REM Shortlistr one-command launcher for Windows (double-click or run from cmd/PowerShell).
REM Installs deps, seeds files, starts API + dashboard + scheduler, opens onboarding.
python -m automation.cli start %*
