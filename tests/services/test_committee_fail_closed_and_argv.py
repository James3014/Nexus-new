"""Committee fails closed without a verified candidate; verify argv passes through unchanged."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from nexus.committee import execution_verifier
from nexus.services.capability_registry import build_real_executor_invoker

FIXTURES = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "wiring_fixtures"


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commands: list[Any]) -> dict[str, Any]:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    ws = tmp_path / "committee"
    shutil.copytree(FIXTURES / "committee", ws)
    monkeypatch.chdir(ws)
    proposals = json.loads((ws / "proposals.json").read_text(encoding="utf-8"))
    invoker = build_real_executor_invoker("committee")
    assert invoker is not None
    return invoker({
        "task_id": "t-committee",
        "task_statement": "pick a candidate",
        "route": {"workspace_root": str(ws)},
        "codeintel": {"committee_proposals": proposals, "committee_verify_commands": commands},
    })


def test_no_verified_candidate_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No OS barrier: every candidate is "not_executed:no_os_barrier", so nobody is verified.
    monkeypatch.setattr(execution_verifier.lane, "os_sandbox_available", lambda: False)
    result = _run(tmp_path, monkeypatch, ["python3 repro.py"])
    outcome = result["response"]["outcome"]
    assert [r["verify_result"] for r in outcome["execution_results"]] == [
        execution_verifier.NOT_EXECUTED_NO_BARRIER
    ] * 3
    assert outcome["verdict_count"] >= 2
    assert result["gate_passed"] is False
    assert outcome["semantic_status"] == "FAILED"
    assert outcome["error"] == "COMMITTEE_NO_VERIFIED_CANDIDATE"


def test_verify_argv_lists_reach_the_verifier_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(execution_verifier.lane, "os_sandbox_available", lambda: False)
    result = _run(tmp_path, monkeypatch, [["python3", "repro.py"], "python3 repro.py"])
    records = result["response"]["outcome"]["execution_results"]
    assert records, result
    for record in records:
        # The list stays a list (it used to be str()-flattened into "['python3', 'repro.py']",
        # which the verifier then split into garbage and refused); the string stays a string.
        assert record["commands"] == [["python3", "repro.py"], "python3 repro.py"]
        assert record["verify_result"] != "not_executed:command_not_allowed"
