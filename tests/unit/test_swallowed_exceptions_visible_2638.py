"""#2638: swallowed exceptions in gateway / local_heal orchestrator are now visible.

Each test forces the failure path and checks that the error is logged (and,
where callers branch on the result, recorded as a distinct field) while the
fallback behaviour stays the same.
"""

from __future__ import annotations

import logging
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.services.gateway import BattlesuitGateway
from nexus.services.local_heal.orchestrator import HealOrchestrator

GATEWAY_LOGGER = "nexus.services.gateway"
ORCH_LOGGER = "nexus.services.local_heal.orchestrator"


def _gateway() -> BattlesuitGateway:
    return object.__new__(BattlesuitGateway)


def _orchestrator() -> HealOrchestrator:
    return object.__new__(HealOrchestrator)


def _ctx(op: Any) -> Any:
    """A minimal HealContext stand-in (only ``op`` is read on these paths)."""
    return SimpleNamespace(op=op)


def _raising_module(monkeypatch, name: str, **attrs) -> None:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)


class _Boom:
    def __getattr__(self, item):
        raise RuntimeError("policy exploded")


# --- gateway -----------------------------------------------------------------


def test_ollama_api_type_policy_failure_is_logged(monkeypatch, caplog):
    monkeypatch.delenv("NEXUS_OLLAMA_API_TYPE", raising=False)
    _raising_module(monkeypatch, "nexus.engine.local_model_policy", LocalModelPolicy=_Boom())
    with caplog.at_level(logging.WARNING, logger=GATEWAY_LOGGER):
        assert _gateway()._ollama_api_type("qwen-test") == "generate"
    assert any(
        "API type lookup failed" in r.getMessage() and "qwen-test" in r.getMessage()
        for r in caplog.records
    )


def test_ollama_options_policy_failure_is_logged(monkeypatch, caplog):
    for key in ("NEXUS_OLLAMA_NUM_CTX", "NEXUS_OLLAMA_NUM_PREDICT"):
        monkeypatch.delenv(key, raising=False)
    _raising_module(monkeypatch, "nexus.engine.local_model_policy", ModelProfile=_Boom())
    with caplog.at_level(logging.WARNING, logger=GATEWAY_LOGGER):
        options = _gateway()._ollama_options("qwen-test")
    assert isinstance(options, dict)
    assert any("options lookup failed" in r.getMessage() for r in caplog.records)


def test_ollama_probe_failure_is_logged_and_reports_unavailable(monkeypatch, caplog):
    import urllib.request

    def _refuse(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setenv("NEXUS_OLLAMA_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    with caplog.at_level(logging.DEBUG, logger=GATEWAY_LOGGER):
        assert _gateway()._ollama_available() is False
    assert any(
        "probe failed" in r.getMessage() and "connection refused" in r.getMessage()
        for r in caplog.records
    )


# --- local_heal orchestrator -------------------------------------------------


def test_render_memory_lessons_outer_failure_records_distinct_error(caplog):
    class _Op(SimpleNamespace):
        @property
        def memory_enabled(self):
            raise RuntimeError("op state corrupt")

    op = _Op(instance_id="inst-1", _memory_influence_trace=object())
    ctx = _ctx(op)
    with caplog.at_level(logging.WARNING, logger=ORCH_LOGGER):
        text, ids = _orchestrator()._render_memory_lessons(ctx, "a.py")
    assert (text, ids) == ("", [])
    assert op._memory_render_error.startswith("RuntimeError: op state corrupt")
    assert any("memory lesson rendering failed" in r.getMessage() for r in caplog.records)


def test_render_memory_lessons_disabled_has_no_error_field():
    op = SimpleNamespace(
        instance_id="inst-2", memory_enabled=False, _memory_influence_trace=object()
    )
    text, ids = _orchestrator()._render_memory_lessons(_ctx(op), "a.py")
    assert (text, ids) == ("", [])
    assert not hasattr(op, "_memory_render_error")


def test_canonical_store_failure_is_recorded(monkeypatch, caplog):
    class _BrokenCanonical:
        def query(self, **_k):
            raise RuntimeError("canonical db locked")

    class _Composite:
        def query(self, **_k):
            return [{"lesson_id": "L1", "summary": "use the guard", "classification": "c"}]

    import nexus.services.local_heal.memory_retrieval_adapter as adapter

    monkeypatch.setattr(adapter, "CanonicalLessonStore", _BrokenCanonical)
    monkeypatch.setattr(adapter, "NexusCompositeLessonStore", _Composite)
    trace = SimpleNamespace(selected_ids=["L1"], prompt_included=False)
    op = SimpleNamespace(
        instance_id="inst-3",
        memory_enabled=True,
        _memory_influence_trace=trace,
        problem_statement="p",
        verifier_stderr_excerpt="",
        retrieved_lesson_ids=None,
    )
    with caplog.at_level(logging.WARNING, logger=ORCH_LOGGER):
        text, ids = _orchestrator()._render_memory_lessons(_ctx(op), "a.py")
    # Composite lessons still render; the canonical failure is visible.
    assert ids == ["L1"]
    assert "use the guard" in text
    assert op._memory_canonical_store_error.startswith("RuntimeError: canonical db locked")
    assert any("canonical lesson store query failed" in r.getMessage() for r in caplog.records)


def test_belief_budget_failure_records_error_and_keeps_default(monkeypatch, caplog):
    class _BrokenEngine:
        def __init__(self):
            raise RuntimeError("belief store unreadable")

    import nexus.core.belief_engine as belief_engine

    monkeypatch.setattr(belief_engine, "BeliefEngine", _BrokenEngine)
    orch = _orchestrator()
    calls: list[str] = []
    monkeypatch.setattr(
        orch, "_attempt_semantic_retry", lambda ctx, report, fc: calls.append(report) or False
    )
    op = SimpleNamespace(instance_id="inst-4", verifier_stdout_excerpt="")
    with caplog.at_level(logging.WARNING, logger=ORCH_LOGGER):
        assert orch._attempt_multipass_semantic_retry(_ctx(op), "r", "f") is False
    assert op._belief_budget_error.startswith("RuntimeError: belief store unreadable")
    assert op._belief_budget_used is False
    assert op._budget_policy == "moderate"
    assert calls == ["r"]
    assert any("belief retry budget resolution failed" in r.getMessage() for r in caplog.records)


def test_abort_receipt_write_failure_is_logged(monkeypatch, caplog):
    import nexus.services.local_heal.orchestrator as orch_mod

    def _fail(**_k):
        raise OSError("disk full")

    monkeypatch.setattr(orch_mod, "write_abort_receipt", _fail)
    op = SimpleNamespace(instance_id="inst-5", repo_dir="/nonexistent", model_decisions=[])
    with caplog.at_level(logging.WARNING, logger=ORCH_LOGGER):
        _orchestrator()._write_abort_receipt_on_failure(_ctx(op), "patch", "boom")
    assert any(
        "abort receipt write failed" in r.getMessage() and "inst-5" in r.getMessage()
        for r in caplog.records
    )


def test_refresh_trace_status_failure_is_logged(caplog):
    class _FrozenTrace:
        def __setattr__(self, key, value):
            raise AttributeError("frozen")

    op = SimpleNamespace(_memory_influence_trace=_FrozenTrace(), solve_eligible=True)
    with caplog.at_level(logging.WARNING, logger=ORCH_LOGGER):
        _orchestrator()._refresh_memory_trace_verifier_status(_ctx(op))
    assert any("verifier_status" in r.getMessage() for r in caplog.records)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
