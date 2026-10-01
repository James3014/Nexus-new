from __future__ import annotations

import copy

import pytest

from nexus.research.core_effectiveness_observability import (
    ELIGIBLE,
    IDENTITY_GAP,
    OBSERVATION_SCHEMA,
    ObservabilityContractError,
    build_g0_coverage_report,
    from_devspace_core_session,
    identity_gap,
)


def _session(index: int, *, first_effect: str | None = None) -> dict[str, object]:
    return {
        "attemptId": f"attempt-{index}",
        "operationId": f"operation-{index}",
        "workspaceSessionId": f"workspace-{index}",
        "bindingId": f"binding-{index}",
        "bindingHash": f"sha256:{index:064x}",
        "sourceHead": f"{index:040x}",
        "sourceTree": f"{index + 100:040x}",
        "createdAt": f"2026-10-01T07:{index:02d}:00Z",
        "firstEffectAt": first_effect,
    }


def _observation(index: int) -> dict[str, object]:
    return from_devspace_core_session(
        repository="James3014/Nexus-new",
        work_item_id=f"James3014/Nexus-new#{2000 + index}",
        attempt_index=1,
        task_family="bounded_change",
        risk_class="low",
        execution_lane="DIRECT_CANONICAL",
        session=_session(index),
    )


def _terminal(row: dict[str, object]) -> dict[str, object]:
    out = copy.deepcopy(row)
    out.update({
        "terminal": True,
        "target_revision": "f" * 40,
        "target_tree": "e" * 40,
        "core_invoked": True,
        "core_verdict": "VERIFIED",
        "core_reason": "VERIFIER_AND_TREE_BOUND",
        "receipt_hash": "d" * 64,
        "baseline_result": "PASS",
        "terminal_outcome": "SUCCEEDED",
        "t_core_detection": "2026-10-01T08:00:01Z",
        "t_baseline_detection": "2026-10-01T08:00:03Z",
        "t_terminal_result": "2026-10-01T08:00:04Z",
        "core_orchestration_runtime_ms": 20,
        "verifier_runtime_ms": 100,
        "duplicate_verifier_runtime_ms": 0,
        "reviewer_calls": 0,
        "manual_interventions": 0,
        "attempts_to_green": 1,
    })
    return out


def test_devspace_pre_effect_session_is_complete_prospective_enrollment() -> None:
    row = _observation(1)

    assert row["eligibility_disposition"] == ELIGIBLE
    assert row["prospective"] is True

    report = build_g0_coverage_report([row])

    assert report["eligible_denominator"] == 1
    assert report["complete_prospective_enrollment_count"] == 1
    assert report["prospective_enrollment_coverage"] == 1.0
    assert report["gate"] == "G0_COVERAGE_TARGET_MET"
    assert report["claim_ceiling"] == "G0_OBSERVABILITY_ONLY_NO_UTILITY_CLAIM"
    assert report["small_n_zero_error_is_not_fleet_proof"] is True


def test_session_observed_after_first_effect_is_not_prospective() -> None:
    row = from_devspace_core_session(
        repository="James3014/Nexus-new",
        work_item_id="James3014/Nexus-new#2001",
        attempt_index=1,
        task_family="bounded_change",
        risk_class="low",
        execution_lane="DIRECT_CANONICAL",
        session=_session(1, first_effect="2026-10-01T07:01:01Z"),
    )

    report = build_g0_coverage_report([row])

    assert row["prospective"] is False
    assert report["prospective_enrollment_coverage"] == 0.0
    assert report["gate"] == "G0_COVERAGE_INSUFFICIENT"


def test_identity_gap_stays_in_denominator_and_is_never_backfilled() -> None:
    gap = identity_gap(
        repository="James3014/nexus-core",
        work_item_id="James3014/nexus-core#99",
        reason="mutation observed before durable attempt enrollment",
    )

    assert gap["eligibility_disposition"] == IDENTITY_GAP
    assert gap["prospective"] is False

    report = build_g0_coverage_report([gap])

    assert report["eligible_denominator"] == 1
    assert report["complete_prospective_enrollment_count"] == 0
    assert report["prospective_enrollment_coverage"] == 0.0
    assert report["retroactive_primary_enrollment_allowed"] is False
    assert report["dispositions"][IDENTITY_GAP] == 1


def test_exact_nineteen_of_twenty_meets_95_percent_target() -> None:
    rows = [_observation(index) for index in range(1, 20)]
    rows.append(
        identity_gap(
            repository="James3014/devspace",
            work_item_id="James3014/devspace#999",
            reason="pre-effect identity missing",
        )
    )

    report = build_g0_coverage_report(rows)

    assert report["eligible_denominator"] == 20
    assert report["complete_prospective_enrollment_count"] == 19
    assert report["prospective_enrollment_coverage"] == pytest.approx(0.95)
    assert report["gate"] == "G0_COVERAGE_TARGET_MET"


def test_eighteen_of_twenty_fails_95_percent_target() -> None:
    rows = [_observation(index) for index in range(1, 19)]
    rows.extend([
        identity_gap(
            repository="James3014/devspace",
            work_item_id=f"James3014/devspace#{999 + index}",
            reason="pre-effect identity missing",
        )
        for index in range(2)
    ])

    report = build_g0_coverage_report(rows)

    assert report["prospective_enrollment_coverage"] == pytest.approx(0.9)
    assert report["gate"] == "G0_COVERAGE_INSUFFICIENT"


def test_terminal_adjudication_completeness_is_measured_separately() -> None:
    complete = _terminal(_observation(1))
    incomplete = _terminal(_observation(2))
    incomplete["receipt_hash"] = None
    incomplete["missingness"] = {"receipt_hash": "core receipt not observed"}

    report = build_g0_coverage_report([complete, incomplete])

    assert report["prospective_enrollment_coverage"] == 1.0
    assert report["terminal_eligible_count"] == 2
    assert report["adjudication_complete_count"] == 1
    assert report["adjudication_completeness"] == 0.5
    assert report["terminal_missing_by_field"]["receipt_hash"] == 1


def test_duplicate_attempt_identity_fails_closed() -> None:
    row = _observation(1)

    with pytest.raises(ObservabilityContractError, match="duplicate_attempt_identity"):
        build_g0_coverage_report([row, row])


def test_identity_gap_requires_explicit_missingness() -> None:
    with pytest.raises(
        ObservabilityContractError,
        match="identity_gap_requires_attempt_id_and_enrolled_at_missingness",
    ):
        build_g0_coverage_report([
            {
                "schema": OBSERVATION_SCHEMA,
                "repository": "James3014/Nexus-new",
                "work_item_id": "James3014/Nexus-new#1",
                "eligibility_disposition": IDENTITY_GAP,
                "prospective": False,
                "terminal": False,
                "missingness": {},
            }
        ])


def test_empty_population_does_not_claim_coverage() -> None:
    report = build_g0_coverage_report([])

    assert report["eligible_denominator"] == 0
    assert report["prospective_enrollment_coverage"] is None
    assert report["gate"] == "NO_ELIGIBLE_ATTEMPTS_OBSERVED"
