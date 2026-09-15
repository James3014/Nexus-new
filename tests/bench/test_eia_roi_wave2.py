from __future__ import annotations

import json

import pytest

from scripts.bench.eia_roi_wave2 import (
    FIXED_WORKER_MODEL,
    FIXED_WORKER_PROVIDER,
    FORMAL_SCORING,
    NON_SCORING,
    OBSERVATION_SCHEMA,
    PROTOCOL_COMMENT_ID,
    QUALIFICATION_WITNESSES,
    WAVE2_QUALIFIED,
    WAVE2_REVISE,
    Wave2QualificationError,
    assert_oracle_quarantine,
    assert_scoring_allowed,
    assert_stage1_pair_identity,
    build_qualification_receipt,
    deserialize_observation,
    execution_fixture_manifest,
    fixture_spec,
    mandatory_schedule,
    serialize_observation,
    validate_materialization,
    validate_observation,
    validate_stage2_identity,
    validate_token_provenance,
)


def _observation(*, fixture_id: str = "F01", arm: str = "A1") -> dict[str, object]:
    spec = fixture_spec(fixture_id)
    return {
        "schema": OBSERVATION_SCHEMA,
        "protocol_comment_id": PROTOCOL_COMMENT_ID,
        "scoring_mode": NON_SCORING,
        "fixture_id": fixture_id,
        "family": spec["family"],
        "base_sha": spec["base_sha"],
        "base_tree": "a" * 40,
        "arm": arm,
        "order_index": 1,
        "attempt_id": f"attempt-{fixture_id}-{arm}",
        "planner_ref": "planner:fixture",
        "admission_ref": "admission:fixture",
        "worker_id": "worker-1",
        "profile": "profile-1",
        "provider": "provider-1",
        "model": "provider-1/model-1",
        "execution_realm": "isolated-worktree",
        "transport": "qualification-dry-run",
        "compiler_artifact": "compiler:none",
        "started_at": "2026-08-22T00:00:00Z",
        "ended_at": "2026-08-22T00:00:01Z",
        "first_pass_verifier_pass": False,
        "repair_count": 0,
        "final_disposition": "OUTCOME_UNKNOWN",
        "candidate_head": "",
        "candidate_tree": "",
        "candidate_diff_sha256": "",
        "scope_violation_count": 0,
        "unauthorized_path_attempt_count": 0,
        "identity_substitution_violation": False,
        "false_green_or_evidence_insufficiency": False,
        "diagnosis_status": "UNKNOWN",
        "diagnosis_probe": "",
        "evidence_refs": [],
        "coordinator_high_reasoning_invocation_count": 0,
        "coordinator_high_reasoning_turn_count": 0,
        "compiler_tokens": None,
        "compiler_token_status": "NOT_OBSERVED",
        "worker_tokens": None,
        "worker_token_status": "NOT_OBSERVED",
        "coordinator_tokens": None,
        "coordinator_token_status": "NOT_OBSERVED",
        "observable_total_tokens": 0,
        "input_bytes": 0,
        "output_bytes": 0,
        "context_bytes": 0,
        "verifier_command": spec["verifier_command"],
        "verifier_artifact_ref": "",
        "diff_check_pass": False,
        "allowed_path_audit_pass": False,
        "deletion_audit_pass": False,
    }


def test_execution_manifest_is_exactly_twelve_fixtures_and_contains_no_oracle() -> None:
    manifest = execution_fixture_manifest()

    assert manifest["protocol_comment_id"] == PROTOCOL_COMMENT_ID
    assert manifest["scoring_mode"] == NON_SCORING
    assert [row["fixture_id"] for row in manifest["fixtures"]] == [
        f"F{index:02d}" for index in range(1, 13)
    ]
    assert "oracle" not in json.dumps(manifest, sort_keys=True).lower()


def test_mandatory_schedule_is_exactly_forty_eight_observations() -> None:
    schedule = mandatory_schedule()

    assert len(schedule) == 48
    assert sum(row["stage"] == 1 for row in schedule) == 24
    assert sum(row["stage"] == 2 for row in schedule) == 24
    assert {row["arm"] for row in schedule if row["stage"] == 1} == {"A1", "A3"}
    assert {row["arm"] for row in schedule if row["stage"] == 2} == {"B1", "B2"}


def test_mandatory_schedule_preserves_frozen_relative_arm_order() -> None:
    schedule = mandatory_schedule()

    def arms(stage: int, fixture_id: str) -> list[str]:
        return [
            str(row["arm"])
            for row in schedule
            if row["stage"] == stage and row["fixture_id"] == fixture_id
        ]

    for fixture_id in ("F01", "F02", "F03", "F07", "F08", "F09"):
        assert arms(1, fixture_id) == ["A1", "A3"]
    for fixture_id in ("F04", "F05", "F06", "F10", "F11", "F12"):
        assert arms(1, fixture_id) == ["A3", "A1"]
    for index in range(1, 13):
        fixture_id = f"F{index:02d}"
        expected = ["B1", "B2"] if index % 2 else ["B2", "B1"]
        assert arms(2, fixture_id) == expected


def test_materialization_binds_exact_base_paths_verifier_and_observed_tree() -> None:
    spec = fixture_spec("F12")

    receipt = validate_materialization(
        fixture_id="F12",
        actual_head=str(spec["base_sha"]),
        actual_tree="B" * 40,
        allowed_paths=spec["allowed_paths"],
        verifier_command=str(spec["verifier_command"]),
    )

    assert receipt == {"base_sha": spec["base_sha"], "base_tree": "b" * 40}


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("actual_head", "0" * 40, "FIXTURE_BASE_SHA_MISMATCH"),
        ("actual_tree", "not-a-tree", "INVALID_FIXTURE_TREE"),
        ("allowed_paths", (), "FIXTURE_ALLOWED_PATHS_MISMATCH"),
        ("verifier_command", "pytest -q", "FIXTURE_VERIFIER_MISMATCH"),
    ],
)
def test_materialization_fails_closed_on_binding_drift(
    field: str,
    value: object,
    error: str,
) -> None:
    spec = fixture_spec("F01")
    kwargs: dict[str, object] = {
        "fixture_id": "F01",
        "actual_head": spec["base_sha"],
        "actual_tree": "a" * 40,
        "allowed_paths": spec["allowed_paths"],
        "verifier_command": spec["verifier_command"],
    }
    kwargs[field] = value

    with pytest.raises(Wave2QualificationError, match=error):
        validate_materialization(**kwargs)  # type: ignore[arg-type]


def test_stage1_pair_requires_exact_same_selected_worker_binding() -> None:
    a1 = _observation(arm="A1")
    a3 = _observation(arm="A3")
    a3["attempt_id"] = "different-attempt-is-allowed"

    assert_stage1_pair_identity(a1, a3)

    a3["model"] = "provider-1/substituted-model"
    with pytest.raises(Wave2QualificationError, match="STAGE1_PAIR_IDENTITY_MISMATCH:model"):
        assert_stage1_pair_identity(a1, a3)


def test_stage2_fixed_worker_requires_exact_identity_and_fresh_availability() -> None:
    row = {
        "arm": "B1",
        "provider": FIXED_WORKER_PROVIDER,
        "model": FIXED_WORKER_MODEL,
        "admission_state": "ALLOW",
        "provider_preflight": "AVAILABLE",
    }

    validate_stage2_identity(row)

    row["model"] = "opencode-go/another-model"
    with pytest.raises(Wave2QualificationError, match="FIXED_WORKER_IDENTITY_MISMATCH"):
        validate_stage2_identity(row)


def test_stage2_authoritative_selection_requires_planner_and_admission() -> None:
    row = {
        "arm": "B2",
        "planner_ref": "planner:decision",
        "admission_ref": "admission:decision",
        "admission_state": "ALLOW",
    }
    validate_stage2_identity(row)

    row["planner_ref"] = ""
    with pytest.raises(
        Wave2QualificationError,
        match="AUTHORITATIVE_SELECTION_MISSING_PLANNER_REF",
    ):
        validate_stage2_identity(row)


def test_oracle_quarantine_rejects_leak_and_requires_external_token_set() -> None:
    assert_oracle_quarantine(
        ["bounded task contract without solution material"],
        forbidden_tokens=["hidden-oracle-head", "hidden-oracle-pr"],
    )

    with pytest.raises(Wave2QualificationError, match="HIDDEN_ORACLE_LEAK"):
        assert_oracle_quarantine(
            ["prompt accidentally contains hidden-oracle-head"],
            forbidden_tokens=["hidden-oracle-head"],
        )
    with pytest.raises(Wave2QualificationError, match="ORACLE_TOKEN_SET_REQUIRED"):
        assert_oracle_quarantine(["payload"], forbidden_tokens=[])


def test_observation_roundtrip_preserves_not_observed_token_provenance() -> None:
    row = _observation()

    payload = serialize_observation(row)
    decoded = deserialize_observation(payload)

    assert decoded["worker_token_status"] == "NOT_OBSERVED"
    assert decoded["worker_tokens"] is None
    assert decoded["observable_total_tokens"] == 0


def test_token_provenance_never_accepts_value_for_not_observed() -> None:
    row = _observation()
    row["input_bytes"] = 7
    row["output_bytes"] = 5
    row["worker_tokens"] = 12

    with pytest.raises(Wave2QualificationError, match="UNOBSERVED_TOKEN_VALUE_PRESENT:worker"):
        validate_token_provenance(row)


def test_token_provenance_sums_only_measured_components() -> None:
    row = _observation()
    row["worker_token_status"] = "MEASURED"
    row["worker_tokens"] = 120
    row["observable_total_tokens"] = 120

    validate_token_provenance(row)

    row["observable_total_tokens"] = 121
    with pytest.raises(Wave2QualificationError, match="OBSERVABLE_TOTAL_TOKEN_MISMATCH"):
        validate_token_provenance(row)


def test_observation_fails_closed_on_protocol_and_repair_budget_drift() -> None:
    row = _observation()
    row["protocol_comment_id"] = PROTOCOL_COMMENT_ID + 1
    with pytest.raises(Wave2QualificationError, match="PROTOCOL_BINDING_MISMATCH"):
        validate_observation(row)

    row = _observation()
    row["repair_count"] = 2
    with pytest.raises(Wave2QualificationError, match="REPAIR_BUDGET_EXCEEDED"):
        validate_observation(row)


@pytest.mark.parametrize("repair_count", [True, False, "1", 1.0, None, -1, 2])
def test_observation_rejects_repair_count_type_confusion(repair_count: object) -> None:
    row = _observation()
    row["repair_count"] = repair_count

    with pytest.raises(Wave2QualificationError, match="REPAIR_BUDGET_EXCEEDED"):
        validate_observation(row)


def test_wave2_observation_cannot_be_relabelled_formal() -> None:
    row = _observation()
    row["scoring_mode"] = FORMAL_SCORING

    with pytest.raises(Wave2QualificationError, match="WAVE2_OBSERVATION_MUST_BE_NON_SCORING"):
        validate_observation(row)


def test_result_quarantine_blocks_formal_scoring_until_qualified() -> None:
    assert_scoring_allowed(qualification_state=WAVE2_REVISE, scoring_mode=NON_SCORING)

    with pytest.raises(
        Wave2QualificationError,
        match="FORMAL_SCORING_BEFORE_WAVE2_QUALIFICATION",
    ):
        assert_scoring_allowed(
            qualification_state=WAVE2_REVISE,
            scoring_mode=FORMAL_SCORING,
        )

    assert_scoring_allowed(
        qualification_state=WAVE2_QUALIFIED,
        scoring_mode=FORMAL_SCORING,
    )


def test_qualification_receipt_requires_all_six_physical_witnesses() -> None:
    witnesses = {name: f"evidence:{name}" for name in QUALIFICATION_WITNESSES}

    receipt = build_qualification_receipt(witnesses)
    assert receipt["gate_passed"] is True
    assert receipt["state"] == WAVE2_QUALIFIED
    assert receipt["missing_witnesses"] == []
    assert receipt["evidence_refs"] == witnesses
    assert receipt["formal_scoring_authorized"] is True

    witnesses["frozen_verifier_readback"] = ""
    receipt = build_qualification_receipt(witnesses)
    assert receipt["gate_passed"] is False
    assert receipt["state"] == WAVE2_REVISE
    assert receipt["missing_witnesses"] == ["frozen_verifier_readback"]
    assert receipt["formal_scoring_authorized"] is False


def test_qualification_receipt_rejects_unfrozen_witness_names() -> None:
    witnesses = {name: f"evidence:{name}" for name in QUALIFICATION_WITNESSES}
    witnesses["invented_shortcut"] = "evidence:shortcut"

    with pytest.raises(Wave2QualificationError, match="UNKNOWN_QUALIFICATION_WITNESS"):
        build_qualification_receipt(witnesses)
