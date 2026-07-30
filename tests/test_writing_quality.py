"""Tests for the writing quality layer (banned fluff / pattern cleanup)."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from writing.sanitize import sanitize, sanitize_blocks
from writing.self_check import invents_unsupported_tokens, self_check
from writing.style import STYLE_BLOCK, with_style


def test_sanitize_removes_banned_words():
    text = "We leverage robust pipelines to utilize cutting-edge tooling."
    out = sanitize(text, mode="prose")
    low = out.lower()
    assert "leverage" not in low
    assert "robust" not in low
    assert "utilize" not in low
    assert "cutting-edge" not in low
    assert "pipeline" in low or "tool" in low


def test_sanitize_cuts_throat_clearing_and_binary_contrast():
    text = (
        "Here's the thing, the eval matters. "
        "It's not the model. It's the eval harness."
    )
    out = sanitize(text, mode="prose")
    low = out.lower()
    assert "here's the thing" not in low
    assert "it's not the model" not in low
    assert "eval" in low


def test_sanitize_reduces_em_dashes_in_short_copy():
    text = "Built the platform — shipped weekly — owned on-call."
    out = sanitize(text, mode="prose")
    assert "—" not in out
    assert "shipped" in out.lower()


def test_label_mode_keeps_fit_reason_shape():
    reason = "title match; JD skills: terraform, python; preferred location"
    out = sanitize(reason, mode="label")
    assert "title match" in out
    assert "terraform" in out
    # Fluff still stripped in label mode
    fluffy = sanitize("title match; leverage skills", mode="label")
    assert "leverage" not in fluffy.lower()
    assert "title match" in fluffy


def test_self_check_flags_slop():
    dirty = "Experts agree this marks a pivotal moment. Let's dive in."
    check = self_check(dirty, strict=True)
    assert check["ok"] is False
    assert check["hits"]

    clean = "Cut deploy time from 40 minutes to 4 using Terraform modules."
    assert self_check(clean, strict=True)["ok"] is True


def test_with_style_is_idempotent():
    once = with_style("Be helpful.")
    twice = with_style(once)
    assert once.count("Writing style (mandatory):") == 1
    assert twice.count("Writing style (mandatory):") == 1
    assert STYLE_BLOCK in once


def test_sanitize_blocks_preserves_keys():
    blocks = {
        "A": "Role at Acme",
        "B": "We leverage robust Kubernetes clusters.",
        "G": "Likely real ATS posting",
    }
    out = sanitize_blocks(blocks, mode="prose")
    assert set(out) == set(blocks)
    assert "leverage" not in out["B"].lower()
    assert "robust" not in out["B"].lower()
    assert "Kubernetes" in out["B"] or "kubernetes" in out["B"].lower()


def test_invents_unsupported_tokens_catches_fake_metric():
    draft = "Cut latency 87% at MegaCorp using QuuxDB."
    evidence = "Worked on payment APIs with Postgres."
    invented = invents_unsupported_tokens(draft, evidence)
    assert any("87" in x or "MegaCorp" in x or "QuuxDB" in x for x in invented)


def test_cover_letter_falls_back_on_heavy_slop(tmp_path, monkeypatch):
    import processors.cover_letter as cl

    monkeypatch.setattr(cl, "_cv_markdown", lambda: "# Jane\n## Skills\nPython, Terraform\n")
    monkeypatch.setattr(
        cl,
        "CANDIDATE",
        {"name": "Jane", "email": "j@x.com", "phone": "", "linkedin": "", "github": "", "years_exp": "8"},
        raising=False,
    )

    class FakeLLM:
        def is_available(self):
            return True

        def complete(self, prompt, system="", max_tokens=600):
            return (
                "I am a highly motivated professional with a proven track record. "
                "Experts agree I leverage robust cutting-edge paradigms. "
                "This marks a pivotal moment. Let's dive in."
            )

    with patch("llm.get_llm", return_value=FakeLLM()):
        result = cl.generate_cover_letter(
            {"company": "Acme", "title": "SRE", "jd_snippet": "Need Terraform and Python"}
        )
    assert result["mode"] in ("llm", "template")
    body = result["body"].lower()
    assert "proven track record" not in body
    assert "highly motivated professional" not in body
    assert "pivotal moment" not in body


def test_linkedin_polish_rejects_invented_employer():
    from linkedin_optimizer.rewriter import maybe_llm_polish

    draft = "SRE focused on Terraform and Kubernetes."
    evidence = "Terraform Kubernetes AWS on-call"

    class FakeLLM:
        def is_available(self):
            return True

        def complete(self, prompt, system="", max_tokens=900):
            return (
                "Passionate SRE at MegaCorp who cut MTTR 99% using QuuxDB synergy."
            )

    with patch("llm.get_llm", return_value=FakeLLM()):
        out, mode = maybe_llm_polish(draft, "about", "sre", evidence=evidence)
    assert mode == "heuristic"
    assert out == draft


def test_eval_sanitizes_blocks_keeps_score(monkeypatch, tmp_path):
    from eval import service as ev

    payload = {
        "score": 4.2,
        "legitimacy": "likely",
        "company": "Acme",
        "role": "SRE",
        "blocks": {
            "A": "SRE at Acme",
            "B": "We leverage robust Kubernetes.",
            "C": "Remote",
            "D": "Gap: Go",
            "E": "Apply via ATS",
            "F": "Ask about on-call",
            "G": "ATS host looks real",
        },
    }

    class FakeLLM:
        def is_available(self):
            return True

        def complete(self, prompt, system="", max_tokens=4096):
            assert "Writing style (mandatory):" in system
            return json.dumps(payload)

    monkeypatch.setattr(ev, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(ev.store, "upsert_job", lambda *a, **k: None)
    monkeypatch.setattr(ev.store, "audit", lambda *a, **k: None)
    monkeypatch.setattr(ev.store, "db", MagicMock())

    result = ev.evaluate_job_text(
        "Need Kubernetes and on-call experience",
        url="",
        company="Acme",
        role="SRE",
        job_id="",
        cv_text="Kubernetes on-call Terraform",
    )
    assert result.score == 4.2
    assert result.legitimacy == "likely"
    assert "leverage" not in result.blocks["B"].lower()
    assert "robust" not in result.blocks["B"].lower()


def test_chat_answer_sanitized_tool_json_untouched():
    from agent import chat as chat_mod

    class FakeLLM:
        def is_available(self):
            return True

        def complete(self, prompt, system="", max_tokens=800):
            return json.dumps(
                {
                    "action": "answer",
                    "text": "Here's the thing, we leverage robust discovery.",
                }
            )

    with patch("llm.get_llm", return_value=FakeLLM()):
        with patch.object(chat_mod.registry, "list_tools", return_value=[]):
            res = chat_mod.chat("how is discover?")
    reply = res["reply"].lower()
    assert "here's the thing" not in reply
    assert "leverage" not in reply
    assert "robust" not in reply
