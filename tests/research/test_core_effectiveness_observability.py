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
    from_devspace_core_session_readback,
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


def test_session_read_after_first_effect_preserves_durable_prospective_order() -> None:
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

    assert row["first_effect_at"] == "2026-10-01T07:01:01Z"
    assert row["prospective"] is True
    assert report["prospective_enrollment_coverage"] == 1.0
    assert report["gate"] == "G0_COVERAGE_TARGET_MET"


def test_session_with_reversed_effect_order_is_not_prospective() -> None:
    row = from_devspace_core_session(
        repository="James3014/Nexus-new",
        work_item_id="James3014/Nexus-new#2002",
        attempt_index=1,
        task_family="bounded_change",
        risk_class="low",
        execution_lane="DIRECT_CANONICAL",
        session=_session(2, first_effect="2026-10-01T07:01:59Z"),
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


def test_devspace_readback_projects_candidate_core_missingness_and_independent_terminal_together() -> None:
    profile_hash = "sha256:26aaa763d00ecb7d18b9c14ff4291998ed1aaa0af43b81d617799648d3922487"
    entry = {
        "session": {
            "id": "cms_b20ea925bada44b2aa3af0e9a1383188",
            "workspaceSessionId": "ws_3ee6ea21fc",
            "attemptId": "wave4-core-verdict-capture-canary-20261004-attempt-1",
            "operationId": "wave4-core-verdict-capture-canary-20261004-op-v1",
            "bindingId": "wave4-core-verdict-capture-canary-20261004-binding-v1",
            "bindingHash": "sha256:ce16cdc2e588bb4b4e50ddf8157a965b3af95d4b4587e9acb60ba64c7115594f",
            "sourceHead": "79c59fea72e2a3f56cfe9fee3915686c73de684a",
            "sourceTree": "11c19b2bf9164d5c10bd9829683221b1727c210d",
            "createdAt": "2026-10-03T18:32:56.262Z",
            "firstEffectAt": "2026-10-03T18:33:08.557Z",
            "binding": {"core": {"verification_profile": {"profile_hash": profile_hash}}},
        },
        "candidate": {
            "sessionId": "cms_b20ea925bada44b2aa3af0e9a1383188",
            "workspaceSessionId": "ws_3ee6ea21fc",
            "bindingHash": "sha256:ce16cdc2e588bb4b4e50ddf8157a965b3af95d4b4587e9acb60ba64c7115594f",
            "sourceHead": "79c59fea72e2a3f56cfe9fee3915686c73de684a",
            "sourceTree": "11c19b2bf9164d5c10bd9829683221b1727c210d",
            "candidateHead": "615e3710621ad29f788a33fd4966be60923887b7",
            "candidateTree": "acb7a0b487374c4d33f4b1d76c98fd6531a9e83d",
            "createdAt": "2026-10-03T18:33:13.488Z",
            "changeSetHash": "sha256:3519735f427ef1d73829f0d4f9778a9148f0bdccbefc46ebab34dfb36f47390c",
            "acceptanceContractHash": "sha256:" + "9" * 64,
            "changeManifestHash": "sha256:7b72e1d82f8f9ba9a53450f7d304dc27f307ff0b0e9ea7672f619e74341c09f5",
        },
        "coreAcquisitionObservation": {
            "operationId": "cca_7f65710d39b98ce51a28cf61cac9508a",
            "durableOperationId": "cca_7f65710d39b98ce51a28cf61cac9508a",
            "acquisitionStatus": "MISSINGNESS",
            "coreInvoked": False,
            "coreVerdict": None,
            "coreReason": None,
            "receiptHash": None,
            "tCoreDetection": None,
            "orchestrationRuntimeMs": None,
            "missingnessCode": "CORE_RUNTIME_UNAVAILABLE_OR_MISMATCH",
            "missingnessDetail": "Core acquisition runtime binding is incomplete or mismatched.",
            "profileHash": profile_hash,
            "sessionId": "cms_b20ea925bada44b2aa3af0e9a1383188",
            "candidateHead": "615e3710621ad29f788a33fd4966be60923887b7",
            "candidateTree": "acb7a0b487374c4d33f4b1d76c98fd6531a9e83d",
            "sourceRevision": "79c59fea72e2a3f56cfe9fee3915686c73de684a",
            "bindingHash": "sha256:ce16cdc2e588bb4b4e50ddf8157a965b3af95d4b4587e9acb60ba64c7115594f",
            "acceptanceContractHash": "sha256:" + "9" * 64,
            "changeSetHash": "sha256:3519735f427ef1d73829f0d4f9778a9148f0bdccbefc46ebab34dfb36f47390c",
            "coreRuntimeIdentity": None,
            "createdAt": "2026-10-03T18:33:13.489Z",
        },
    }
    original = copy.deepcopy(entry)

    row = from_devspace_core_session_readback(
        repository="James3014/devspace",
        work_item_id="wave4-physical-canary-20261004",
        attempt_index=1,
        task_family="synthetic_capture_canary",
        risk_class="low",
        execution_lane="DIRECT_CANONICAL",
        census_entry=entry,
        independent_terminal={
            "evidence_id": "wave4-independent-terminal-verifier-20261004",
            "candidate_head": "615e3710621ad29f788a33fd4966be60923887b7",
            "baseline_result": "PASS",
            "terminal_outcome": "CANARY_TERMINAL_CHECKS_PASS",
            "t_baseline_detection": "2026-10-03T18:47:17Z",
            "t_terminal_result": "2026-10-03T18:47:17Z",
            "verifier_runtime_ms": 103,
            "duplicate_verifier_runtime_ms": 0,
            "reviewer_calls": 0,
            "manual_interventions": 0,
            "attempts_to_green": 1,
        },
    )

    assert entry == original
    assert row["prospective"] is True
    assert row["candidate_head"] == row["target_revision"]
    assert row["candidate_tree"] == row["target_tree"]
    assert row["core_acquisition_status"] == "MISSINGNESS"
    assert row["core_missingness_code"] == "CORE_RUNTIME_UNAVAILABLE_OR_MISMATCH"
    assert row["verification_profile_hash"] == profile_hash
    assert row["core_verdict"] is None
    assert row["receipt_hash"] is None
    assert row["terminal_evidence_id"] == "wave4-independent-terminal-verifier-20261004"
    assert row["terminal_candidate_head"] == row["candidate_head"]
    assert row["terminal_outcome"] == "CANARY_TERMINAL_CHECKS_PASS"
    assert row["missingness"]["core_verdict"] == "Core acquisition runtime binding is incomplete or mismatched."

    report = build_g0_coverage_report([row])

    assert report["terminal_eligible_count"] == 1
    assert report["adjudication_complete_count"] == 0
    assert report["terminal_missing_by_field"]["core_verdict"] == 1
    assert report["terminal_missing_by_field"]["receipt_hash"] == 1
    assert report["claim_ceiling"] == "G0_OBSERVABILITY_ONLY_NO_UTILITY_CLAIM"
    assert report["retroactive_primary_enrollment_allowed"] is False

    complete_entry = copy.deepcopy(entry)
    complete_entry["coreAcquisitionObservation"].update({
        "acquisitionStatus": "VERDICT_RECORDED",
        "coreInvoked": True,
        "coreVerdict": "VERIFIED",
        "coreReason": "NO_REASON_CODES",
        "receiptHash": "sha256:" + "d" * 64,
        "tCoreDetection": "2026-10-03T18:33:15Z",
        "orchestrationRuntimeMs": 42,
        "missingnessCode": None,
        "missingnessDetail": None,
    })
    terminal_fields = (
        "baseline_result", "terminal_outcome", "t_baseline_detection",
        "t_terminal_result", "verifier_runtime_ms", "duplicate_verifier_runtime_ms",
        "reviewer_calls", "manual_interventions", "attempts_to_green",
    )
    complete = from_devspace_core_session_readback(
        repository="James3014/devspace",
        work_item_id="wave4-prospective-positive",
        attempt_index=1,
        task_family="synthetic_capture_canary",
        risk_class="low",
        execution_lane="DIRECT_CANONICAL",
        census_entry=complete_entry,
        independent_terminal={
            "evidence_id": "independent-positive-terminal",
            "candidate_head": row["candidate_head"],
            **{field: row[field] for field in terminal_fields},
        },
    )
    assert complete["missingness"] == {}
    assert build_g0_coverage_report([complete])["adjudication_complete_count"] == 1


def test_devspace_readback_rejects_candidate_or_terminal_identity_drift() -> None:
    entry = {
        "session": {
            **_session(1),
            "id": "session-1",
            "bindingHash": "sha256:" + "a" * 64,
        },
        "candidate": {
            "sessionId": "session-1",
            "workspaceSessionId": "workspace-1",
            "bindingHash": "sha256:" + "b" * 64,
            "sourceHead": "0" * 40,
            "sourceTree": str(101).zfill(40),
            "candidateHead": "f" * 40,
            "candidateTree": "e" * 40,
            "acceptanceContractHash": "sha256:" + "9" * 64,
            "changeSetHash": "sha256:" + "8" * 64,
        },
        "coreAcquisitionObservation": {
            "profileHash": "sha256:" + "c" * 64,
            "sessionId": "session-1",
            "candidateHead": "f" * 40,
            "candidateTree": "e" * 40,
            "sourceRevision": "0" * 40,
            "bindingHash": "sha256:" + "a" * 64,
            "acceptanceContractHash": "sha256:" + "9" * 64,
            "changeSetHash": "sha256:" + "8" * 64,
        },
    }

    with pytest.raises(ObservabilityContractError, match="candidate_bindingHash_mismatch"):
        from_devspace_core_session_readback(
            repository="James3014/devspace",
            work_item_id="work-item-1",
            attempt_index=1,
            task_family="bounded_change",
            risk_class="low",
            execution_lane="DIRECT_CANONICAL",
            census_entry=entry,
        )

    entry["candidate"]["bindingHash"] = entry["session"]["bindingHash"]
    entry["candidate"]["sourceHead"] = entry["session"]["sourceHead"]
    entry["candidate"]["sourceTree"] = entry["session"]["sourceTree"]
    entry["coreAcquisitionObservation"]["sourceRevision"] = entry["session"]["sourceHead"]
    entry["coreAcquisitionObservation"]["profileHash"] = "sha256:" + "d" * 64
    entry["session"]["binding"] = {
        "core": {"verification_profile": {"profile_hash": "sha256:" + "c" * 64}}
    }

    with pytest.raises(ObservabilityContractError, match="core_observation_profile_hash_mismatch"):
        from_devspace_core_session_readback(
            repository="James3014/devspace",
            work_item_id="work-item-1",
            attempt_index=1,
            task_family="bounded_change",
            risk_class="low",
            execution_lane="DIRECT_CANONICAL",
            census_entry=entry,
        )

    entry["coreAcquisitionObservation"]["profileHash"] = "sha256:" + "c" * 64
    entry["coreAcquisitionObservation"]["candidateHead"] = "0" * 40
    with pytest.raises(ObservabilityContractError, match="core_observation_candidateHead_mismatch"):
        from_devspace_core_session_readback(
            repository="James3014/devspace",
            work_item_id="work-item-1",
            attempt_index=1,
            task_family="bounded_change",
            risk_class="low",
            execution_lane="DIRECT_CANONICAL",
            census_entry=entry,
        )
    entry["coreAcquisitionObservation"]["candidateHead"] = "f" * 40
    with pytest.raises(ObservabilityContractError, match="terminal_candidate_identity_mismatch"):
        from_devspace_core_session_readback(
            repository="James3014/devspace",
            work_item_id="work-item-1",
            attempt_index=1,
            task_family="bounded_change",
            risk_class="low",
            execution_lane="DIRECT_CANONICAL",
            census_entry=entry,
            independent_terminal={
                "evidence_id": "terminal-1",
                "candidate_head": "1" * 40,
                "terminal_outcome": "SUCCEEDED",
                "t_terminal_result": "2026-10-01T08:00:04Z",
            },
        )


def test_empty_population_does_not_claim_coverage() -> None:
    report = build_g0_coverage_report([])

    assert report["eligible_denominator"] == 0
    assert report["prospective_enrollment_coverage"] is None
    assert report["gate"] == "NO_ELIGIBLE_ATTEMPTS_OBSERVED"
