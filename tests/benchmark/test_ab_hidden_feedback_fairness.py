"""R1: the with-Nexus arm must not get hidden-verifier feedback the bare arm never gets.

Online A/B report 2026-10-14: after a hidden-verifier miss the bench (a) patched the file
with the local fixture mutator using the hidden assertion text and (b) re-asked the model
with the hidden test quoted.  Both rows were counted as model solves.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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

    assert out["hidden_retry_reason"] == "hidden_verifier_failure_deterministic_pre_retry"
    assert out["status"] == "SUCCESS"
    # The local fixture mutator produced the delivered file, not the model.
    assert out["nexus_winner_source"] == "local_hidden_pre_retry"
    out["mode"] = "with_nexus"
    apply_strict_llm_baseline_classification([out])
    assert out["solve_classification"] == HIDDEN_FEEDBACK_RESCUE


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


def test_strict_cli_defaults_to_no_hidden_feedback(tmp_path: Path) -> None:
    """``--strict-llm-baseline`` alone turns hidden feedback off; ``--allow-hidden-feedback`` restores it."""

    import os

    repo_root = Path(__file__).resolve().parents[2]
    probe = (
        "import os, sys\n"
        "import scripts.bench.capability_ab_runner as r\n"
        "def stop(*a, **k):\n"
        "    print('NHF=' + os.environ.get('NEXUS_BENCH_NO_HIDDEN_FEEDBACK', ''))\n"
        "    raise SystemExit(0)\n"
        "r.build_public_benchmark_preflight = stop\n"
        "sys.argv = ['capability_ab_runner.py', '--tasks-file', 'scripts/bench/public_benchmark_nexus_value_v1.json',\n"
        "            '--output-dir', sys.argv[1], '--preflight-only'] + sys.argv[2:]\n"
        "r.main()\n"
    )
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    env.pop("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", None)

    def run(*flags: str) -> str:
        proc = subprocess.run(
            [sys.executable, "-c", probe, str(tmp_path / "out"), *flags],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        lines = [line for line in proc.stdout.splitlines() if line.startswith("NHF=")]
        assert lines, proc.stderr[-2000:]
        return lines[-1]

    assert run("--strict-llm-baseline") == "NHF=1"
    assert run("--strict-llm-baseline", "--allow-hidden-feedback") == "NHF=0"
    assert run() == "NHF=0"
    assert run("--no-hidden-feedback") == "NHF=1"
