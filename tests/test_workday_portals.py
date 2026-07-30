"""Workday board parsing from portals / ATS detection URLs."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


def test_parse_workday_url_strips_locale_and_deep_paths():
    from portals_config import parse_workday_url

    assert parse_workday_url(
        "https://zendesk.wd1.myworkdayjobs.com/en-US/zendesk"
    ) == ("zendesk", "1", "zendesk")
    assert parse_workday_url(
        "https://paloaltonetworks.wd5.myworkdayjobs.com/en-US/panwexternalcareers/introduction"
    ) == ("paloaltonetworks", "5", "panwexternalcareers")
    assert parse_workday_url("https://workday.wd5.myworkdayjobs.com/Workday") == (
        "workday",
        "5",
        "Workday",
    )
    assert parse_workday_url("https://example.com/careers") is None


def test_get_workday_boards_from_portals(tmp_path, monkeypatch):
    import portals_config as pc
    import yaml

    portals = tmp_path / "portals.yml"
    portals.write_text(
        yaml.safe_dump(
            {
                "tracked_companies": [
                    {
                        "name": "Zendesk",
                        "careers_url": "https://zendesk.wd1.myworkdayjobs.com/en-US/zendesk",
                        "scan_method": "workday",
                        "enabled": True,
                    },
                    {
                        "name": "Ignore Me",
                        "careers_url": "https://example.com/careers",
                        "scan_method": "playwright",
                        "enabled": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pc, "PORTALS_PATH", str(portals))
    monkeypatch.setattr(pc, "PORTALS_EXAMPLE_PATH", str(tmp_path / "missing.yml"))

    boards = pc.get_workday_boards()
    assert boards == [("zendesk", "1", "zendesk", "Zendesk")]
