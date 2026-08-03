"""Interview questions should be about the posting, not the job family.

Every SRE role produced the same ten questions — a payment-processing SLO, alert
fatigue, a zero-downtime database migration — regardless of employer or
description. Those banks were written as a fallback for when web research finds
nothing, but research needs a search key, so on most installs the fallback is
the only thing anyone ever sees.

The job description is already on hand and is what the interview will be about,
so it is used directly. On two real SRE postings this took the overlap from
"identical" to zero: Microsoft's asked about Azure Data Factory and Cosmos DB,
Priceline's about OpenTelemetry and telemetry pipeline cost.

The static banks stay as the fallback. A generic question beats none.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from processors.generate_prep import _llm_practice_questions

JD = "You will own Kubernetes on Azure, build ELT with Data Factory, and run on-call." * 6


def _provider(reply, calls=None):
    class P:
        def is_available(self): return True

        def complete(self, prompt, system="", max_tokens=1024, json_mode=False):
            if calls is not None:
                calls.append({"prompt": prompt, "json_mode": json_mode})
            if isinstance(reply, Exception):
                raise reply
            return reply
    return P()


def _reply(*questions):
    return json.dumps({"questions": list(questions)})


# ── when it works ────────────────────────────────────────────────────────────

def test_questions_come_back_with_category_and_hint(monkeypatch):
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: _provider(_reply(
        {"category": "TECHNICAL", "question": "How would you shard this?",
         "hint": "keys, rebalancing"})))

    out = _llm_practice_questions("Acme", "SRE", JD, "sre")
    assert out == [("FROM THIS POSTING · TECHNICAL", "How would you shard this?", "keys, rebalancing")]


def test_company_fit_is_not_prefixed_as_practice(monkeypatch):
    """"COMPANY FIT" is its own heading in the guide, not a practice drill."""
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: _provider(_reply(
        {"category": "COMPANY FIT", "question": "Why us?", "hint": "product, blog"})))

    assert _llm_practice_questions("Acme", "SRE", JD, "sre")[0][0] == "COMPANY FIT"


def test_the_job_description_is_what_gets_sent(monkeypatch):
    """The whole point — questions grounded in this posting."""
    calls: list[dict] = []
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: _provider(
        _reply({"category": "TECHNICAL", "question": "q", "hint": "h"}), calls))

    _llm_practice_questions("Acme", "Senior SRE", JD, "sre")
    prompt = calls[0]["prompt"]
    assert "Data Factory" in prompt, "the description was not included"
    assert "Acme" in prompt and "Senior SRE" in prompt
    assert calls[0]["json_mode"] is True


def test_an_unknown_category_becomes_technical(monkeypatch):
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: _provider(_reply(
        {"category": "WHATEVER", "question": "q", "hint": "h"})))

    assert _llm_practice_questions("Acme", "SRE", JD, "sre")[0][0] == "FROM THIS POSTING · TECHNICAL"


def test_a_missing_category_becomes_technical(monkeypatch):
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: _provider(
        _reply({"question": "q"})))

    cat, question, hint = _llm_practice_questions("Acme", "SRE", JD, "sre")[0]
    assert cat == "FROM THIS POSTING · TECHNICAL" and question == "q" and hint == ""


def test_the_list_is_capped(monkeypatch):
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: _provider(_reply(
        *[{"category": "TECHNICAL", "question": f"q{i}"} for i in range(40)])))

    assert len(_llm_practice_questions("Acme", "SRE", JD, "sre")) == 12


def test_blank_questions_are_dropped(monkeypatch):
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: _provider(_reply(
        {"question": "  "}, {"question": "real one"}, "not a dict")))

    out = _llm_practice_questions("Acme", "SRE", JD, "sre")
    assert [q for _, q, _ in out] == ["real one"]


# ── when it does not ─────────────────────────────────────────────────────────

def test_no_job_description_means_no_call(monkeypatch):
    called: list[int] = []
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: called.append(1))

    assert _llm_practice_questions("Acme", "SRE", "", "sre") == []
    assert not called, "asked the model to write questions about nothing"


def test_no_provider_falls_back_quietly(monkeypatch):
    monkeypatch.setattr("llm.get_llm", lambda *a, **k: None)
    assert _llm_practice_questions("Acme", "SRE", JD, "sre") == []


def test_an_unavailable_provider_falls_back(monkeypatch):
    class Down:
        def is_available(self): return False

        def complete(self, *a, **k): raise AssertionError("should not be called")

    monkeypatch.setattr("llm.get_llm", lambda *a, **k: Down())
    assert _llm_practice_questions("Acme", "SRE", JD, "sre") == []


def test_unparseable_output_falls_back(monkeypatch):
    monkeypatch.setattr("llm.get_llm",
                        lambda *a, **k: _provider("I'd rather not answer that."))
    assert _llm_practice_questions("Acme", "SRE", JD, "sre") == []


def test_a_provider_error_falls_back(monkeypatch):
    monkeypatch.setattr("llm.get_llm",
                        lambda *a, **k: _provider(RuntimeError("rate limited")))
    assert _llm_practice_questions("Acme", "SRE", JD, "sre") == []


def test_a_provider_without_json_mode_still_works(monkeypatch):
    """Anthropic, OpenAI and Grok are still on the three-argument signature."""
    class Old:
        def is_available(self): return True

        def complete(self, prompt, system="", max_tokens=1024):
            return _reply({"category": "TECHNICAL", "question": "q", "hint": "h"})

    monkeypatch.setattr("llm.get_llm", lambda *a, **k: Old())
    assert len(_llm_practice_questions("Acme", "SRE", JD, "sre")) == 1


# ── the fallback bank is still there ─────────────────────────────────────────

def test_the_static_bank_still_answers_for_a_known_role():
    from processors.generate_prep import _fallback_practice_questions

    out = _fallback_practice_questions("sre", "Acme")
    assert out, "the fallback must survive — a generic question beats none"
    assert any("COMPANY FIT" == cat for cat, _, _ in out)
