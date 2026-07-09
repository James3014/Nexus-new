from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierReceipt,
    IsolatedVerifierRequest,
    compute_semantic_correctness,
    run_isolated_verifier,
)


def test_isolated_verifier_not_allowed() -> None:
    request = IsolatedVerifierRequest(
        task_id="t1",
        workspace_path=".",
        verifier_command=("python3", "-c", "print(1)"),
        verifier_allowed=False,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "blocked"
    assert receipt.verifier_error == "verifier_not_allowed"


def test_isolated_verifier_pass() -> None:
    request = IsolatedVerifierRequest(
        task_id="t2",
        workspace_path=".",
        verifier_command=("python3", "-c", "import sys; sys.exit(0)"),
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "pass"
    assert receipt.exit_code == 0
    assert receipt.verifier_error == ""


def test_isolated_verifier_fail() -> None:
    request = IsolatedVerifierRequest(
        task_id="t3",
        workspace_path=".",
        verifier_command=("python3", "-c", "import sys; sys.exit(1)"),
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "fail"
    assert receipt.exit_code == 1


def test_isolated_verifier_timeout() -> None:
    request = IsolatedVerifierRequest(
        task_id="t4",
        workspace_path=".",
        verifier_command=("python3", "-c", "import time; time.sleep(2)"),
        timeout_sec=0.1,
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "blocked"
    assert "verifier_timeout" in receipt.verifier_error
    assert receipt.exit_code is None


def test_isolated_verifier_calls_semantic_correctness_after_tests() -> None:
    request = IsolatedVerifierRequest(
        task_id="t5",
        workspace_path=".",
        verifier_command=("python3", "-c", "import sys; sys.exit(0)"),
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    result = compute_semantic_correctness(receipt)
    assert isinstance(result, bool)


def test_semantic_correctness_true_when_tests_pass_no_buggy_symbol() -> None:
    receipt = IsolatedVerifierReceipt(
        task_id="t6",
        verifier_status="pass",
        exit_code=0,
        stdout_tail="all tests passed",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": True}],
    )
    assert compute_semantic_correctness(receipt) is True


def test_semantic_correctness_false_when_buggy_symbol_in_artifact() -> None:
    receipt = IsolatedVerifierReceipt(
        task_id="t7",
        verifier_status="pass",
        exit_code=0,
        stdout_tail="test output: view(NdarrayMixin) still present",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": True}],
    )
    assert compute_semantic_correctness(receipt) is False


def test_semantic_correctness_false_when_tests_fail() -> None:
    receipt = IsolatedVerifierReceipt(
        task_id="t8",
        verifier_status="fail",
        exit_code=1,
        stdout_tail="test failed",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": False}],
    )
    assert compute_semantic_correctness(receipt) is False


def test_completion_envelope_receives_semantic_correctness_passed() -> None:
    from nexus.engine.completion_contract import build_completion_envelope

    receipt = IsolatedVerifierReceipt(
        task_id="t9",
        verifier_status="pass",
        exit_code=0,
        stdout_tail="all tests passed",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": True}],
    )
    result = compute_semantic_correctness(receipt)
    payload = build_completion_envelope(
        command_name="run",
        task_name="test task",
        runtime_ok=True,
        execution_path="cli->engine",
        semantic_correctness_passed=result,
    )
    assert payload["semantic_correctness_passed"] is True
