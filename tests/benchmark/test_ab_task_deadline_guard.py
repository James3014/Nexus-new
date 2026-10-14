"""R4: a per-task deadline overrun fails the row instead of crashing the whole runner,
and both arms' single-model-call budgets derive from the same setting."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _materialize_fixture,
    run_with_nexus,
    run_without_nexus,
)

NEXUS_CLI_PREFIX = ["uv", "run", "scripts/engine/nexus_cli.py"]


def _governance_task() -> CapabilityTask:
    return CapabilityTask(
        id="rlm-v2-deadline-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden governance task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_governance_guard",
    )


def _success_payload() -> str:
    return json.dumps({
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "pillars": {},
            "phase_trace": {},
            "capabilities": {},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
                "total_tokens": 10,
                "token_capture_status": "ok",
            },
        },
    })


def test_hidden_verifier_after_task_deadline_fails_row_instead_of_raising(
    tmp_path: Path, monkeypatch
) -> None:
    task = _governance_task()
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    verifier_calls: list[list[str]] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            # First pass (plus any rescue) uses up the whole per-task budget.
            time.sleep(1.2)
            return subprocess.CompletedProcess(cmd, 0, stdout=_success_payload(), stderr="")
        verifier_calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="hidden passed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=1,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert verifier_calls == []
    assert out["status"] == "FAILED"
    assert out["hidden_verifier_passed"] is False
    assert out["task_deadline_exceeded"] is True
    assert out["task_deadline_stage"] == "hidden_verifier"
    assert out["task_deadline_failure"] == "task_deadline_exceeded"
    assert out["hidden_retry_reason"] == "task_deadline_exceeded"
    assert out["hidden_retry_used"] is False


def test_bare_agy_call_timeout_uses_the_with_nexus_per_call_setting(
    tmp_path: Path, monkeypatch
) -> None:
    task = _governance_task()
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    seen: list[int] = []

    def fake_agy(*, prompt: str, timeout_sec: int):
        seen.append(int(timeout_sec))
        return {"status": "FAILED", "patch": "", "error_category": "timeout"}, ""

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_agy_patch", fake_agy)
    monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "300")
    run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=900,
        force_flow=None,
        mode="agy",
    )
    assert seen and seen[0] == 300

    seen.clear()
    monkeypatch.delenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC")
    run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=900,
        force_flow=None,
        mode="agy",
    )
    assert seen and 890 <= seen[0] <= 900


def test_strict_both_arms_get_identical_per_call_cap_when_env_unset(
    tmp_path: Path, monkeypatch
) -> None:
    import argparse

    from scripts.bench.capability_ab_runner import _resolve_symmetric_per_call_cap_sec

    monkeypatch.delenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", raising=False)
    args = argparse.Namespace(
        strict_llm_baseline=True,
        require_same_model_baseline=False,
        per_call_timeout_sec=0,
        timeout_sec=900,
    )
    cap = _resolve_symmetric_per_call_cap_sec(args)
    assert cap == 870
    # Outside the like-for-like config nothing is forced.
    assert _resolve_symmetric_per_call_cap_sec(argparse.Namespace(timeout_sec=900)) is None
    monkeypatch.setenv("NEXUS_BENCH_PER_CALL_CAP_SEC", str(cap))

    task = _governance_task()
    bare_seen: list[int] = []

    def fake_agy(*, prompt: str, timeout_sec: int):
        bare_seen.append(int(timeout_sec))
        return {"status": "FAILED", "patch": "", "error_category": "timeout"}, ""

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_agy_patch", fake_agy)
    bare_root = tmp_path / "bare"
    bare_root.mkdir()
    target_file, visible_test_file = _materialize_fixture(bare_root, task)
    run_without_nexus(
        repo_root=bare_root,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=900,
        force_flow=None,
        mode="agy",
    )

    nexus_seen: list[str] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            nexus_seen.append(str(env.get("NEXUS_GATEWAY_TIMEOUT_SEC")))
            return subprocess.CompletedProcess(cmd, 0, stdout=_success_payload(), stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="passed", stderr="")

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    nexus_root = tmp_path / "nexus"
    nexus_root.mkdir()
    target_file, visible_test_file = _materialize_fixture(nexus_root, task)
    run_with_nexus(
        repo_root=nexus_root,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=900,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert bare_seen == [cap]
    assert nexus_seen and set(nexus_seen) == {str(cap)}


def test_strict_later_with_nexus_subprocesses_share_one_task_deadline(
    tmp_path: Path, monkeypatch
) -> None:
    """S17/S11: a rescue/fallback subprocess gets the remaining shared budget, not a fresh one."""

    task = _governance_task()
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    nexus_timeouts: list[int] = []

    def failed_payload() -> str:
        payload = json.loads(_success_payload())
        payload["status"] = "FAILED"
        payload["semantic_status"] = "UNVERIFIED"
        return json.dumps(payload)

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            nexus_timeouts.append(int(timeout_sec))
            if len(nexus_timeouts) == 1:
                time.sleep(3.2)
            return subprocess.CompletedProcess(cmd, 0, stdout=failed_payload(), stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="failed", stderr="")

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert len(nexus_timeouts) >= 2, nexus_timeouts
    assert nexus_timeouts[0] <= 10
    assert all(later <= 7 for later in nexus_timeouts[1:]), nexus_timeouts
