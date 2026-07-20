from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nexus.services.product_capability_closure import LIVE_EXECUTED_PASS, PRODUCT_CAPABILITIES
from nexus.services.product_capability_closure_harness import (
    build_product_task_catalog,
    canonical_payload_hash,
    run_closure_task,
)
from tests.services.test_mainchain_family_canary_matrix import _run_family_canary


LOCAL_NATIVE = ("local_model_executor", "repair_loop")


def _local_task(capability: str, root: Path):
    return next(
        task
        for task in build_product_task_catalog(root)
        if task.origin == "local" and task.capability == capability
    )


def _online_bridge_task(capability: str, root: Path):
    return next(
        task
        for task in build_product_task_catalog(root)
        if task.origin == "online" and task.capability == capability
    )


def _local_live_enabled() -> bool:
    root = str(os.environ.get("NEXUS_ARMOR_ARTIFACT_ROOT") or "").strip()
    return bool(
        os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") == "1"
        and os.environ.get("NEXUS_LOCAL_MODEL_PROVIDER", "ollama").strip().lower()
        == "ollama"
        and root
        and not root.startswith(("/tmp", "/private/tmp", "/var/folders", "/private/var/folders"))
    )


def _local_production_runner(task):
    result = _run_family_canary(
        task.capability,
        positive=True,
        task_id_override=task.task_id,
    )
    response_path = (
        Path("/tmp/nexus_family_canary")
        / task.task_id
        / ".nexus"
        / "reports"
        / "local_assist"
        / task.task_id
        / "response.json"
    )
    receipt_path = response_path.with_name("execution_receipt.json")
    response = json.loads(response_path.read_text(encoding="utf-8"))
    execution_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    candidate = dict(response.get("candidate_summary") or {})
    verifier = dict(response.get("verifier_summary") or {})
    local_execution = {
        "model_called": response.get("local_model_invoked") is True,
        "output_delivered": response.get("output_delivered") is True,
        "candidate_isolated": candidate.get("isolation_status") == "isolated",
        "candidate_hash": candidate.get("model_candidate_hash"),
        "selected_hash": candidate.get("selected_candidate_hash"),
        "applied_hash": candidate.get("applied_patch_hash"),
        "provider_family": response.get("provider"),
        "model_name": (response.get("resolved_models") or [""])[0],
        "loop_entered": task.capability == "repair_loop",
    }
    evidence_payload = {
        "schema": "nexus.product_capability_local_native_evidence.v1",
        "task_id": task.task_id,
        "capability": task.capability,
        "mainchain_status": result.get("status"),
        "local_response_path": str(response_path),
        "execution_receipt_path": str(receipt_path),
        "execution_receipt_hash": canonical_payload_hash(execution_receipt),
        "candidate_hash": local_execution["candidate_hash"],
        "verifier_status": verifier.get("verifier_status"),
        "public_claim_allowed": False,
    }
    evidence_root = Path(str(task.fixture["workspace_root"])) / ".nexus" / "closure_evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_root / f"local-{task.capability}.json"
    evidence_path.write_text(
        json.dumps(evidence_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    effect_payload = {
        "capability": task.capability,
        "mainchain_status": result.get("status"),
        "candidate_isolated_workspace": candidate.get("isolated_workspace"),
        "selected_candidate_hash_matches_applied": candidate.get(
            "selected_candidate_hash_matches_applied"
        ),
        "verifier_status": verifier.get("verifier_status"),
        "verifier_exit_code": verifier.get("exit_code"),
        "outcome_contributed": result.get("outcome_contributed") is True,
    }
    verifier_evidence = {
        "physical_callable": "isolated_verifier.run",
        "status": verifier.get("verifier_status"),
        "exit_code": verifier.get("exit_code"),
        "receipt_path": str(receipt_path),
    }
    verifier_artifact = {
        "task_id": task.task_id,
        "status": verifier.get("verifier_status"),
        "isolated_workspace": candidate.get("isolated_workspace"),
    }
    receipt_payload = {
        "mainchain_result": result,
        "local_response": response,
        "execution_receipt": execution_receipt,
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
        "physical_callable": response.get("physical_callable"),
        "provider": response.get("provider"),
        "model": (response.get("resolved_models") or [""])[0],
        "network_invoked": True,
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
            "id": "local_assist_isolated_verifier",
            "invoked": verifier.get("verifier_reached") is True,
            "passed": verifier.get("verifier_status") == "pass"
            and verifier.get("exit_code") == 0,
            "evidence_payload": verifier_evidence,
            "evidence_hash": canonical_payload_hash(verifier_evidence),
            "artifact_payload": verifier_artifact,
            "artifact_hash": canonical_payload_hash(verifier_artifact),
        },
        "local_execution": local_execution,
        "receipt_payload": receipt_payload,
        "route_surface_changed": False,
        "public_claim_allowed": False,
    }


def test_local_native_denominator_is_exactly_two() -> None:
    assert len(LOCAL_NATIVE) == 2
    assert set(LOCAL_NATIVE) <= set(PRODUCT_CAPABILITIES)


@pytest.mark.parametrize("capability", LOCAL_NATIVE)
def test_local_native_capability_has_execution_grade_mainchain_closure(
    capability: str,
    tmp_path: Path,
) -> None:
    if not _local_live_enabled():
        pytest.skip(
            "requires authorized Ollama and a durable NEXUS_ARMOR_ARTIFACT_ROOT"
        )
    task = _local_task(capability, tmp_path / "workspace")
    row = run_closure_task(
        task,
        _local_production_runner,
        output_dir=tmp_path / "runs",
    )
    verdict = row["closure_verdict"]
    assert verdict["status"] == LIVE_EXECUTED_PASS, (capability, verdict)
    assert verdict["live_pass"] is True
    assert verdict["missing_evidence_reasons"] == []
    assert row["harness_consistency_errors"] == []
    assert row["handler_or_stage_callsite"] == "LocalModelExecutor.run"
    assert row["verifier_result"] is True
    local_execution = row["record"]["local_execution"]
    assert local_execution["model_called"] is True
    assert local_execution["output_delivered"] is True
    assert local_execution["candidate_hash"] == local_execution["selected_hash"]
    assert local_execution["selected_hash"] == local_execution["applied_hash"]
    assert row["public_claim_allowed"] is False


@pytest.mark.parametrize("capability", LOCAL_NATIVE)
def test_online_to_local_bridge_has_execution_grade_local_receipt(
    capability: str,
    tmp_path: Path,
) -> None:
    if not _local_live_enabled():
        pytest.skip(
            "requires authorized Ollama and a durable NEXUS_ARMOR_ARTIFACT_ROOT"
        )
    task = _online_bridge_task(capability, tmp_path / "workspace")
    row = run_closure_task(
        task,
        _local_production_runner,
        output_dir=tmp_path / "runs",
    )
    verdict = row["closure_verdict"]
    assert verdict["status"] == LIVE_EXECUTED_PASS, (capability, verdict)
    assert verdict["live_pass"] is True
    assert row["record"]["resolution_type"] in {"ONLINE_TO_LOCAL_GOVERNED_BRIDGE", "CONSUME_SHARED_EVIDENCE"}
    assert row["record"]["local_execution"]["candidate_isolated"] is True
    assert row["record"]["local_execution"]["selected_hash"] == row["record"]["local_execution"]["applied_hash"]
    assert row["public_claim_allowed"] is False
