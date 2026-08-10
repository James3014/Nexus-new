from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.bench.codex_dx_benchmark import (
    ReceiptError,
    compare_receipts,
    load_and_validate,
    validate_receipt,
)

ROOT = Path(__file__).resolve().parents[2]
BEFORE_MANIFEST = ROOT / "configs/benchmarks/codex_dx_before_v1.json"


def test_frozen_before_manifest_is_complete_and_valid() -> None:
    receipt, aggregate = load_and_validate(BEFORE_MANIFEST)

    assert receipt["arm"] == "before"
    assert receipt["source"]["commit"] == "b6601270edd95a756c4eab8c7a623006ee1b32d1"
    assert aggregate["trial_count"] == 15
    assert aggregate["valid_trial_count"] == 15
    assert aggregate["invalid_trial_count"] == 0
    assert aggregate["task_class_counts"] == {
        "bounded_change": 3,
        "focused_test": 3,
        "orientation": 3,
        "setup": 3,
        "verification": 3,
    }
    assert aggregate["observed_outcome_counts"] == {
        "failure": 2,
        "infra_failure": 4,
        "success": 9,
    }
    assert aggregate["success_rate"] == 0.6
    assert aggregate["median_context_bytes"] == 68015
    assert aggregate["unauthorized_action_total"] == 0

    schema = json.loads(
        (ROOT / "docs/benchmark/codex_dx_benchmark_receipt_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False


def _eligible_arm(receipt: dict, arm: str) -> dict:
    result = deepcopy(receipt)
    result["arm"] = arm
    if arm == "after":
        result["source"]["commit"] = "a" * 40
    task_class_by_id = {task["id"]: task["task_class"] for task in result["tasks"]}
    for artifact in result["session_artifacts"]:
        artifact["session_id"] = f"{arm}-fresh-{artifact['repetition']}"
        artifact["source_commit"] = result["source"]["commit"]
        for index, payload_trial in enumerate(artifact["payload"]["trials"]):
            payload_trial["outcome"] = "success"
            payload_trial["context_bytes"] = 100 + index
            payload_trial["context_items"] = 2
            payload_trial["tool_calls"] = 2
            payload_trial["wall_time_seconds"] = 1.0
            payload_trial["human_interventions"] = 0
            payload_trial["secret_reads"] = 0
            payload_trial["unauthorized_actions"] = 0
            payload_trial["changed_files"] = []
            payload_trial["within_scope"] = True
        payload_bytes = json.dumps(
            artifact["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        artifact["sha256"] = hashlib.sha256(payload_bytes).hexdigest()
    artifacts = {artifact["repetition"]: artifact for artifact in result["session_artifacts"]}
    for trial in result["trials"]:
        artifact = artifacts[trial["repetition"]]
        payload_trial = next(
            row for row in artifact["payload"]["trials"]
            if row["task_class"] == task_class_by_id[trial["task_id"]]
        )
        trial["session_id"] = artifact["session_id"]
        trial["fresh_context"] = True
        trial["source_commit"] = result["source"]["commit"]
        trial["verifier_status"] = "passed"
        trial["verifier_artifact"] = {
            "ref": f"inline-session:{artifact['session_id']}",
            "sha256": artifact["sha256"],
        }
        trial["valid"] = True
        trial["invalid_reasons"] = []
        trial["context"] = {"bytes": payload_trial["context_bytes"], "items": 2}
        trial["tool_calls"] = payload_trial["tool_calls"]
        trial["wall_time_seconds"] = payload_trial["wall_time_seconds"]
        trial["human_interventions"] = payload_trial["human_interventions"]
        trial["secret_reads"] = payload_trial["secret_reads"]
        trial["unauthorized_actions"] = payload_trial["unauthorized_actions"]
        trial["diff"] = {"changed_files": [], "within_scope": True}
        trial["outcome"] = payload_trial["outcome"]
    return result


def test_compare_fails_claim_gate_when_after_has_human_repair_or_failed_verifier() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    before = _eligible_arm(receipt, "before")
    after = _eligible_arm(receipt, "after")
    after_artifact = after["session_artifacts"][0]
    after_payload_trial = after_artifact["payload"]["trials"][0]
    after_payload_trial["human_interventions"] = 1
    after_payload_trial["outcome"] = "failure"
    after_artifact["sha256"] = hashlib.sha256(
        json.dumps(
            after_artifact["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    for trial in after["trials"]:
        if trial["repetition"] == 1:
            trial["verifier_artifact"]["sha256"] = after_artifact["sha256"]
    after["trials"][0]["human_interventions"] = 1
    after["trials"][0]["verifier_status"] = "failed"
    after["trials"][0]["outcome"] = "failure"

    comparison = compare_receipts(before, after)

    assert comparison["claim_eligible"] is False
    assert comparison["claim_blockers"] == [
        "after_human_interventions_nonzero",
        "after_not_15_of_15_verifier_confirmed",
    ]


def test_validate_rejects_incomplete_diff_evidence() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt["trials"][0]["diff"] = {"changed_files": []}

    with pytest.raises(ReceiptError, match="diff"):
        validate_receipt(receipt)


def test_three_fresh_sessions_each_cover_all_five_task_classes() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt = _eligible_arm(receipt, "before")

    aggregate = validate_receipt(receipt)

    assert aggregate["valid_trial_count"] == 15


def test_task_fixture_hash_binds_prompt_and_verifier_contract() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt["tasks"][0]["prompt"] += " silently changed"

    with pytest.raises(ReceiptError, match="fixture_sha256"):
        validate_receipt(receipt)


def test_session_artifact_hash_binds_persisted_luna_output() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt["session_artifacts"][0]["payload"]["trials"][0]["answer"] += " tampered"

    with pytest.raises(ReceiptError, match="session artifact hash"):
        validate_receipt(receipt)


def test_compare_rejects_session_reuse_across_arms() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    before = _eligible_arm(receipt, "before")
    after = _eligible_arm(receipt, "after")
    before_artifacts = {row["repetition"]: row for row in before["session_artifacts"]}
    for artifact in after["session_artifacts"]:
        artifact["session_id"] = before_artifacts[artifact["repetition"]]["session_id"]
    after_artifacts = {row["repetition"]: row for row in after["session_artifacts"]}
    for trial in after["trials"]:
        artifact = after_artifacts[trial["repetition"]]
        trial["session_id"] = artifact["session_id"]
        trial["verifier_artifact"]["ref"] = f"inline-session:{artifact['session_id']}"

    with pytest.raises(ReceiptError, match="fresh sessions"):
        compare_receipts(before, after)


def test_schema_rejects_undeclared_nested_trial_field() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt["trials"][0]["undeclared"] = True

    with pytest.raises(ReceiptError, match="additional property"):
        validate_receipt(receipt)


def test_before_arm_rejects_wrong_repository_or_source_commit() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt["source"]["commit"] = "f" * 40

    with pytest.raises(ReceiptError, match="frozen b660 source"):
        validate_receipt(receipt)


def test_session_artifact_ids_are_nonempty_and_distinct_even_if_trials_invalid() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt["session_artifacts"][1]["session_id"] = receipt["session_artifacts"][0]["session_id"]
    for trial in receipt["trials"]:
        trial["valid"] = False
        trial["invalid_reasons"] = ["negative_control"]

    with pytest.raises(ReceiptError, match="distinct session artifact"):
        validate_receipt(receipt)


def test_before_arm_requires_both_frozen_baseline_failures() -> None:
    receipt = json.loads(BEFORE_MANIFEST.read_text(encoding="utf-8"))
    receipt["baseline_evidence"] = []

    with pytest.raises(ReceiptError, match="baseline[_ ]evidence"):
        validate_receipt(receipt)
