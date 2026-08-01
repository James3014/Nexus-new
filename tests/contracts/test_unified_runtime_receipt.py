from __future__ import annotations

from nexus.contracts.unified_runtime_receipt import (
    FAILURE_DIAGNOSTICS_SCHEMA,
    attach_failure_diagnostics,
    build_failure_diagnostics,
    validate_failure_diagnostics,
)


def test_success_projection_has_no_amplification_root() -> None:
    receipt = attach_failure_diagnostics({"terminal_status": "SUCCEEDED", "capability_closure_blockers": []})
    assert receipt["failure_class"] == "none"
    assert receipt["amplification_root_id"] == ""
    assert receipt["failure_diagnostics"]["schema"] == FAILURE_DIAGNOSTICS_SCHEMA
    assert validate_failure_diagnostics(receipt) == []


def test_equivalent_provider_failures_share_root_across_tasks() -> None:
    first = build_failure_diagnostics({
        "task_id": "task-a",
        "terminal_status": "INCOMPLETE",
        "stages": [{"name": "online", "status": "FAILED", "reason": "provider timeout", "provider": "agy"}],
    })
    second = build_failure_diagnostics({
        "task_id": "task-b",
        "execution_attempt": {"attempt_number": 2},
        "terminal_status": "INCOMPLETE",
        "stages": [{"name": "online", "status": "FAILED", "reason": "provider timeout", "provider": "agy"}],
    })
    assert first["failure_class"] == second["failure_class"] == "provider_failed"
    assert first["amplification_root_id"] == second["amplification_root_id"]


def test_diagnostics_validator_fails_closed_on_projection_mismatch() -> None:
    receipt = attach_failure_diagnostics({
        "terminal_status": "INCOMPLETE",
        "stages": [{"name": "online", "status": "NOT_RUN", "reason": "provider unavailable"}],
    })
    receipt["amplification_root_id"] = "sha256:" + "0" * 64
    assert "amplification_root_projection_mismatch" in validate_failure_diagnostics(receipt)
