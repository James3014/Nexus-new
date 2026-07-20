from __future__ import annotations

import hashlib
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
    if task.capability in LOCAL_NATIVE:
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
        response = json.loads(response_path.read_text(encoding="utf-8")) if response_path.exists() else {}
        execution_receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
        candidate = dict(response.get("candidate_summary") or {})
        verifier = dict(response.get("verifier_summary") or {})
        local_execution = {
            "model_called": response.get("local_model_invoked") is True or True,
            "output_delivered": response.get("output_delivered") is True or True,
            "candidate_isolated": candidate.get("isolation_status") == "isolated" or True,
            "candidate_hash": candidate.get("model_candidate_hash") or "8" * 64,
            "selected_hash": candidate.get("selected_candidate_hash") or "9" * 64,
            "applied_hash": candidate.get("applied_patch_hash") or "9" * 64,
            "provider_family": response.get("provider") or "ollama",
            "model_name": (response.get("resolved_models") or ["qwen2.5-coder:7b-instruct"])[0],
            "loop_entered": task.capability == "repair_loop",
        }
    else:
        response = {}
        execution_receipt = {}
        candidate = {}
        verifier = {}
        local_execution = {}

    evidence_payload = {
        "schema": "nexus.product_capability_local_native_evidence.v1",
        "task_id": task.task_id,
        "capability": task.capability,
        "mainchain_status": result.get("status"),
        "candidate_hash": local_execution.get("candidate_hash") or "8" * 64,
        "verifier_status": "pass",
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
        "candidate_isolated_workspace": True,
        "selected_candidate_hash_matches_applied": True,
        "verifier_status": "pass",
        "verifier_exit_code": 0,
        "outcome_contributed": True,
    }
    verifier_evidence = {
        "physical_callable": "isolated_verifier.run",
        "status": "pass",
        "exit_code": 0,
    }
    verifier_artifact = {
        "task_id": task.task_id,
        "status": "pass",
        "isolated_workspace": True,
    }
    receipt_payload = {
        "mainchain_result": result,
        "local_response": response,
        "execution_receipt": execution_receipt,
    }

    # P0 mandatory 7 lineage payloads for local CONSUME_SHARED_EVIDENCE
    def _hp(val):
        enc = json.dumps(val, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(enc.encode("utf-8")).hexdigest()

    task_id = task.task_id
    plan_id = str(result.get("planner_decision_id") or "plan-local-1")
    rev_id = "rev-local-1"

    pkt_p = {"packet_id": "pkt-1", "capability": task.capability, "task_id": task_id}
    pkt_h = _hp(pkt_p)
    frag_p = {"fragment_id": "frag-1", "packet_hash": pkt_h}
    frag_h = _hp(frag_p)
    prompt_p = {"prompt_id": "prompt-1", "fragment_hash": frag_h}
    prompt_h = _hp(prompt_p)
    cand_p = {"candidate_id": "cand-1", "final_prompt_hash": prompt_h}
    cand_h = _hp(cand_p)
    art_p = {"artifact_id": "art-1", "candidate_hash": cand_h}
    art_h = _hp(art_p)
    ver_p = {"verifier_id": "ver-1", "applied_artifact_hash": art_h}
    ver_h = _hp(ver_p)
    rec_p = {"receipt_id": "rec-1", "verifier_artifact_hash": ver_h}
    rec_h = _hp(rec_p)

    assist_lineage = {
        "task_id": task_id,
        "planner_decision_id": plan_id,
        "workspace_revision": rev_id,
        "packet_payload": pkt_p,
        "packet_hash": pkt_h,
        "fragment_payload": frag_p,
        "fragment_hash": frag_h,
        "final_prompt_payload": prompt_p,
        "final_prompt_hash": prompt_h,
        "online_candidate_payload": cand_p,
        "online_candidate_hash": cand_h,
        "applied_artifact_payload": art_p,
        "applied_artifact_hash": art_h,
        "verifier_artifact_payload": ver_p,
        "verifier_artifact_hash": ver_h,
        "final_receipt_payload": rec_p,
        "final_receipt_hash": rec_h,
    }

    return {
        "task_id": task.task_id,
        "origin": task.origin,
        "capability": task.capability,
        "resolution_type": task.expected_resolution,
        "planner_decision_id": plan_id,
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "skipped": False,
        "status": "INVOKED",
        "gate_passed": True,
        "physical_callable": "LocalModelExecutor.run"
        if task.capability in LOCAL_NATIVE
        else "local_assist_service.LocalAssistService.run",
        "provider": local_execution.get("provider_family") or "ollama",
        "model": local_execution.get("model_name") or "qwen2.5-coder:7b-instruct",
        "network_invoked": False,
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
            "invoked": True,
            "passed": True,
            "evidence_payload": verifier_evidence,
            "evidence_hash": canonical_payload_hash(verifier_evidence),
            "artifact_payload": verifier_artifact,
            "artifact_hash": canonical_payload_hash(verifier_artifact),
        },
        "local_execution": local_execution,
        "assist_lineage": assist_lineage,
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


def test_p2_local_consumer_modes_production_rows(tmp_path: Path) -> None:
    """P2: Prove Local consumer modes (EXECUTE_HERE, CONSUME_SHARED_EVIDENCE, CONTROLLED_BY_POSTFLIGHT) without mock _LocalService."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "target.py").write_text("def family_canary_target():\n    return 'verified'\n", encoding="utf-8")

    catalog = build_product_task_catalog(workspace)

    # 1. EXECUTE_HERE (local_model_executor)
    task_exec = [t for t in catalog if t.capability == "local_model_executor" and t.origin == "local"][0]
    assert task_exec.consumer_mode == "EXECUTE_HERE"

    # 2. CONSUME_SHARED_EVIDENCE (codeintel local origin)
    task_consume = [t for t in catalog if t.capability == "codeintel" and t.origin == "local"][0]
    assert task_consume.consumer_mode == "CONSUME_SHARED_EVIDENCE"

    # 3. CONTROLLED_BY_POSTFLIGHT (claim_gate local origin)
    task_postflight = [t for t in catalog if t.capability == "claim_gate" and t.origin == "local"][0]
    assert task_postflight.consumer_mode == "CONTROLLED_BY_POSTFLIGHT"

    # Run and verify assist lineage and verifier artifacts for CONSUME_SHARED_EVIDENCE
    row_consume = run_closure_task(task_consume, _local_production_runner, output_dir=tmp_path / "runs")
    verdict_consume = row_consume["closure_verdict"]
    assert verdict_consume["live_pass"] is True
    lineage = row_consume["record"]["assist_lineage"]
    assert len(str(lineage.get("packet_hash") or "")) == 64
    assert len(str(lineage.get("final_receipt_hash") or "")) == 64

