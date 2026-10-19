"""#2661: canonical lesson store / learning_closure read errors reach the caller.

Found by the #2651 live fault-injection witness (#2638 issuecomment-6256790914):
a ledger that is a directory, garbage, or chmod 000 still read as "no lessons",
and an unreadable learning_closure.jsonl still read as "no patterns". Every
fault here is a real file fault inside tmp_path; the store and retrieval code
under test run unpatched.
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import nexus.services.local_heal.memory_retrieval_adapter as adapter
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.repair_pattern_retrieval import (
    retrieve_successful_repair_patterns,
)

ORCH_LOGGER = "nexus.services.local_heal.orchestrator"


def _make_dir(path: Path) -> None:
    path.mkdir()


def _make_garbage(path: Path) -> None:
    path.write_bytes(b"\x00\xffnot json at all\n{broken\n[1, 2]\n")


def _make_unreadable(path: Path) -> None:
    path.write_text('{"lesson_id": "L1"}\n', encoding="utf-8")
    path.chmod(0)


@pytest.fixture
def restore_modes(tmp_path):
    yield
    for root, dirs, files in os.walk(tmp_path):
        for name in dirs + files:
            try:
                os.chmod(os.path.join(root, name), 0o700)
            except OSError:
                pass


def _require_permission_enforced(path: Path) -> None:
    if os.access(path, os.R_OK):  # pragma: no cover - only when running as root
        pytest.fail("chmod 000 file is still readable (running as root?)")


# --- canonical lesson store --------------------------------------------------


class _EmptyComposite:
    def query(self, **_k):
        return []


def _render_with_ledger(monkeypatch, ledger: Path) -> SimpleNamespace:
    monkeypatch.setattr(
        adapter,
        "CanonicalLessonStore",
        functools.partial(adapter.CanonicalLessonStore, path=ledger),
    )
    monkeypatch.setattr(adapter, "NexusCompositeLessonStore", _EmptyComposite)
    op = SimpleNamespace(
        instance_id="inst-2661",
        memory_enabled=True,
        _memory_influence_trace=SimpleNamespace(selected_ids=["L1"], prompt_included=False),
        problem_statement="fix the add function",
        verifier_stderr_excerpt="",
        retrieved_lesson_ids=None,
    )
    text, ids = object.__new__(HealOrchestrator)._render_memory_lessons(
        SimpleNamespace(op=op), "a.py"
    )
    assert (text, ids) == ("", [])  # fallback behaviour unchanged
    return op


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        (_make_dir, "IsADirectoryError"),
        (_make_garbage, "CanonicalLedgerUnreadable"),
        (_make_unreadable, "PermissionError"),
    ],
    ids=["directory", "garbage", "chmod000"],
)
def test_canonical_ledger_fault_is_recorded(
    monkeypatch, caplog, tmp_path, restore_modes, fault, expected
):
    ledger = tmp_path / "learning_lessons.jsonl"
    fault(ledger)
    if fault is _make_unreadable:
        _require_permission_enforced(ledger)
    with caplog.at_level(logging.WARNING, logger=ORCH_LOGGER):
        op = _render_with_ledger(monkeypatch, ledger)
    assert op._memory_canonical_store_error == expected
    assert any("canonical lesson store query failed" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("content", [None, ""], ids=["missing", "empty"])
def test_canonical_ledger_missing_or_empty_has_no_error(monkeypatch, tmp_path, content):
    ledger = tmp_path / "learning_lessons.jsonl"
    if content is not None:
        ledger.write_text(content, encoding="utf-8")
    op = _render_with_ledger(monkeypatch, ledger)
    assert not hasattr(op, "_memory_canonical_store_error")


# --- learning_closure retrieval ----------------------------------------------


def test_retrieve_patterns_reports_permission_error_to_sink(tmp_path, restore_modes):
    path = tmp_path / "learning_closure.jsonl"
    _make_unreadable(path)
    _require_permission_enforced(path)
    errors: list[str] = []
    assert retrieve_successful_repair_patterns(path, limit=5, error_sink=errors) == []
    assert len(errors) == 1 and errors[0].startswith("PermissionError")
    # Without a sink the legacy fail-open contract is unchanged.
    assert retrieve_successful_repair_patterns(path, limit=5) == []


class _NoneClient:
    def generate(self, **_kw):
        return None  # injected empty model output; no model is called


def _semantic_retry_telemetry(monkeypatch, tmp_path: Path, closure: Path) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(HealOrchestrator, "_learning_closure_path", staticmethod(lambda: closure))

    class PatchSynthesisPhase:  # detected by class name
        llm_client = _NoneClient()

    orch = HealOrchestrator(phases=[PatchSynthesisPhase()], governance_gate=None)
    op = SimpleNamespace(
        instance_id="inst-2661-closure",
        task_id="inst-2661-closure",
        memory_enabled=False,
        _memory_influence_trace=object(),
        problem_statement="fix add",
        verifier_stderr_excerpt="",
        verifier_stdout_excerpt="AssertionError: add(1,2) == 3",
        retrieved_lesson_ids=None,
        model_decisions=[],
        attempt=1,
        repo_dir=repo,
        final_patch=(
            "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n"
            "-    return a - b\n+    return a * b\n"
        ),
        localized_files=[SimpleNamespace(path="calc.py")],
        plan=SimpleNamespace(search_symbols=["add"]),
        user_prompt="fix add",
        failure_class="verification_failed",
    )
    orch._attempt_semantic_retry(
        SimpleNamespace(op=op), "AssertionError: add(1,2)==3", "verification_failed"
    )
    telemetry = getattr(op, "_semantic_retry_telemetry", None)
    assert isinstance(telemetry, dict)
    return telemetry


@pytest.mark.parametrize(
    ("fault", "expected"),
    [(_make_unreadable, "PermissionError"), (_make_dir, "IsADirectoryError")],
    ids=["chmod000", "directory"],
)
def test_unreadable_learning_closure_reaches_research_error(
    monkeypatch, caplog, tmp_path, restore_modes, fault, expected
):
    closure = tmp_path / "learning_closure.jsonl"
    fault(closure)
    if fault is _make_unreadable:
        _require_permission_enforced(closure)
    with caplog.at_level(logging.WARNING, logger=ORCH_LOGGER):
        telemetry = _semantic_retry_telemetry(monkeypatch, tmp_path, closure)
    assert telemetry["semantic_retry_research_error"].startswith(expected)
    assert telemetry["semantic_retry_research_pattern_count"] == 0
    assert any("repair pattern retrieval failed" in r.getMessage() for r in caplog.records)


def test_missing_learning_closure_has_no_research_error(monkeypatch, tmp_path):
    telemetry = _semantic_retry_telemetry(
        monkeypatch, tmp_path, tmp_path / "learning_closure.jsonl"
    )
    assert telemetry["semantic_retry_research_error"] == ""
