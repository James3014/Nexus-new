from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.product_capability_closure import LIVE_EXECUTED_PASS, PRODUCT_CAPABILITIES
from nexus.services.product_capability_closure_harness import (
    build_product_task_catalog,
    canonical_payload_hash,
    run_closure_task,
)
from tests.services.test_mainchain_family_canary_matrix import _run_family_canary


STAGE_OWNED = frozenset(
    {"artifact_gate", "claim_gate", "delivery_gate", "prompt_compression"}
)
LOCAL_NATIVE = frozenset({"local_model_executor", "repair_loop"})
ONLINE_NATIVE = tuple(
    capability
    for capability in PRODUCT_CAPABILITIES
    if capability not in STAGE_OWNED | LOCAL_NATIVE
)


def _online_task(capability: str, root: Path):
    return next(
        task
        for task in build_product_task_catalog(root)
        if task.origin == "online" and task.capability == capability
    )


def _production_canary_runner(task):
    result = _run_family_canary(
        task.capability,
        positive=True,
        task_id_override=task.task_id,
    )
    evidence_payload = {
        "schema": "nexus.product_capability_online_native_evidence.v1",
        "capability": task.capability,
        "mainchain_result": result,
        "expected_effect": dict(task.expected_effect),
        "public_claim_allowed": False,
    }
    evidence_root = Path(str(task.fixture["workspace_root"])) / ".nexus" / "closure_evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_root / f"online-{task.capability}.json"
    evidence_path.write_text(
        json.dumps(evidence_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    effect_payload = {
        "capability": task.capability,
        "action": result.get("action"),
        "semantic_status": result.get("semantic_status"),
        "consumer_proof": result.get("consumer_proof"),
        "contract_violations": result.get("contract_violations"),
        "outcome_contributed": result.get("outcome_contributed"),
    }
    verifier_evidence = {
        "physical_callable": result.get("verifier_physical_callable"),
        "exit_code": result.get("verifier_exit_code"),
        "status": result.get("verifier_status"),
    }
    verifier_artifact = {
        "source_artifact": result.get("verifier_artifact"),
        "status": result.get("verifier_status"),
        "task_id": task.task_id,
    }
    return {
        "task_id": task.task_id,
        "origin": task.origin,
        "capability": task.capability,
        "resolution_type": task.expected_resolution,
        "planner_decision_id": result.get("planner_decision_id"),
        "planner_selected": result.get("planner_selected") is True,
        "trigger_condition_met": result.get("positive") is True,
        "invoked": result.get("invoked") is True,
        "skipped": result.get("skipped") is True,
        "status": result.get("status"),
        "gate_passed": result.get("gate_passed") is True,
        "physical_callable": result.get("physical_callable"),
        "provider": "nexus.production.mainchain",
        "transport": "MainchainEntry",
        "evidence_refs": [
            {
                "path": str(evidence_path),
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
            "id": "family_canary_isolated_verifier",
            "invoked": bool(result.get("verifier_physical_callable")),
            "passed": result.get("verifier_status") == "pass"
            and result.get("verifier_exit_code") == 0,
            "evidence_payload": verifier_evidence,
            "evidence_hash": canonical_payload_hash(verifier_evidence),
            "artifact_payload": verifier_artifact,
            "artifact_hash": canonical_payload_hash(verifier_artifact),
        },
        "receipt_complete": True,
        "route_surface_changed": False,
        "public_claim_allowed": False,
    }


def test_online_native_denominator_is_exactly_28() -> None:
    assert len(ONLINE_NATIVE) == 28
    assert set(ONLINE_NATIVE) | STAGE_OWNED | LOCAL_NATIVE == set(PRODUCT_CAPABILITIES)


@pytest.mark.parametrize("capability", ONLINE_NATIVE)
def test_online_native_capability_has_execution_grade_mainchain_closure(
    capability: str,
    tmp_path: Path,
) -> None:
    task = _online_task(capability, tmp_path / "workspace")
    row = run_closure_task(
        task,
        _production_canary_runner,
        output_dir=tmp_path / "runs",
    )
    verdict = row["closure_verdict"]
    assert verdict["status"] == LIVE_EXECUTED_PASS, (capability, verdict)
    assert verdict["live_pass"] is True
    assert verdict["missing_evidence_reasons"] == []
    assert row["harness_consistency_errors"] == []
    evidence_payload = row["record"]["evidence_refs"][0]["payload"]
    assert evidence_payload["mainchain_result"]["_raw_receipt"]["task_id"] == task.task_id
    assert row["handler_or_stage_callsite"].startswith("capability_executor_registry:")
    assert row["verifier_result"] is True
    effect = row["record"]["observable_effect"]["artifact_payload"]
    assert effect["contract_violations"] == []
    assert effect["semantic_status"] in {"SUCCEEDED", "VERIFIED"}
    assert effect["outcome_contributed"] is True
    consumer = effect["consumer_proof"]
    if task.expected_effect["consumer_effect"] == "PROMPT_EVIDENCE":
        assert consumer["evidence_refs_present"] or consumer["prompt_marker_or_payload"]
    elif task.expected_effect["consumer_effect"] == "EXECUTION_CONTROL":
        assert consumer["control_receipt"] is True
    elif task.expected_effect["consumer_effect"] == "POSTFLIGHT_GATE":
        assert consumer["gate_receipt"] is True
    assert row["public_claim_allowed"] is False
