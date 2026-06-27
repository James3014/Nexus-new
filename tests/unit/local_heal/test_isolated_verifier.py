from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
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
