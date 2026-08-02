#!/usr/bin/env python3
"""Run the local, fail-closed acceptance matrix for runtime phase convergence.

This runner deliberately exercises existing contracts in memory.  It does not
start providers, mutate lifecycle state, write receipts, or make a production
claim.  External provider/service acceptance remains an explicitly deferred
follow-up with the evidence boundary preserved in the output.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from nexus.contracts.learning_experience import (
    RUNTIME_LEARNING_PHASE_CHAIN,
    build_runtime_learning_closure,
)
from nexus.contracts.unified_runtime_receipt import (
    build_runtime_development_mapping,
)
from nexus.engine.phase_handshake import build_phase_receipt, validate_phase_receipt
from nexus.engine.runtime_phase_contract import (
    RuntimePhase,
    RuntimeStatus,
    RuntimeTransitionError,
    research_continuation,
    validate_transition,
)


TASK_ID = "acceptance:runtime-phase-convergence"
ATTEMPT_ID = "attempt:local-contract-matrix"
ACTION_ID = "action:card-5"
AUTHORITY_REVISION = "runtime-phase-contract-v1"


def _receipt(*, phase: str, status: str, transition: str, evidence: str) -> dict[str, Any]:
    receipt = build_phase_receipt(
        task_id=TASK_ID,
        attempt_id=ATTEMPT_ID,
        action_id=ACTION_ID,
        phase=phase,
        phase_attempt=1,
        input_payload={"scenario": evidence},
        output_payload={"status": status},
        authority_revision=AUTHORITY_REVISION,
        status=status,
        transition=transition,
        evidence_refs=(f"local:{evidence}",),
        verifier_refs=("local:phase-contract-acceptance",),
        timeout_telemetry={"timed_out": status == "TIMEOUT"},
        block_class="RECOVERABLE_BLOCK" if status == "TIMEOUT" else "",
        next_action="owner_review" if status in {"REJECTED", "DEFINITION_DRIFT"} else "",
    )
    validate_phase_receipt(receipt)
    return receipt


def _expect_error(call: Callable[[], Any], marker: str) -> None:
    try:
        call()
    except (RuntimeTransitionError, ValueError) as exc:
        if marker not in str(exc):
            raise AssertionError(f"expected {marker!r}, got {exc!s}") from exc
        return
    raise AssertionError(f"expected failure: {marker}")


def _check_contract_flow() -> None:
    expected = ("S", "P", "D", "X", "R", "A", "C")
    actual = tuple(phase.value for phase in RuntimePhase)
    assert actual == expected, (actual, expected)
    assert tuple(RUNTIME_LEARNING_PHASE_CHAIN) == expected
    validate_transition("S", "P")
    validate_transition("P", "D")
    validate_transition("D", "R")
    validate_transition("R", "A")
    validate_transition("A", "C", audit_passed=True)


def _check_branch_matrix() -> None:
    assert research_continuation(external_research_required=True) == (
        RuntimePhase.X,
        RuntimePhase.D,
    )
    assert research_continuation(external_research_required=False) == (
        RuntimePhase.D,
        RuntimePhase.R,
    )
    validate_transition("A", "R")
    validate_transition("A", "D")
    validate_transition("D", "X")
    validate_transition("X", "D")
    validate_transition("D", RuntimeStatus.RECOVERABLE_BLOCK)
    validate_transition("D", RuntimeStatus.HARD_BLOCK)
    _expect_error(lambda: validate_transition("A", "C"), "audit_pass_required_for_crystallize")
    _expect_error(lambda: validate_transition("C", "D"), "illegal_runtime_transition")


def _check_receipt_bound_scenarios() -> None:
    scenarios = (
        ("P", "DIRECT", "S->P", "read_only"),
        ("D", "ASSISTED", "P->D", "assisted"),
        ("R", "CANDIDATE", "A->R", "isolated_candidate"),
        ("X", "TIMEOUT", "D->X", "timeout"),
        ("D", "DEFINITION_DRIFT", "X->D", "definition_drift"),
        ("A", "REJECTED", "R->A", "approval_rejection"),
        ("A", "CANDIDATE_DISPOSITION", "R->A", "candidate_disposition"),
    )
    for phase, status, transition, evidence in scenarios:
        receipt = _receipt(phase=phase, status=status, transition=transition, evidence=evidence)
        assert receipt["evidence_refs"] == [f"local:{evidence}"]
        assert receipt["verifier_refs"] == ["local:phase-contract-acceptance"]


def _check_identity_mapping() -> None:
    mapping = build_runtime_development_mapping(
        task_id=TASK_ID,
        attempt_id=ATTEMPT_ID,
        action_id=ACTION_ID,
        runtime_terminal_state="CANDIDATE",
        development_status="CANDIDATE",
        runtime_success=True,
        candidate_status="CREATED",
        candidate_accepted=False,
        runtime_receipt_ref="local:runtime-receipt",
        development_receipt_ref="local:development-receipt",
    )
    assert mapping["identity"]["task_id"] == TASK_ID
    assert mapping["claim_boundaries"]["public_claim_allowed"] is False
    assert mapping["claim_boundaries"]["production_ready"] is False
    assert mapping["development"]["integrated"] is False


def _check_learning_closure() -> None:
    receipt = _receipt(phase="C", status="SUCCESS", transition="A->C", evidence="terminal")
    closure = build_runtime_learning_closure(
        task_id=TASK_ID,
        attempt_id=ATTEMPT_ID,
        action_id=ACTION_ID,
        phase_receipts=[receipt],
        candidate_ref="candidate:local",
        outcome="SUCCESS",
        terminal_evidence={"receipt_ref": "local:terminal", "verifier": "pass"},
        uncertain_mutation=False,
        lesson_disposition="shadow",
        primary_task_success=True,
        learning_write_succeeded=True,
    )
    assert closure["auto_replay_allowed"] is False
    assert closure["primary_task_success"] is True
    assert closure["phase_chain"] == list(RUNTIME_LEARNING_PHASE_CHAIN)
    _expect_error(
        lambda: build_runtime_learning_closure(
            task_id=TASK_ID,
            attempt_id=ATTEMPT_ID,
            action_id=ACTION_ID,
            phase_receipts=[receipt],
            outcome="FAILED",
            terminal_evidence={"receipt_ref": "local:failed"},
            lesson_disposition="graduated",
        ),
        "RUNTIME_LEARNING_FAILED_ATTEMPT_CANNOT_GRADUATE",
    )


def main() -> int:
    checks: list[dict[str, str]] = []
    local_checks: tuple[tuple[str, Callable[[], Any]], ...] = (
        ("phase_flow_and_terminal_contract", _check_contract_flow),
        ("branch_and_block_transition_matrix", _check_branch_matrix),
        ("receipt_bound_acceptance_scenarios", _check_receipt_bound_scenarios),
        ("runtime_development_identity_mapping", _check_identity_mapping),
        ("learning_closure_and_graduation_gate", _check_learning_closure),
    )
    for name, check in local_checks:
        try:
            check()
        except Exception as exc:  # pragma: no cover - CLI failure path
            checks.append({"name": name, "status": "FAIL", "detail": str(exc)})
            break
        checks.append({"name": name, "status": "PASS", "detail": "receipt_bound_local_evidence"})

    failed = [item for item in checks if item["status"] != "PASS"]
    result = {
        "schema": "nexus.runtime_lifecycle_acceptance.v1",
        "status": "PASS_LOCAL_CANDIDATE" if not failed else "FAIL",
        "task_id": TASK_ID,
        "attempt_id": ATTEMPT_ID,
        "checks": checks,
        "deferred_external": [
            "live_provider_and_transport_acceptance",
            "owner_P7_disposition_and_final_approval",
        ],
        "claim_ceiling": "LOCAL_RUNTIME_PHASE_ACCEPTANCE_CANDIDATE",
        "public_claim_allowed": False,
        "production_ready": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
