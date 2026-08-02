"""The evaluation score has to carry information.

Measured on a real inbox of 158 jobs, it did not. Scores clustered at 4.2/4.5/4.8
with 96% inside 4.2-4.8, and — the part that gives it away — the average was
flat against the discovery fit score:

    fit <40   61 jobs   avg eval 4.42
    fit 40-59 36 jobs   avg eval 4.48
    fit 60-79 58 jobs   avg eval 4.31

Jobs discovery rated below 40 scored *higher* than jobs it rated 60-79. A number
uncorrelated with fit cannot be ranking anything.

The cause was the prompt: the whole rubric was "Be honest. Score below 4.0 if
not a strong fit", which names one anchor and no bands. Adding bands alone did
not fix it — asking for a holistic number gets a holistic answer. Making the
model first enumerate the posting's hard requirements and mark each met/unmet,
and derive the score from that, took the spread from 3 distinct values to 6.

Keeping the list is the other half: it makes the score explainable, and "you
miss these two requirements" is the part a cover letter can answer.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


# ── keeping the rows ─────────────────────────────────────────────────────────

def test_requirements_are_kept_with_their_evidence():
    from eval.service import _clean_must_haves

    out = _clean_must_haves([
        {"req": "5+ years SRE", "met": True, "evidence": "9 years as SRE"},
        {"req": "Go in production", "met": False, "evidence": ""},
    ])
    assert out == [
        {"req": "5+ years SRE", "met": True, "evidence": "9 years as SRE"},
        {"req": "Go in production", "met": False, "evidence": ""},
    ]


def test_a_missing_met_flag_counts_as_unmet():
    """Silence is not evidence — an unmarked requirement must not read as met."""
    from eval.service import _clean_must_haves

    assert _clean_must_haves([{"req": "Kubernetes"}])[0]["met"] is False


def test_rows_without_a_requirement_are_dropped():
    from eval.service import _clean_must_haves

    out = _clean_must_haves([{"req": "  ", "met": True}, {"met": True}, "nonsense"])
    assert out == []


def test_a_non_list_is_not_a_gap_list():
    from eval.service import _clean_must_haves

    for junk in (None, {}, "Kubernetes", 7):
        assert _clean_must_haves(junk) == []


def test_the_list_is_capped():
    """A model that enumerates the entire JD must not bloat every stored row."""
    from eval.service import _clean_must_haves

    assert len(_clean_must_haves([{"req": f"r{i}", "met": True} for i in range(90)])) == 25


def test_long_text_is_truncated():
    from eval.service import _clean_must_haves

    out = _clean_must_haves([{"req": "x" * 900, "met": True, "evidence": "y" * 900}])
    assert len(out[0]["req"]) == 300
    assert len(out[0]["evidence"]) == 300


# ── carrying them through ────────────────────────────────────────────────────

def _result(**kw):
    from eval.service import EvalResult

    base = dict(score=3.5, legitimacy="likely", company="Acme", role="SRE",
                blocks={"A": "x"}, raw={})
    base.update(kw)
    return EvalResult(**base)


def test_must_haves_survive_into_the_stored_row():
    """Computed and thrown away is the same as never computed."""
    rows = [{"req": "Terraform", "met": False, "evidence": ""}]
    assert _result(must_haves=rows).to_dict()["must_haves"] == rows


def test_an_evaluation_without_them_still_stores_cleanly():
    """Older rows and the template path have no list; that is not an error."""
    assert _result().to_dict()["must_haves"] == []


# ── a timeout is not worth retrying ──────────────────────────────────────────
#
# Ollama's client timeout is 120s and the eval retried once, so a slow local
# model made a 240-second HTTP request. The dev proxy in front of the API hangs
# up long before that, which reached the browser as "socket hang up /
# ECONNRESET" and a 500 with no body — while the API carried on, eventually gave
# up, and stored a heuristic result. One cause, both symptoms: an error the user
# cannot read, and "Basic score" on a machine with a working local model.

def _provider(exc, calls):
    class P:
        def is_available(self): return True

        def complete(self, *a, **k):
            calls.append(1)
            raise exc
    return P()


def test_a_timeout_is_not_retried(monkeypatch):
    import requests

    from eval import service

    calls: list[int] = []
    monkeypatch.setattr(service, "get_llm",
                        lambda *a, **k: _provider(requests.Timeout("read timed out"), calls))

    res = service.evaluate_job_text("kubernetes on-call " * 40, company="Acme", role="SRE")
    assert len(calls) == 1, "waited out the provider timeout twice"
    assert res.eval_mode == "template"


def test_malformed_json_is_still_retried(monkeypatch):
    """The retry exists for exactly this — a model that fumbles the format once."""
    from eval import service

    calls: list[int] = []
    monkeypatch.setattr(service, "get_llm",
                        lambda *a, **k: _provider(ValueError("No JSON object"), calls))

    service.evaluate_job_text("kubernetes on-call " * 40, company="Acme", role="SRE")
    assert len(calls) == 2, "a bad-JSON attempt should get one more try"


def test_a_dropped_connection_is_not_retried(monkeypatch):
    import requests

    from eval import service

    calls: list[int] = []
    monkeypatch.setattr(service, "get_llm",
                        lambda *a, **k: _provider(requests.ConnectionError("reset"), calls))

    service.evaluate_job_text("kubernetes on-call " * 40, company="Acme", role="SRE")
    assert len(calls) == 1


# ── what small local models actually return ──────────────────────────────────
#
# On a Windows laptop with qwen3:0.6b — the model an 18GB machine picks — every
# evaluation came back "No JSON object in LLM response" and fell to the
# heuristic, so every card read "Basic score" while the model was running fine.
# It was answering in prose, and qwen3 is a reasoning model that emits a <think>
# block before the answer.

def test_a_reasoning_block_is_not_the_answer():
    from eval.service import _parse_json_response

    assert _parse_json_response(
        '<think>Let me weigh this {carefully}</think>{"score": 4.0}'
    ) == {"score": 4.0}


def test_a_fenced_object_is_unwrapped():
    from eval.service import _parse_json_response

    assert _parse_json_response('```json\n{"score": 4.0}\n```') == {"score": 4.0}


def test_trailing_prose_after_the_object_is_ignored():
    from eval.service import _parse_json_response

    assert _parse_json_response('{"score": 4.0} Hope this helps!') == {"score": 4.0}


def test_prose_with_no_object_still_raises():
    """Tolerance must not become invention."""
    import pytest

    from eval.service import _parse_json_response

    with pytest.raises(ValueError):
        _parse_json_response("I cannot evaluate this posting.")


def test_the_failure_says_what_came_back():
    """"No JSON object in LLM response" is true and useless.

    Two rounds of diagnosis were spent guessing whether the model returned prose,
    returned nothing, or was never called. The reply itself settles all three, so
    it belongs in the message.
    """
    import pytest

    from eval.service import _parse_json_response

    with pytest.raises(ValueError, match="I cannot evaluate"):
        _parse_json_response("I cannot evaluate this posting.")

    with pytest.raises(ValueError, match="0 chars"):
        _parse_json_response("")


def test_json_mode_is_requested_when_the_provider_supports_it(monkeypatch):
    """Ollama's JSON grammar is what stops a small model answering in prose."""
    from eval import service

    seen = {}

    class Provider:
        def is_available(self): return True

        def complete(self, prompt, system="", max_tokens=1024, json_mode=False):
            seen["json_mode"] = json_mode
            return '{"score": 4.0, "legitimacy": "likely", "company": "A", ' \
                   '"role": "R", "blocks": {"A": "x"}}'

    monkeypatch.setattr(service, "get_llm", lambda *a, **k: Provider())
    service.evaluate_job_text("kubernetes " * 60, company="A", role="R")
    assert seen["json_mode"] is True


def test_a_provider_without_json_mode_still_works(monkeypatch):
    """Third-party providers on the old signature must not start failing."""
    from eval import service

    class OldProvider:
        def is_available(self): return True

        def complete(self, prompt, system="", max_tokens=1024):
            return '{"score": 3.5, "legitimacy": "likely", "company": "A", ' \
                   '"role": "R", "blocks": {"A": "x"}}'

    monkeypatch.setattr(service, "get_llm", lambda *a, **k: OldProvider())
    assert service.evaluate_job_text("kubernetes " * 60, company="A", role="R").eval_mode == "llm"


# ── reasoning models must be told not to think out loud ──────────────────────
#
# qwen3.6-27b on Groq answered a full evaluation with 16,877 characters of "I
# will output raw JSON starting with {" and hit the token ceiling before writing
# any of it. response_format alone did not stop that on a long prompt.
# reasoning_effort=none did: 26.5s and a heuristic fallback became 3.9s,
# mode=llm, and 7 must-haves. The same trap applies to the local qwen3 family,
# where Ollama's equivalent is think=False.

def test_groq_json_mode_disables_reasoning():
    from llm.groq_llm import GroqProvider

    sent = {}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    sent.update(kwargs)
                    class M:
                        content = '{"ok": true}'
                    class C:
                        message = M()
                    class R:
                        choices = [C()]
                    return R()

    p = GroqProvider("gsk_test", model="qwen/qwen3.6-27b")
    p._get_client = lambda: FakeClient()
    p.complete("hi", max_tokens=100, json_mode=True)

    assert sent.get("response_format") == {"type": "json_object"}
    assert sent.get("reasoning_effort") == "none"


def test_groq_without_json_mode_asks_for_neither():
    """A plain completion must not be constrained to JSON."""
    from llm.groq_llm import GroqProvider

    sent = {}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    sent.update(kwargs)
                    class M:
                        content = "hello"
                    class C:
                        message = M()
                    class R:
                        choices = [C()]
                    return R()

    p = GroqProvider("gsk_test")
    p._get_client = lambda: FakeClient()
    p.complete("hi", max_tokens=100)

    assert "response_format" not in sent
    assert "reasoning_effort" not in sent


def test_ollama_json_mode_sets_format_and_disables_thinking():
    import types

    import llm.ollama as mod
    from llm.ollama import OllamaProvider

    sent = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self): pass

        def json(self): return {"response": '{"ok": true}'}

    real = mod.requests
    try:
        mod.requests = types.SimpleNamespace(
            post=lambda url, json=None, timeout=None: (sent.update(json or {}), FakeResp())[1],
            ConnectionError=real.ConnectionError,
        )
        OllamaProvider(model="qwen3:0.6b").complete("hi", json_mode=True)
    finally:
        mod.requests = real

    assert sent.get("format") == "json"
    assert sent.get("think") is False


def test_ollama_retries_without_think_on_an_older_build():
    """Ollama before 0.9 rejects `think`; that must not cost the evaluation."""
    import types

    import llm.ollama as mod
    from llm.ollama import OllamaProvider

    attempts = []

    class Resp:
        def __init__(self, code): self.status_code = code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError("should have retried before raising")

        def json(self): return {"response": '{"ok": true}'}

    def post(url, json=None, timeout=None):
        attempts.append(dict(json or {}))
        return Resp(400 if "think" in (json or {}) else 200)

    real = mod.requests
    try:
        mod.requests = types.SimpleNamespace(post=post, ConnectionError=real.ConnectionError)
        out = OllamaProvider(model="qwen3:0.6b").complete("hi", json_mode=True)
    finally:
        mod.requests = real

    assert out == '{"ok": true}'
    assert len(attempts) == 2
    assert "think" in attempts[0] and "think" not in attempts[1]


def test_a_model_that_rejects_reasoning_effort_still_gets_json():
    """Regression: reasoning_effort broke every non-reasoning Groq model.

    Sending it unconditionally with json_mode made llama-3.3-70b — the default —
    answer 400 "`reasoning_effort` is not supported with this model", so every
    evaluation and every generated prep question silently fell back. Only the
    field the model objected to is dropped; the JSON grammar is kept.
    """
    from llm.groq_llm import GroqProvider

    seen: list[dict] = []

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.append(dict(kwargs))
                    if "reasoning_effort" in kwargs:
                        raise RuntimeError(
                            "Error code: 400 - `reasoning_effort` is not "
                            "supported with this model"
                        )
                    class M:
                        content = '{"ok": true}'
                    class C:
                        message = M()
                    class R:
                        choices = [C()]
                    return R()

    p = GroqProvider("gsk_test", model="llama-3.3-70b-versatile")
    p._get_client = lambda: FakeClient()

    assert p.complete("hi", max_tokens=100, json_mode=True) == '{"ok": true}'
    assert len(seen) == 2, "should retry once without the unsupported field"
    assert "reasoning_effort" not in seen[1]
    assert seen[1].get("response_format") == {"type": "json_object"}, (
        "the JSON grammar must survive the retry"
    )
