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


def test_per_call_cap_is_clamped_to_the_task_budget_and_validated(monkeypatch) -> None:
    """Reviewer C(1): the cap never exceeds the task budget; bad or too-small settings fail loudly."""

    import argparse

    import pytest

    from scripts.bench.capability_ab_runner import _resolve_symmetric_per_call_cap_sec

    monkeypatch.delenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", raising=False)
    explicit = argparse.Namespace(
        strict_llm_baseline=True, per_call_timeout_sec=600, timeout_sec=420
    )
    assert _resolve_symmetric_per_call_cap_sec(explicit) == 390
    monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "900")
    assert (
        _resolve_symmetric_per_call_cap_sec(
            argparse.Namespace(strict_llm_baseline=True, timeout_sec=420)
        )
        == 390
    )
    monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "3OO")
    with pytest.raises(ValueError, match="must be an integer"):
        _resolve_symmetric_per_call_cap_sec(
            argparse.Namespace(strict_llm_baseline=True, timeout_sec=420)
        )
    monkeypatch.delenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC")
    with pytest.raises(ValueError, match="too small"):
        _resolve_symmetric_per_call_cap_sec(
            argparse.Namespace(strict_llm_baseline=True, timeout_sec=30)
        )


def test_main_rejects_an_invalid_per_call_cap(tmp_path, monkeypatch, capsys) -> None:
    import sys

    import pytest

    import scripts.bench.capability_ab_runner as runner

    saved = dict(__import__("os").environ)
    try:
        monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "abc")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "capability_ab_runner.py",
                "--tasks-file",
                "scripts/bench/public_benchmark_nexus_value_v1.json",
                "--output-dir",
                str(tmp_path / "o"),
                "--preflight-only",
                "--strict-llm-baseline",
                "--with-llm-mode",
                "all",
                "--without-mode",
                "agy",
                "--timeout-sec",
                "420",
            ],
        )
        monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
        with pytest.raises(SystemExit) as exc:
            runner.main()
        assert exc.value.code == 2
        assert "must be an integer" in capsys.readouterr().err
        # A task budget of 35 s leaves a 5 s per-call cap: refused too.
        monkeypatch.delenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC")
        monkeypatch.setattr(sys, "argv", [*sys.argv, "--timeout-sec", "35"])
        with pytest.raises(SystemExit) as exc:
            runner.main()
        assert exc.value.code == 2
        assert "too small" in capsys.readouterr().err
    finally:
        import os

        os.environ.clear()
        os.environ.update(saved)


def test_subprocess_killed_at_the_shared_deadline_marks_the_row(tmp_path, monkeypatch) -> None:
    """Reviewer C(2): a kill AT the shared cap is a task-deadline overrun too."""

    task = _governance_task()
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    granted: list[int] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            granted.append(int(timeout_sec))
            time.sleep(min(float(timeout_sec), 2.2))
            raise subprocess.TimeoutExpired(cmd, timeout_sec)
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
        timeout_sec=2,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )
    assert granted and granted[0] <= 2
    assert out["task_deadline_exceeded"] is True
    assert out["status"] == "FAILED"


def test_receipt_first_probe_cannot_outlive_the_remaining_budget(tmp_path, monkeypatch) -> None:
    """Reviewer C(3)."""

    import dataclasses

    from scripts.bench.capability_ab_runner import _run_receipt_first_probe_payload

    task = dataclasses.replace(_governance_task(), expected_capabilities=["claim_gate"])
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    seen: list[int] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        seen.append(int(timeout_sec))
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    _run_receipt_first_probe_payload(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=300,
        force_flow=None,
        candidate_cap=1,
        enable_autoreason_executor=False,
        enable_ddtree_executor=False,
        enable_ultra_review_dry_gate=False,
        required=True,
        hard_cap_sec=3,
    )
    assert seen == [3]
