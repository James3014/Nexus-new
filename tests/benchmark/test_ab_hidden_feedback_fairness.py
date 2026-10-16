"""R1: the with-Nexus arm must not get hidden-verifier feedback the bare arm never gets.

Online A/B report 2026-10-14: after a hidden-verifier miss the bench (a) patched the file
with the local fixture mutator using the hidden assertion text and (b) re-asked the model
with the hidden test quoted.  Both rows were counted as model solves.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _materialize_fixture,
    _run_process_group,
    run_with_nexus,
)
from scripts.bench.strict_llm_baseline import (
    HIDDEN_FEEDBACK_RESCUE,
    MODEL_SOLVE,
    NOT_SOLVED,
    apply_strict_llm_baseline_classification,
    honest_scorecard,
)

NEXUS_CLI_PREFIX = ["uv", "run", "scripts/engine/nexus_cli.py"]


@pytest.fixture(autouse=True)
def _restore_environ():
    """``main()`` writes several bench switches straight into os.environ; never leak them."""

    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _payload(model_calls: int = 1) -> str:
    return json.dumps({
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capabilities": {"delivery_gate": True},
            "pillars": {"artifact": {"active": True}},
            "phase_trace": {"P": "route_built", "R": "patched", "A": "verified"},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": model_calls,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
                "total_tokens": 10,
                "token_capture_status": "measured",
            },
        },
    })


def _repair_task() -> CapabilityTask:
    return CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
        eligibility_class="model_required",
    )


def _run_pre_retry_case(tmp_path: Path, monkeypatch) -> tuple[dict, list[list[str]]]:
    task = _repair_task()
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    nexus_cmds: list[list[str]] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            nexus_cmds.append(list(cmd))
            # The "model" delivers a file that passes visible tests but misses the hidden contract.
            Path(target_file).write_text(
                "def compute_backoff(attempt: int) -> int:\n    if attempt <= 1:\n        return 1\n    return attempt\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=_payload(), stderr="")
        return _run_process_group(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    out = run_with_nexus(
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
    return out, nexus_cmds


def test_no_hidden_feedback_disables_deterministic_hidden_pre_retry(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", "1")
    out, nexus_cmds = _run_pre_retry_case(tmp_path, monkeypatch)

    assert len(nexus_cmds) == 1
    assert not out.get("hidden_pre_retry_used")
    assert out["hidden_retry_used"] is False
    assert out["hidden_retry_reason"] == "disabled_no_hidden_feedback"
    assert out["hidden_verifier_passed"] is False
    assert out["status"] == "FAILED"


def test_deterministic_hidden_pre_retry_marks_local_winner_and_is_never_a_model_solve(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", "0")
    out, _ = _run_pre_retry_case(tmp_path, monkeypatch)

    # #2339 follow-up: the local fixture mutator (deterministic pre-retry) is deleted, so no local
    # file is ever delivered on a hidden-verifier failure.
    assert out["hidden_retry_reason"] != "hidden_verifier_failure_deterministic_pre_retry"
    assert not out.get("hidden_pre_retry_used")
    assert out.get("nexus_winner_source") != "local_hidden_pre_retry"
    assert out["status"] == "FAILED"


def test_no_hidden_feedback_disables_bounded_model_retry_quoting_hidden_test(
    tmp_path: Path, monkeypatch
) -> None:
    task = CapabilityTask(
        id="rlm-v2-hidden-retry-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden governance task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_governance_guard",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    nexus_cmds: list[list[str]] = []
    state = {"verify_calls": 0}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            nexus_cmds.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout=_payload(), stderr="")
        state["verify_calls"] += 1
        if state["verify_calls"] == 1:
            return subprocess.CompletedProcess(
                cmd, 1, stdout="hidden failed: delete_file must be blocked", stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="hidden passed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setenv("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", "1")
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert len(nexus_cmds) == 1
    assert not any("delete_file must be blocked" in " ".join(cmd) for cmd in nexus_cmds)
    assert out["hidden_retry_used"] is False
    assert out["hidden_retry_reason"] == "disabled_no_hidden_feedback"
    assert out["status"] == "FAILED"


def test_hidden_feedback_success_rows_are_rescues_not_model_solves() -> None:
    rows = [
        {
            "mode": "with_nexus",
            "status": "SUCCESS",
            "model_calls": 2,
            "nexus_winner_source": "nexus_llm_baseline",
            "hidden_retry_used": True,
            "hidden_retry_reason": "hidden_verifier_failure_bounded_nexus_retry",
        },
        {
            "mode": "with_nexus",
            "status": "SUCCESS",
            "model_calls": 1,
            "nexus_winner_source": "nexus_llm_baseline",
            "hidden_retry_reason": "hidden_verifier_failure_deterministic_pre_retry",
        },
        {
            "mode": "with_nexus",
            "status": "SUCCESS",
            "model_calls": 1,
            "nexus_winner_source": "nexus_llm_baseline",
        },
        {
            "mode": "without_nexus",
            "status": "SUCCESS",
            "model_calls": 2,
            "hidden_retry_used": True,
            "hidden_retry_reason": "hidden_verifier_failure_bounded_nexus_retry",
        },
    ]
    apply_strict_llm_baseline_classification(rows)

    assert [r["solve_classification"] for r in rows] == [
        HIDDEN_FEEDBACK_RESCUE,
        HIDDEN_FEEDBACK_RESCUE,
        MODEL_SOLVE,
        NOT_SOLVED,
    ]
    card = honest_scorecard(rows, "with_nexus")
    assert card["solved_by_model"] == 1
    assert card["rescued_by_local"] == 2
    assert card["failed"] == 0


def test_strict_cli_defaults_to_no_hidden_feedback(tmp_path: Path, monkeypatch) -> None:
    """``--strict-llm-baseline`` alone turns hidden feedback off; ``--allow-hidden-feedback`` restores it."""

    import scripts.bench.capability_ab_runner as runner

    class _Stop(Exception):
        pass

    def stop(*_args, **_kwargs):
        raise _Stop(os.environ.get("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", ""))

    monkeypatch.setattr(runner, "build_public_benchmark_preflight", stop)

    def run(*flags: str) -> str:
        monkeypatch.delenv("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", raising=False)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "capability_ab_runner.py",
                "--tasks-file",
                "scripts/bench/public_benchmark_nexus_value_v1.json",
                "--output-dir",
                str(tmp_path / "out"),
                "--preflight-only",
                *flags,
            ],
        )
        with pytest.raises(_Stop) as exc:
            runner.main()
        return str(exc.value)

    assert run("--strict-llm-baseline") == "1"
    assert run("--strict-llm-baseline", "--allow-hidden-feedback") == "0"
    assert run() == "0"
    assert run("--no-hidden-feedback") == "1"


def _failed_first_attempt_payload() -> str:
    return json.dumps({
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "nexus_failure_analysis": {
            "schema": "nexus_failure_analysis_v1",
            "status": "ACTION_REQUIRED",
            "primary_cause": "flash_patch_failed_tests",
            "nexus_gap": "bounded_self_heal_not_triggered",
            "recoverable": True,
        },
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capabilities": {"delivery_gate": True},
            "pillars": {"artifact": {"active": True}},
            "phase_trace": {"P": "route_built", "R": "failed"},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
                "total_tokens": 10,
                "token_capture_status": "measured",
            },
        },
    })


def _run_failed_first_attempt(tmp_path: Path, monkeypatch) -> tuple[dict, list[list[str]]]:
    task = _repair_task()
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    nexus_cmds: list[list[str]] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            nexus_cmds.append(list(cmd))
            return subprocess.CompletedProcess(
                cmd, 0, stdout=_failed_first_attempt_payload(), stderr=""
            )
        return subprocess.CompletedProcess(cmd, 1, stdout="failed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE", "1")
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    out = run_with_nexus(
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
    return out, nexus_cmds


def test_counted_first_attempt_disables_bounded_hyper_rescue(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_BENCH_COUNTED_FIRST_ATTEMPT", "1")
    out, nexus_cmds = _run_failed_first_attempt(tmp_path, monkeypatch)

    assert len(nexus_cmds) == 1
    assert out["hyper_admission_decision"] == "run_hyper"
    assert out["bounded_nexus_rescue_used"] is False
    assert out["bounded_nexus_rescue_reason"] == "disabled_counted_first_attempt"
    assert out["status"] == "FAILED"


def test_bounded_hyper_rescue_still_runs_as_nexus_treatment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_BENCH_COUNTED_FIRST_ATTEMPT", "0")
    _, nexus_cmds = _run_failed_first_attempt(tmp_path, monkeypatch)
    assert len(nexus_cmds) == 2


def test_stop_loss_and_escalate_rows_stay_in_the_denominator_as_failures() -> None:
    from scripts.bench.strict_llm_baseline import apply_strict_llm_baseline_to_summary

    rows = [
        {"mode": "with_nexus", "task_id": "a", "status": "SUCCESS", "model_calls": 1},
        {
            "mode": "with_nexus",
            "task_id": "b",
            "status": "SUCCESS",
            "model_calls": 1,
            "infra_invalid_reason": "task_stop_loss_exceeded",
            "run_eligible": False,
        },
        {
            "mode": "with_nexus",
            "task_id": "c",
            "status": "FAILED",
            "model_calls": 0,
            "infra_invalid_reason": "nexus_delivery_invalid",
            "run_eligible": False,
        },
        {"mode": "without_nexus", "task_id": "a", "status": "SUCCESS", "model_calls": 1},
    ]
    apply_strict_llm_baseline_classification(rows)
    assert rows[1]["solve_classification"] == NOT_SOLVED
    summary = apply_strict_llm_baseline_to_summary(rows, {"with_nexus": {}, "without_nexus": {}})
    assert summary["with_nexus"]["solved_n"] == 1
    assert summary["with_nexus"]["solve_rate"] == round(1 / 3, 4)
    assert summary["with_nexus"]["run_eligible_n"] == 1


def test_strict_cli_turns_on_counted_first_attempt_and_its_guards(
    tmp_path: Path, monkeypatch
) -> None:
    import scripts.bench.capability_ab_runner as runner

    class _Stop(Exception):
        pass

    seen: dict[str, str] = {}

    def stop(*_args, **_kwargs):
        for name in (
            "NEXUS_BENCH_COUNTED_FIRST_ATTEMPT",
            "NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE",
            "NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY",
            "NEXUS_BENCH_DISABLE_HIDDEN_RETRY",
        ):
            seen[name] = os.environ.get(name, "")
        raise _Stop

    for name in (
        "NEXUS_BENCH_COUNTED_FIRST_ATTEMPT",
        "NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE",
        "NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY",
        "NEXUS_BENCH_DISABLE_HIDDEN_RETRY",
        "NEXUS_BENCH_NO_HIDDEN_FEEDBACK",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(runner, "build_public_benchmark_preflight", stop)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_ab_runner.py",
            "--tasks-file",
            "scripts/bench/public_benchmark_nexus_value_v1.json",
            "--output-dir",
            str(tmp_path / "out"),
            "--preflight-only",
            "--strict-llm-baseline",
        ],
    )
    with pytest.raises(_Stop):
        runner.main()
    assert seen == {
        "NEXUS_BENCH_COUNTED_FIRST_ATTEMPT": "1",
        "NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE": "1",
        "NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY": "1",
        "NEXUS_BENCH_DISABLE_HIDDEN_RETRY": "1",
    }


@pytest.mark.parametrize("lane_env", ["NEXUS_SYMMETRIC_PROMPT", "NEXUS_CONFINE_VISIBLE_TEST"])
def test_counted_lanes_never_quote_the_hidden_failure_even_with_feedback_enabled(
    tmp_path: Path, monkeypatch, lane_env: str
) -> None:
    """Gemini G9 (pre-existing since #2138): under the symmetric-prompt / counted lanes the
    hidden verifier's failure tail never reaches a retry prompt, even if the flag says on."""
    task = CapabilityTask(
        id="rlm-v2-hidden-retry-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden governance task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_governance_guard",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    nexus_cmds: list[list[str]] = []
    state = {"verify_calls": 0}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == NEXUS_CLI_PREFIX:
            nexus_cmds.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout=_payload(), stderr="")
        state["verify_calls"] += 1
        if state["verify_calls"] == 1:
            return subprocess.CompletedProcess(
                cmd, 1, stdout="hidden failed: delete_file must be blocked", stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="hidden passed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setenv("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", "0")  # flag says feedback ON
    monkeypatch.setenv(lane_env, "1")
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert not any("delete_file must be blocked" in " ".join(cmd) for cmd in nexus_cmds)
    assert out["hidden_retry_used"] is False
    assert out["hidden_retry_reason"] == "disabled_no_hidden_feedback"
