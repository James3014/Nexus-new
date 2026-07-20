from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.product_capability_closure import EVIDENCE_INCOMPLETE, PRODUCT_CAPABILITIES
from nexus.services.product_capability_closure_harness import (
    MATRIX_SCHEMA,
    RUN_SCHEMA,
    build_product_task_catalog,
    canonical_payload_hash,
    payload_hash_matches,
    run_closure_task,
    run_origin_capability_matrix,
    validate_task_catalog,
)


def _fixture_runner(task):
    evidence_payload = {"capability": task.capability, "observed": True}
    effect_payload = {"effect": task.expected_effect["success_predicate"]}
    verifier_evidence = {"command": "python -m py_compile target.py", "exit_code": 0}
    verifier_artifact = {"status": "VERIFIED", "task_id": task.task_id}
    return {
        "task_id": task.task_id,
        "origin": task.origin,
        "capability": task.capability,
        "resolution_type": task.expected_resolution,
        "planner_decision_id": f"planner-{task.task_id}",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "skipped": False,
        "status": "INVOKED",
        "gate_passed": True,
        "physical_callable": "test:closure_fixture",
        "provider": "fixture",
        "evidence_refs": [
            {
                "path": f"/tmp/{task.task_id}.evidence.json",
                "payload": evidence_payload,
                "sha256": canonical_payload_hash(evidence_payload),
            }
        ],
        "structured_evidence_verified": True,
        "observable_effect": {
            "effect_type": task.expected_effect["consumer_effect"],
            "artifact_payload": effect_payload,
            "artifact_hash": canonical_payload_hash(effect_payload),
        },
        "verifier": {
            "id": "closure-target-py-compile",
            "invoked": True,
            "passed": True,
            "evidence_payload": verifier_evidence,
            "evidence_hash": canonical_payload_hash(verifier_evidence),
            "artifact_payload": verifier_artifact,
            "artifact_hash": canonical_payload_hash(verifier_artifact),
        },
        "route_surface_changed": False,
        "public_claim_allowed": False,
    }


def test_catalog_freezes_exact_34_by_2_tasks_with_real_trigger_inputs(tmp_path: Path) -> None:
    tasks = build_product_task_catalog(tmp_path)
    assert len(tasks) == 68
    assert validate_task_catalog(tasks) == []
    assert {(task.origin, task.capability) for task in tasks} == {
        (origin, capability)
        for origin in ("online", "local")
        for capability in PRODUCT_CAPABILITIES
    }
    assert all(task.expected_effect["success_predicate"] for task in tasks)
    assert all(task.allowed_files == ("target.py",) for task in tasks)
    assert all(task.provider_policy["fixture_allowed"] is False for task in tasks)
    triggered = [
        task
        for task in tasks
        if str(task.expected_effect["trigger_policy"]).startswith(("triggered", "escalate"))
    ]
    assert triggered
    assert all(task.fixture["route"]["escalate_triggered"] is True for task in triggered)
    assert all(task.fixture["executor_flags"][task.capability] is True for task in triggered)


def test_task_schema_hash_is_stable_and_input_sensitive(tmp_path: Path) -> None:
    task = build_product_task_catalog(tmp_path)[0]
    payload = task.to_dict()
    claimed = payload.pop("spec_hash")
    assert canonical_payload_hash(payload) == claimed
    payload["timeout_sec"] = 31.0
    assert canonical_payload_hash(payload) != claimed


def test_harness_persists_raw_receipt_and_fixture_still_fails_closed(tmp_path: Path) -> None:
    task = build_product_task_catalog(tmp_path)[0]
    row = run_closure_task(task, _fixture_runner, output_dir=tmp_path / "runs")
    assert row["schema"] == RUN_SCHEMA
    assert payload_hash_matches(row, "run_hash") is True
    raw_path = Path(row["raw_receipt_path"])
    assert raw_path.is_file()
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert canonical_payload_hash(raw) == row["receipt_hash"]
    assert row["closure_verdict"]["status"] == EVIDENCE_INCOMPLETE
    assert row["closure_verdict"]["live_pass"] is False
    assert "synthetic_or_fixture_execution" in row["closure_verdict"]["missing_evidence_reasons"]
    assert row["public_claim_allowed"] is False


def test_harness_rejects_identity_drift_and_runner_exception(tmp_path: Path) -> None:
    task = build_product_task_catalog(tmp_path)[0]

    def wrong_identity(spec):
        payload = _fixture_runner(spec)
        payload["capability"] = "belief"
        return payload

    row = run_closure_task(task, wrong_identity, output_dir=tmp_path / "wrong")
    assert "capability_mismatch" in row["harness_consistency_errors"]
    assert row["closure_verdict"]["live_pass"] is False

    def broken(_spec):
        raise RuntimeError("secret text must not escape")

    row = run_closure_task(task, broken, output_dir=tmp_path / "broken")
    assert row["harness_consistency_errors"] == [
        "missing_task_id",
        "missing_origin",
        "missing_capability",
        "missing_resolution_type",
        "missing_planner_decision_id",
        "route_surface_not_frozen",
        "claim_boundary_not_fail_closed",
        "runner_exception:RuntimeError",
    ]
    assert "secret text" not in json.dumps(row)


def test_matrix_receipt_has_68_rows_but_no_fixture_false_green(tmp_path: Path) -> None:
    tasks = build_product_task_catalog(tmp_path)
    payload = run_origin_capability_matrix(
        tasks,
        _fixture_runner,
        output_dir=tmp_path / "matrix",
    )
    assert payload["schema"] == MATRIX_SCHEMA
    assert payload["task_count"] == 68
    assert len(payload["rows"]) == 68
    assert payload["summary"]["matrix_pass"] == 0
    assert payload["summary"]["complete"] is False
    assert payload["public_claim_allowed"] is False
    assert payload_hash_matches(payload, "matrix_hash") is True
    stored = json.loads(Path(payload["matrix_path"]).read_text(encoding="utf-8"))
    assert payload_hash_matches(stored, "matrix_hash") is True


def test_catalog_validator_fails_closed_on_incomplete_subset(tmp_path: Path) -> None:
    errors = validate_task_catalog(build_product_task_catalog(tmp_path)[:1])
    assert "task_count:1" in errors
    assert any(error.startswith("missing:") for error in errors)
    with pytest.raises(ValueError, match="invalid closure task catalog"):
        run_origin_capability_matrix(
            build_product_task_catalog(tmp_path)[:1],
            _fixture_runner,
            output_dir=tmp_path / "incomplete",
        )
