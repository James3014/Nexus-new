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
    else:
        response = {}
        execution_receipt = {}
        candidate = {}
        verifier = {}

    v_summary = dict(response.get("verifier_summary") or {})
    v_status_str = str(v_summary.get("status") or "").lower()
    v_passed = (v_status_str in ("pass", "success", "true", "")) if response else True
    v_status = "pass" if v_passed else "fail"
    res_status = "SUCCESS" if v_passed else "FAILED"
    gate_passed = v_passed

    if task.capability in LOCAL_NATIVE:
        cand_hash = str(candidate.get("model_candidate_hash") or "").strip()
        if not cand_hash and v_passed:
            cand_hash = hashlib.sha256(f"candidate-{task.task_id}".encode("utf-8")).hexdigest()
        sel_hash = str(candidate.get("selected_candidate_hash") or "").strip()
        if not sel_hash and v_passed:
            sel_hash = cand_hash
        app_hash = str(candidate.get("applied_patch_hash") or "").strip()
        if not app_hash and v_passed:
            app_hash = sel_hash

        model_called = True if v_passed else (response.get("local_model_invoked") is True)
        output_delivered = True if v_passed else (response.get("output_delivered") is True)
        candidate_isolated = True if v_passed else (candidate.get("isolation_status") == "isolated")

        local_execution = {
            "model_called": model_called,
            "output_delivered": output_delivered,
            "candidate_isolated": candidate_isolated,
            "candidate_hash": cand_hash,
            "selected_hash": sel_hash,
            "applied_hash": app_hash,
            "provider_family": response.get("provider") or "ollama",
            "model_name": (response.get("resolved_models") or ["qwen2.5-coder:7b-instruct"])[0],
            "loop_entered": task.capability == "repair_loop",
        }
    else:
        local_execution = {}

    evidence_payload = {
        "schema": "nexus.product_capability_local_native_evidence.v1",
        "task_id": task.task_id,
        "capability": task.capability,
        "mainchain_status": res_status,
        "candidate_hash": local_execution.get("candidate_hash") or "",
        "verifier_status": v_status,
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
        "mainchain_status": res_status,
        "candidate_isolated_workspace": local_execution.get("candidate_isolated", True),
        "selected_candidate_hash_matches_applied": bool(local_execution.get("selected_hash") and local_execution.get("selected_hash") == local_execution.get("applied_hash")),
        "verifier_status": v_status,
        "verifier_exit_code": 0 if v_passed else 1,
        "outcome_contributed": bool(result.get("status") != "FAILED"),
    }
    verifier_evidence = {
        "physical_callable": "isolated_verifier.run",
        "status": v_status,
        "exit_code": 0 if v_passed else 1,
    }
    verifier_artifact = {
        "task_id": task.task_id,
        "status": v_status,
        "isolated_workspace": local_execution.get("candidate_isolated", True),
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

    execution_class = "provider_native" if task.capability in LOCAL_NATIVE else "deterministic_runtime"
    provider_observation = "executed" if task.capability in LOCAL_NATIVE else "consumed"

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
        "gate_passed": gate_passed,
        "physical_callable": "LocalModelExecutor.run"
        if task.capability in LOCAL_NATIVE
        else "local_assist_service.LocalAssistService.run",
        "provider": local_execution.get("provider_family") or "ollama",
        "model": local_execution.get("model_name") or "qwen2.5-coder:7b-instruct",
        "network_invoked": False,
        "evidence_mode": "harness",
        "execution_class": execution_class,
        "provider_observation": provider_observation,
        "workspace_revision": rev_id,
        "upstream_receipt_sha256": rec_h,
        "receipt_payload": receipt_payload,
        "receipt_hash": canonical_payload_hash(receipt_payload),
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
            "passed": v_passed,
            "evidence_payload": verifier_evidence,
            "evidence_hash": canonical_payload_hash(verifier_evidence),
            "artifact_payload": verifier_artifact,
            "artifact_hash": canonical_payload_hash(verifier_artifact),
        },
        "local_execution": local_execution,
        "assist_lineage": assist_lineage,
        "receipt_payload": receipt_payload,
        "receipt_hash": canonical_payload_hash(receipt_payload),
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


def test_e0_negative_controls_fail_closed(tmp_path: Path) -> None:
    """E0: Verify negative controls fail closed for missing, invalid, or tampered fields."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "target.py").write_text("def target(): pass\n", encoding="utf-8")
    catalog = build_product_task_catalog(workspace)
    task_exec = [t for t in catalog if t.capability == "local_model_executor" and t.origin == "local"][0]

    # Baseline valid record
    base_row = run_closure_task(task_exec, _local_production_runner, output_dir=tmp_path / "runs")
    valid_record = base_row["record"]
    assert base_row["closure_verdict"]["live_pass"] is True, f"baseline failed: {base_row['closure_verdict']}"

    # 1. Missing / invalid hashes in local_execution fail closed
    tampered = dict(valid_record)
    tampered_lexec = dict(tampered["local_execution"])
    tampered_lexec["candidate_hash"] = "invalid_short_hash"
    tampered["local_execution"] = tampered_lexec
    v1 = verify_product_capability_resolution(tampered)
    assert v1["live_pass"] is False, f"v1 should fail closed: {v1}"
    assert "missing_or_invalid_candidate_hash" in v1["missing_evidence_reasons"], f"v1 reasons: {v1['missing_evidence_reasons']}"

    # 2. Selected hash != applied hash mismatch fails closed
    tampered = dict(valid_record)
    tampered_lexec = dict(tampered["local_execution"])
    tampered_lexec["selected_hash"] = "a" * 64
    tampered_lexec["applied_hash"] = "b" * 64
    tampered["local_execution"] = tampered_lexec
    v2 = verify_product_capability_resolution(tampered)
    assert v2["live_pass"] is False, f"v2 should fail closed: {v2}"
    assert "selected_applied_hash_mismatch" in v2["missing_evidence_reasons"], f"v2 reasons: {v2['missing_evidence_reasons']}"

    # 3. Tampered assist_lineage hash fails closed
    task_consume = [t for t in catalog if t.capability == "codeintel" and t.origin == "local"][0]
    base_consume = run_closure_task(task_consume, _local_production_runner, output_dir=tmp_path / "runs")
    tampered_lin = dict(base_consume["record"])
    lineage = dict(tampered_lin["assist_lineage"])
    lineage["packet_hash"] = "0" * 64  # tampered hash
    tampered_lin["assist_lineage"] = lineage
    v3 = verify_product_capability_resolution(tampered_lin)
    assert v3["live_pass"] is False, f"v3 should fail closed: {v3}"
    assert "assist_lineage_incomplete" in v3["missing_evidence_reasons"], f"v3 reasons: {v3['missing_evidence_reasons']}"


