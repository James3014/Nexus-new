"""Group D wiring fixes (2026-10-13): ultra_review, control-plane nodes, judge_panel,
architecture_scout. Unit-level: executors and invokers, no model call (Ollama is mocked)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.engine import llm_judge_providers as providers
from nexus.engine.ultra_review_service import os_sandbox_available
from nexus.services.capability_registry import (
    NOT_EXECUTABLE_CAPABILITY_REASONS,
    build_default_mainchain_invokers,
)


def _plan(**constraints):
    return CapabilityExecutionPlan(
        plan_id="group-d", task_id="group-d", phases=["R"], constraints=dict(constraints)
    )


def _records(families):
    return [
        {
            "run_id": f"r{i}",
            "family": fam,
            "status": "discard",
            "metric": 0.0,
            "rollback_reason": "timeout",
        }
        for i, fam in enumerate(families, start=1)
    ]


# --- control-plane-only nodes -------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(NOT_EXECUTABLE_CAPABILITY_REASONS))
def test_control_plane_node_receipt_says_not_executable(name: str) -> None:
    invoker = build_default_mainchain_invokers(include_postflight_gates=False)[name]
    row = invoker({"task_id": "t-1", "escalate_triggered": True})
    assert row["invoked"] is False
    assert row["skipped"] is True
    assert row["outcome_contributed"] is False
    assert row["skip_reason"] == NOT_EXECUTABLE_CAPABILITY_REASONS[name]
    assert row["execution_state"] == "NOT_EXECUTABLE"
    assert row["physical_callable"] is None
    assert row["telemetry"]["model_calls"] == 0
    assert row["response"]["status"] == "NOT_EXECUTABLE"


# --- architecture_scout --------------------------------------------------------------------


def test_architecture_scout_plans_only_after_real_plateau() -> None:
    receipt = EXECUTOR_REGISTRY["architecture_scout"](
        _plan(asi_failure_records=_records(["flow:retry"] * 4)), "fix the retry timeout"
    )
    assert receipt.gate_passed is True
    assert receipt.outcome["plateau_detected"] is True
    assert receipt.outcome["plan_status"] == "READY"
    assert receipt.outcome["result"]["forbidden_families"] == ["flow:retry"]


@pytest.mark.parametrize(
    "records,reason",
    [
        ([], "insufficient_window"),
        (_records(["a", "b", "a", "a"]), "family_not_stable"),
    ],
)
def test_architecture_scout_fails_closed_without_plateau(records, reason) -> None:
    receipt = EXECUTOR_REGISTRY["architecture_scout"](_plan(asi_failure_records=records), "task")
    assert receipt.invoked is True
    assert receipt.gate_passed is False
    assert receipt.outcome["error"] == f"PLATEAU_NOT_DETECTED:{reason}"
    assert receipt.outcome["plateau_detected"] is False


# --- judge_panel ---------------------------------------------------------------------------

CANDIDATES = [
    {
        "candidate_id": "a",
        "summary": "delete the failing test",
        "evidence_refs": ["pytest: 3 passed"],
    },
    {"candidate_id": "b", "summary": "round the total", "evidence_refs": ["pytest: 4 passed"]},
]


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_ollama(monkeypatch, content: str, seen: list) -> None:
    def fake_urlopen(request, timeout=0):
        seen.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse(
            json.dumps({"model": "qwen3.5:9b", "message": {"content": content}}).encode("utf-8")
        )

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)


def test_judge_panel_blocked_without_authorization(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", raising=False)
    receipt = EXECUTOR_REGISTRY["judge_panel"](_plan(candidate_pool=CANDIDATES), "task")
    assert receipt.gate_passed is False
    assert receipt.outcome["error"] == "BLOCKED_EXTERNAL_AUTH"


def test_judge_panel_skips_without_candidate_pool(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    receipt = EXECUTOR_REGISTRY["judge_panel"](_plan(), "task")
    assert receipt.invoked is False
    assert receipt.outcome["skip_reason"] == "no_candidate_pool"


def test_judge_panel_local_ollama_ranks_the_plan_candidates(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.delenv("NEXUS_LLM_JUDGE_PROVIDERS", raising=False)
    monkeypatch.setenv("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434")
    seen: list = []
    _fake_ollama(monkeypatch, json.dumps({"ranking": ["b", "a"], "reason": "b fixes it"}), seen)
    receipt = EXECUTOR_REGISTRY["judge_panel"](_plan(candidate_pool=CANDIDATES), "fix rounding")
    assert receipt.gate_passed is True, receipt.outcome
    assert receipt.outcome["provider"] == "ollama"
    assert receipt.outcome["judge_model"] == "qwen3.5:9b"
    assert receipt.outcome["ranking"] == ["b", "a"]
    assert receipt.outcome["winner"] == "b"
    assert receipt.outcome["candidate_count"] == 2
    request = seen[0]
    assert request["model"] == "qwen3.5:9b"  # Workforce local_first.classification worker
    sent = json.loads(request["messages"][1]["content"])
    assert sent["candidate_ids"] == ["a", "b"]
    assert "c0" not in json.dumps(sent)


def test_judge_panel_local_only_auth_never_admits_command_judges(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.setenv("NEXUS_LLM_JUDGE_PROVIDERS", "codex")
    monkeypatch.setenv("NEXUS_CODEX_JUDGE_CMD", "false")
    seen: list = []
    _fake_ollama(monkeypatch, json.dumps({"ranking": ["a", "b"]}), seen)
    receipt = EXECUTOR_REGISTRY["judge_panel"](_plan(candidate_pool=CANDIDATES), "task")
    assert receipt.outcome["provider"] == "ollama"
    assert len(seen) == 1


def test_ollama_judge_appends_omitted_ids_and_keeps_model_winner(monkeypatch) -> None:
    seen: list = []
    _fake_ollama(monkeypatch, json.dumps({"ranking": ["b", "zzz"]}), seen)
    provider = providers.OllamaJudgeProvider(model="qwen3.5:9b", worker_id="local_qwen35_9b")
    cands = [providers.AutoreasonCandidate.from_mapping(c, i) for i, c in enumerate(CANDIDATES)]
    out = provider.rank(task_desc="t", candidates=cands)
    assert out["ranking"] == ["b", "a"]
    assert out["winner"] == "b"
    assert out["omitted_by_model"] == ["a"]
    assert out["unknown_ids_dropped"] == ["zzz"]


def test_ollama_judge_unreachable_blocks(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.delenv("NEXUS_LLM_JUDGE_PROVIDERS", raising=False)

    def boom(request, timeout=0):
        raise providers.urllib.error.URLError("connection refused")

    monkeypatch.setattr(providers.urllib.request, "urlopen", boom)
    receipt = EXECUTOR_REGISTRY["judge_panel"](_plan(candidate_pool=CANDIDATES), "task")
    assert receipt.gate_passed is False
    assert receipt.outcome["error"].startswith("BLOCKED_PROVIDER_UNAVAILABLE:ollama_unreachable")


def test_ollama_judge_worker_comes_from_workforce_policy() -> None:
    worker = providers.resolve_ollama_judge_worker()
    assert worker["worker_id"] == "local_qwen35_9b"
    assert worker["model"] == "qwen3.5:9b"
    assert "advisor" not in worker["model"]


# --- ultra_review --------------------------------------------------------------------------


def _git_repo(root: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@e.x", "-c", "user.name=t", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )

    (root / "app.py").write_text("def handler(v):\n    return v.strip()\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text(
        "from app import handler\n\n\ndef test_strip():\n    assert handler(' a ') == 'a'\n",
        encoding="utf-8",
    )
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "base")


def _assert_no_barrier_fail_closed(receipt) -> bool:
    """Without an OS barrier (Linux CI) the PR's tests never run and the review cannot
    finish; sandbox-dependent tests assert that instead of skipping. Since #2732 that is
    recorded (review_status BLOCKED + review_error), never a blocking receipt."""
    if os_sandbox_available():
        return False
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    assert receipt.outcome["advisory_only"] is True
    assert receipt.outcome["review_status"] == "BLOCKED"
    assert receipt.outcome["review_error"] == "ghost_regression_not_executed:no_os_barrier"
    assert "error" not in receipt.outcome
    assert not any(c.startswith("tests/") for c in receipt.outcome["executed_checks"])
    return True


def test_ultra_review_executor_flags_planted_eval_and_failing_test(tmp_path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(v):\n    return v\n\n\ndef unsafe():\n    return eval(input())\n",
        encoding="utf-8",
    )
    receipt = EXECUTOR_REGISTRY["ultra_review"](_plan(workspace_root=str(tmp_path)), "review")
    if _assert_no_barrier_fail_closed(receipt):
        return
    assert receipt.invoked is True
    # #2732: the findings are recorded, but the record-only receipt never fails the gate.
    assert receipt.gate_passed is True
    assert receipt.outcome["semantic_status"] == "SUCCEEDED"
    assert receipt.outcome["advisory_only"] is True
    assert receipt.outcome["review_status"] == "FAIL"
    assert receipt.outcome["review_passed"] is False
    rules = {f["rule_id"] for f in receipt.outcome["findings"]}
    assert "bandit:B307" in rules and "regression_test_failed" in rules
    assert {"bandit", "ruff-security", "tests/test_app.py"} <= set(
        receipt.outcome["executed_checks"]
    )


def test_ultra_review_executor_passes_benign_diff(tmp_path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(v):\n    return v.strip()\n\n\ndef shout(v):\n    return handler(v).upper()\n",
        encoding="utf-8",
    )
    receipt = EXECUTOR_REGISTRY["ultra_review"](_plan(workspace_root=str(tmp_path)), "review")
    if _assert_no_barrier_fail_closed(receipt):
        return
    assert receipt.gate_passed is True, receipt.outcome
    assert receipt.outcome["semantic_status"] == "SUCCEEDED"
    assert receipt.outcome["lanes"]["security_sentry"]["executed_checks"] == [
        "diff-pattern-scan",
        "bandit",
        "ruff-security",
    ]


def test_ultra_review_executor_clean_tree_fails_closed(tmp_path) -> None:
    _git_repo(tmp_path)
    receipt = EXECUTOR_REGISTRY["ultra_review"](_plan(workspace_root=str(tmp_path)), "review")
    # #2732: nothing to review is recorded (review_status BLOCKED), never blocking.
    assert receipt.gate_passed is True
    assert receipt.outcome["review_status"] == "BLOCKED"
    assert receipt.outcome["review_error"] == "no_diff_to_review"


def test_ollama_judge_retries_once_on_unusable_output(monkeypatch) -> None:
    replies = iter(["not json at all", json.dumps({"ranking": ["a", "b"]})])

    def fake_urlopen(request, timeout=0):
        return _FakeResponse(
            json.dumps({"model": "qwen3.5:9b", "message": {"content": next(replies)}}).encode(
                "utf-8"
            )
        )

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    provider = providers.OllamaJudgeProvider(model="qwen3.5:9b", worker_id="local_qwen35_9b")
    cands = [providers.AutoreasonCandidate.from_mapping(c, i) for i, c in enumerate(CANDIDATES)]
    out = provider.rank(task_desc="t", candidates=cands)
    assert out["winner"] == "a"
    assert len(out["discarded_response_sha256"]) == 1


def test_ultra_review_executor_without_os_sandbox_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "1")
    _git_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(v):\n    return v.strip()\n\n\ndef shout(v):\n    return handler(v).upper()\n",
        encoding="utf-8",
    )
    receipt = EXECUTOR_REGISTRY["ultra_review"](_plan(workspace_root=str(tmp_path)), "review")
    # #2732: the review could not run its tests; recorded, never blocking.
    assert receipt.gate_passed is True
    assert receipt.outcome["semantic_status"] == "SUCCEEDED"
    assert receipt.outcome["review_status"] == "BLOCKED"
    assert receipt.outcome["review_error"] == "ghost_regression_not_executed:no_os_barrier"
