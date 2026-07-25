from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nexus.services.capability_registry import LOCAL_STAGE_CAPABILITIES
from nexus.services.product_capability_closure import (
    EVIDENCE_INCOMPLETE,
    PRODUCT_CAPABILITIES,
)
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


def _production_canary_runner(task, *, evidence_mode: str = ""):
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
    if evidence_mode:
        evidence_payload["evidence_mode"] = evidence_mode
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
    # For LOCAL_STAGE_CAPABILITIES (local_model_executor, repair_loop), the online
    # capability row gate_passed is always False because gate ownership lives in the
    # local stage.  Use final_status=="OK" (driven by _local_live_proof_complete) as
    # the authoritative gate signal for these two capabilities only.
    is_local_stage_cap = task.capability in LOCAL_STAGE_CAPABILITIES
    raw_receipt = result.get("_raw_receipt") or {}
    raw_local_stage = raw_receipt.get("local") if isinstance(raw_receipt.get("local"), dict) else {}
    raw_local_response = raw_local_stage.get("response") if isinstance(raw_local_stage.get("response"), dict) else {}
    raw_candidate = raw_local_response.get("candidate_summary") if isinstance(raw_local_response.get("candidate_summary"), dict) else {}
    raw_verifier = raw_local_response.get("verifier_summary") if isinstance(raw_local_response.get("verifier_summary"), dict) else {}
    if is_local_stage_cap:
        gate_passed = result.get("final_status") == "OK"
        physical_callable = (
            result.get("physical_callable")
            or raw_local_response.get("physical_callable")
            or f"local_stage:{task.capability}:LocalModelExecutor.run"
        )
        # Assemble local_execution record required by _local_execution_reasons()
        candidate_hash = str(raw_candidate.get("selected_candidate_hash") or "")
        applied_hash = str(raw_candidate.get("applied_patch_hash") or candidate_hash)
        local_execution = {
            "model_called": raw_local_response.get("local_model_invoked") is True,
            "output_delivered": raw_local_response.get("output_delivered") is True,
            "candidate_isolated": raw_candidate.get("isolation_status") == "isolated",
            "candidate_hash": candidate_hash,
            "selected_hash": candidate_hash,
            "applied_hash": applied_hash,
            "provider_family": raw_local_response.get("provider") or "ollama",
            "model_name": raw_local_response.get("model") or "qwen2.5-coder:7b-instruct",
            "loop_entered": True,  # repair_loop: local stage invoked constitutes loop entry
            "network_invoked": False,
        }
    else:
        gate_passed = result.get("gate_passed") is True
        physical_callable = result.get("physical_callable")
        local_execution = {}
    result_dict = {
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
        "gate_passed": gate_passed,
        "physical_callable": physical_callable,
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
        "local_execution": local_execution,
        "receipt_complete": True,
        "route_surface_changed": False,
        "public_claim_allowed": False,
    }
    if evidence_mode:
        result_dict["evidence_mode"] = evidence_mode
    return result_dict



def test_online_native_denominator_is_exactly_28() -> None:
    assert len(ONLINE_NATIVE) == 28
    assert set(ONLINE_NATIVE) | STAGE_OWNED | LOCAL_NATIVE == set(PRODUCT_CAPABILITIES)


@pytest.mark.parametrize("capability", ONLINE_NATIVE)
def test_online_native_canary_is_structurally_valid_but_not_live_claimable(
    capability: str,
    tmp_path: Path,
) -> None:
    task = _online_task(capability, tmp_path / "workspace")
    row = run_closure_task(
        task,
        lambda t: _production_canary_runner(t, evidence_mode="canary"),
        output_dir=tmp_path / "runs",
    )
    verdict = row["closure_verdict"]
    assert verdict["status"] == EVIDENCE_INCOMPLETE, (capability, verdict)
    assert verdict["live_pass"] is False
    assert "non_live_evidence_mode:canary" in verdict["missing_evidence_reasons"]
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
