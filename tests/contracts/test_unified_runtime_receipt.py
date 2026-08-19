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


def test_verifier_not_observed_precedes_disabled_provider_stage() -> None:
    diagnostics = build_failure_diagnostics(
        {
            "terminal_status": "INCOMPLETE",
            "stages": [
                {"name": "local", "status": "NOT_REQUESTED", "reason": "local_route_disabled"},
                {"name": "online", "status": "NOT_REQUESTED", "reason": "online_route_disabled"},
                {"name": "verifier", "status": "NOT_RUN", "reason": "verifier_callback_not_supplied"},
            ],
        }
    )

    assert diagnostics["failure_class"] == "verifier_evidence_untrusted"
    assert diagnostics["source_stage"] == "verifier"
    assert diagnostics["reason_code"] == "verifier_not_observed"
    assert diagnostics["provider"] == ""


def test_untrusted_verifier_evidence_precedes_disabled_provider_stage() -> None:
    diagnostics = build_failure_diagnostics(
        {
            "terminal_status": "INCOMPLETE",
            "stages": [
                {"name": "online", "status": "NOT_REQUESTED", "reason": "online_route_disabled"},
                {
                    "name": "verifier",
                    "status": "FAILED",
                    "invoked": True,
                    "evidence_present": False,
                    "gate_passed": False,
                    "reason": "verifier_evidence_untrusted",
                },
            ],
        }
    )

    assert diagnostics["failure_class"] == "verifier_evidence_untrusted"
    assert diagnostics["source_stage"] == "verifier"
    assert diagnostics["reason_code"] == "verifier_evidence_untrusted"


def test_trusted_verifier_failure_remains_distinct_from_untrusted_evidence() -> None:
    diagnostics = build_failure_diagnostics(
        {
            "terminal_status": "INCOMPLETE",
            "stages": [
                {"name": "local", "status": "NOT_REQUESTED", "reason": "local_route_disabled"},
                {
                    "name": "verifier",
                    "status": "FAILED",
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": False,
                    "reason": "assertion_failed",
                },
            ],
        }
    )

    assert diagnostics["failure_class"] == "verifier_failed"
    assert diagnostics["source_stage"] == "verifier"
    assert diagnostics["reason_code"] == "assertion_failed"


def test_provider_unavailable_is_preserved_when_verifier_passed() -> None:
    diagnostics = build_failure_diagnostics(
        {
            "terminal_status": "INCOMPLETE",
            "stages": [
                {"name": "online", "status": "NOT_RUN", "reason": "online_invoker_not_supplied"},
                {
                    "name": "verifier",
                    "status": "SUCCEEDED",
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": True,
                },
            ],
        }
    )

    assert diagnostics["failure_class"] == "provider_unavailable"
    assert diagnostics["source_stage"] == "online"
