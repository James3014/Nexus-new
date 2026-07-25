from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from nexus.services.product_capability_closure import (
    EXECUTION_FAILED,
    LIVE_EXECUTED_PASS,
    PRODUCT_CAPABILITIES,
)
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
    _run_family_canary(
        task.capability,
        positive=True,
        task_id_override=task.task_id,
    )
    response_path: Path | None = None
    receipt_path: Path | None = None
    response_bytes = b""
    receipt_bytes = b""
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
        response_bytes = response_path.read_bytes() if response_path.exists() else b""
        receipt_bytes = receipt_path.read_bytes() if receipt_path.exists() else b""
        response = json.loads(response_bytes) if response_bytes else {}
        execution_receipt = json.loads(receipt_bytes) if receipt_bytes else {}
        candidate = dict(response.get("candidate_summary") or {})
    else:
        response = {}
        execution_receipt = {}
        candidate = {}

    v_summary = dict(response.get("verifier_summary") or {})
    verified_artifact = dict(execution_receipt.get("verified_artifact") or {})
    v_status = str(v_summary.get("verifier_status") or "not_run").lower()
    receipt_verifier_status = str(execution_receipt.get("verifier_result") or "not_run").lower()
    v_passed = bool(
        v_summary.get("verifier_reached") is True
        and v_status == "pass"
        and int(v_summary.get("exit_code") if v_summary.get("exit_code") is not None else 1) == 0
        and execution_receipt.get("verifier_reached") is True
        and receipt_verifier_status == "pass"
        and str(verified_artifact.get("verifier_status") or "").lower() == "pass"
    )

    if task.capability in LOCAL_NATIVE:
        cand_hash = str(verified_artifact.get("candidate_hash") or "").strip()
        sel_hash = str(candidate.get("selected_candidate_hash") or "").strip()
        app_hash = str(candidate.get("applied_patch_hash") or "").strip()
        usage_status = dict(
            (response.get("local_outputs") or {}).get("capability_usage_status") or {}
        )
        local_execution = {
            "model_called": bool(
                execution_receipt.get("executor_invoked") is True
                and int(execution_receipt.get("provider_call_count") or 0) > 0
                and verified_artifact.get("model_invoked") is True
                and response.get("local_model_invoked") is True
            ),
            "output_delivered": bool(
                execution_receipt.get("substitution_stages", {}).get("output_delivered") is True
                and verified_artifact.get("output_delivered") is True
                and response.get("output_delivered") is True
            ),
            "candidate_isolated": bool(
                execution_receipt.get("isolation_status") == "isolated"
                and candidate.get("isolation_status") == "isolated"
            ),
            "candidate_hash": cand_hash,
            "selected_hash": sel_hash,
            "applied_hash": app_hash,
            "provider_family": str(execution_receipt.get("provider") or ""),
            "model_name": str(execution_receipt.get("resolved_model") or ""),
            "loop_entered": usage_status.get("repair_loop") == "used",
        }
    else:
        local_execution = {}

    evidence_root = Path(str(task.fixture["workspace_root"])) / ".nexus" / "closure_evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    request_payload = {
        "schema": "nexus.product_capability_local_native_request.v1",
        "task_id": task.task_id,
        "origin": task.origin,
        "capability": task.capability,
    }
    request_evidence_path = evidence_root / "request.json"
    request_evidence_path.write_text(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    stderr_evidence_path = evidence_root / "stderr.txt"
    stderr_evidence_path.write_bytes(str(v_summary.get("stderr_tail") or "").encode("utf-8"))

    evidence_refs: list[dict[str, object]] = [
        {
            "path": str(request_evidence_path),
            "payload": request_payload,
            "sha256": hashlib.sha256(request_evidence_path.read_bytes()).hexdigest(),
            "json_sha256": canonical_payload_hash(request_payload),
            "content_kind": "json",
            "kind": "request",
        },
        {
            "path": str(stderr_evidence_path),
            "sha256": hashlib.sha256(stderr_evidence_path.read_bytes()).hexdigest(),
            "content_kind": "raw_bytes",
            "kind": "stderr",
        },
    ]
    if response_bytes:
        response_evidence_path = evidence_root / "response.json"
        response_evidence_path.write_bytes(response_bytes)
        evidence_refs.append(
            {
                "path": str(response_evidence_path),
                "payload": response,
                "sha256": hashlib.sha256(response_bytes).hexdigest(),
                "json_sha256": canonical_payload_hash(response),
                "content_kind": "json",
                "kind": "stdout",
            }
        )
    copied_receipt_path: Path | None = None
    if receipt_bytes:
        copied_receipt_path = evidence_root / "execution_receipt.json"
        copied_receipt_path.write_bytes(receipt_bytes)
        evidence_refs.append(
            {
                "path": str(copied_receipt_path),
                "payload": execution_receipt,
                "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "json_sha256": canonical_payload_hash(execution_receipt),
                "content_kind": "json",
                "kind": "receipt",
            }
        )

    source_hash = str(execution_receipt.get("source_snapshot_hash") or "")
    candidate_hash = str(local_execution.get("candidate_hash") or "")
    effect_payload = {
        "capability": task.capability,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest() if receipt_bytes else "",
        "candidate_hash": candidate_hash,
        "verifier_status": v_status,
    }
    verifier_evidence = {
        "task_id": task.task_id,
        "verifier_summary": v_summary,
    }
    verifier_artifact = {
        "task_id": task.task_id,
        "candidate_hash": candidate_hash,
        "verifier_status": receipt_verifier_status,
        "source_hash": source_hash,
    }

    execution_class = "provider_native" if task.capability in LOCAL_NATIVE else "deterministic_runtime"
    provider_observation = (
        "executed"
        if int(execution_receipt.get("provider_call_count") or 0) > 0
        else "failed"
    )
    plan_id = str(execution_receipt.get("planner_decision_id") or "")
    revision = str(execution_receipt.get("workspace_revision") or "")
    upstream_hash = hashlib.sha256(receipt_bytes).hexdigest() if receipt_bytes else ""

    return {
        "task_id": task.task_id,
        "origin": task.origin,
        "capability": task.capability,
        "resolution_type": task.expected_resolution,
        "planner_decision_id": plan_id,
        "planner_selected": response.get("planner_selected") is True,
        "trigger_condition_met": True,
        "invoked": execution_receipt.get("executor_invoked") is True,
        "skipped": False,
        "status": "INVOKED",
        "gate_passed": v_passed,
        "physical_callable": str(execution_receipt.get("physical_callable") or ""),
        "provider": local_execution.get("provider_family") or "",
        "model": local_execution.get("model_name") or "",
        "network_invoked": False,
        "evidence_mode": "live_runtime",
        "run_root": str(evidence_root),
        "execution_class": execution_class,
        "provider_observation": provider_observation,
        "workspace_revision": revision,
        "upstream_receipt_sha256": upstream_hash,
        "receipt_path": str(copied_receipt_path or ""),
        "receipt_payload": execution_receipt,
        "receipt_hash": canonical_payload_hash(execution_receipt),
        "evidence_refs": evidence_refs,
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
    if capability == "repair_loop":
        assert verdict["status"] == EXECUTION_FAILED, verdict
        assert verdict["live_pass"] is False
        assert "repair_loop_not_entered" in verdict["missing_evidence_reasons"]
        assert row["record"]["local_execution"]["loop_entered"] is False
        return
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
    if capability == "repair_loop":
        assert verdict["status"] == EXECUTION_FAILED, verdict
        assert verdict["live_pass"] is False
        assert "repair_loop_not_entered" in verdict["missing_evidence_reasons"]
        assert row["record"]["local_execution"]["loop_entered"] is False
        return
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

    # A route-mode declaration without a physical LocalAssist receipt is not
    # execution proof and must stay fail-closed.
    row_consume = run_closure_task(task_consume, _local_production_runner, output_dir=tmp_path / "runs")
    verdict_consume = row_consume["closure_verdict"]
    assert verdict_consume["live_pass"] is False
    assert row_consume["record"].get("assist_lineage") is None


def test_e0_negative_controls_fail_closed(tmp_path: Path) -> None:
    """E0: Verify negative controls fail closed for missing, invalid, or tampered fields."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    if not _local_live_enabled():
        pytest.skip("requires one physical LocalModelExecutor receipt")

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

    # 3. A verifier projection that disagrees with the physical receipt blocks.
    tampered_verifier = dict(valid_record)
    verifier = dict(tampered_verifier["verifier"])
    artifact = dict(verifier["artifact_payload"])
    artifact["source_hash"] = "0" * 64
    verifier["artifact_payload"] = artifact
    verifier["artifact_hash"] = canonical_payload_hash(artifact)
    tampered_verifier["verifier"] = verifier
    v3 = verify_product_capability_resolution(tampered_verifier)
    assert v3["live_pass"] is False, f"v3 should fail closed: {v3}"
    assert "local_verifier_source_candidate_mismatch" in v3["missing_evidence_reasons"], f"v3 reasons: {v3['missing_evidence_reasons']}"
