"""Authoritative five-stage receipt for the World C repair pipeline.

The receipt is built from phase executions recorded by :class:`PhaseRunner`.
It deliberately does not infer stage completion from fields left on HealContext.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from nexus.services.local_heal.interface import PhaseResult

WORLD_C_RECEIPT_SCHEMA = "nexus.world_c.pipeline_receipt.v1"
WORLD_C_STAGES = (
    "reproduction",
    "planning",
    "localization",
    "patch_synthesis",
    "verification",
)


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def canonical_stage_name(phase_name: str) -> str:
    name = str(phase_name or "").strip().lower()
    if name.startswith("patch_attempt") or name.startswith("patch_synthesis"):
        return "patch_synthesis"
    if name.startswith("verify_attempt") or name.startswith("verify_semantic_retry"):
        return "verification"
    return name if name in WORLD_C_STAGES else ""


def _stage_output_evidence(op: Any, stage: str) -> tuple[bool, str]:
    if stage == "reproduction":
        payload = {
            "repro_evidence": str(getattr(op, "repro_evidence", "") or "")[:4000],
            "reproduced": bool(getattr(op, "reproduced", False)),
            "skip_reproduction": bool(getattr(op, "skip_reproduction", False)),
        }
        present = bool(
            payload["repro_evidence"]
            or payload["reproduced"]
            or payload["skip_reproduction"]
        )
    elif stage == "planning":
        plan = getattr(op, "plan", None)
        payload = {"plan": plan}
        present = plan is not None
    elif stage == "localization":
        files = []
        for item in getattr(op, "localized_files", []) or []:
            path = str(getattr(item, "path", "") or "")
            content = str(getattr(item, "content", "") or "")
            files.append({"path": path, "content_hash": hashlib.sha256(content.encode()).hexdigest()})
        payload = {"localized_files": files}
        present = bool(files and all(item["path"] for item in files))
    elif stage == "patch_synthesis":
        patch = str(
            getattr(op, "final_patch", "")
            or getattr(op, "pre_verification_final_patch", "")
            or ""
        )
        payload = {"patch_hash": hashlib.sha256(patch.encode()).hexdigest() if patch else ""}
        present = bool(patch)
    else:
        report = str(getattr(op, "evaluation_report", "") or "")[:4000]
        verifier_receipt = getattr(op, "verifier_receipt", None)
        payload = {
            "evaluation_report": report,
            "verifier_receipt": verifier_receipt,
            "solve_eligible": bool(getattr(op, "solve_eligible", False)),
        }
        present = bool(report or verifier_receipt is not None)
    return present, _sha256_json(payload) if present else ""


def record_world_c_phase_result(ctx: Any, phase_name: str, result: PhaseResult) -> None:
    """Record one physical phase execution on the V2 operational context."""
    stage = canonical_stage_name(phase_name)
    if not stage:
        return
    op = getattr(ctx, "op", ctx)
    attempts = getattr(op, "_world_c_phase_attempts", None)
    if not isinstance(attempts, list):
        attempts = []
        setattr(op, "_world_c_phase_attempts", attempts)
    stage_attempt = 1 + sum(1 for item in attempts if item.get("stage") == stage)
    output_evidence_present, output_evidence_hash = _stage_output_evidence(op, stage)
    payload = {
        "stage": stage,
        "phase_name": str(phase_name),
        "attempt": stage_attempt,
        "success": bool(result.success),
        "exit_layer": str(result.exit_layer or ""),
        "failure_reason": str(result.failure_reason or "")[:500],
        "output_evidence_present": output_evidence_present,
        "output_evidence_hash": output_evidence_hash,
    }
    payload["evidence_hash"] = _sha256_json(payload)
    attempts.append(payload)


def build_world_c_receipt(ctx: Any) -> dict[str, Any]:
    """Build a deterministic, fail-closed five-stage pipeline receipt."""
    op = getattr(ctx, "op", ctx)
    route_context = getattr(op, "route_context", {})
    route_context = route_context if isinstance(route_context, Mapping) else {}
    signal_snapshot = route_context.get("signal_snapshot")
    signal_snapshot = signal_snapshot if isinstance(signal_snapshot, Mapping) else {}
    canonical_execution = signal_snapshot.get("canonical_execution")
    canonical_execution = (
        canonical_execution if isinstance(canonical_execution, Mapping) else {}
    )
    evidence_bundle = signal_snapshot.get("capability_evidence_bundle")
    evidence_bundle = evidence_bundle if isinstance(evidence_bundle, Mapping) else {}
    task_id = str(getattr(op, "task_id", "") or getattr(op, "instance_id", ""))
    source_root = str(route_context.get("world_c_source_root") or "")
    workspace_path = str(
        route_context.get("world_c_workspace_path") or getattr(op, "repo_dir", "") or ""
    )
    workspace_isolated = bool(
        source_root
        and workspace_path
        and Path(source_root).expanduser().resolve()
        != Path(workspace_path).expanduser().resolve()
    )
    workspace_exists = bool(workspace_path and Path(workspace_path).is_dir())
    raw_attempts = getattr(op, "_world_c_phase_attempts", [])
    attempts = [dict(item) for item in raw_attempts if isinstance(item, Mapping)]

    stages: list[dict[str, Any]] = []
    for stage_name in WORLD_C_STAGES:
        stage_attempts = [item for item in attempts if item.get("stage") == stage_name]
        completed = any(
            item.get("success") is True and item.get("output_evidence_present") is True
            for item in stage_attempts
        )
        final_success = bool(
            stage_attempts
            and stage_attempts[-1].get("success") is True
            and stage_attempts[-1].get("output_evidence_present") is True
        )
        stages.append(
            {
                "name": stage_name,
                "invoked": bool(stage_attempts),
                "completed": completed,
                "final_success": final_success,
                "attempt_count": len(stage_attempts),
                "attempts": stage_attempts,
                "evidence_refs": [
                    str(item.get("evidence_hash"))
                    for item in stage_attempts
                    if item.get("evidence_hash")
                ],
            }
        )

    all_completed = all(stage["completed"] for stage in stages)
    verifier_stage = stages[-1]
    receipt: dict[str, Any] = {
        "schema": WORLD_C_RECEIPT_SCHEMA,
        "task_id": task_id,
        "world": "C",
        "pipeline": "HealOrchestrator",
        "execution_topology": str(
            signal_snapshot.get("executor_topology") or "localheal_pipeline"
        ),
        "execution_world": str(signal_snapshot.get("execution_world") or ""),
        "canonical_execution_topology": str(
            signal_snapshot.get("canonical_execution_topology") or ""
        ),
        "canonical_execution_hash": str(
            canonical_execution.get("context_hash") or ""
        ),
        "source_hash": str(evidence_bundle.get("source_hash") or ""),
        "planner_decision_id": str(
            signal_snapshot.get("planner_decision_id")
            or route_context.get("planner_decision_id")
            or ""
        ),
        "source_root": source_root,
        "workspace_path": workspace_path,
        "workspace_isolated": workspace_isolated,
        "workspace_exists": workspace_exists,
        "stages": stages,
        "stage_order": list(WORLD_C_STAGES),
        "authoritative_verifier": {
            "source": "HealOrchestrator.VerificationPhase",
            "invoked": verifier_stage["invoked"],
            "gate_passed": verifier_stage["final_success"],
            "evidence_refs": list(verifier_stage["evidence_refs"]),
        },
        "receipt_complete": bool(all_completed and verifier_stage["final_success"]),
        "public_claim_allowed": False,
    }
    receipt["receipt_hash"] = _sha256_json(receipt)
    return receipt


def validate_world_c_receipt(receipt: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    """Validate structure, stage truth and self-hash without inferring evidence."""
    data = dict(receipt) if isinstance(receipt, Mapping) else {}
    reasons: list[str] = []
    if data.get("schema") != WORLD_C_RECEIPT_SCHEMA:
        reasons.append("unsupported_schema")
    if not str(data.get("task_id") or ""):
        reasons.append("task_id_missing")
    if not str(data.get("planner_decision_id") or ""):
        reasons.append("planner_decision_id_missing")
    canonical_values = (
        str(data.get("execution_world") or ""),
        str(data.get("canonical_execution_topology") or ""),
        str(data.get("canonical_execution_hash") or ""),
    )
    if any(canonical_values):
        if canonical_values[0] != "local_armor":
            reasons.append("canonical_execution_world_mismatch")
        if canonical_values[1] not in {
            "DIRECT_CANONICAL",
            "ISOLATED_TARGET",
            "ASSISTED_CANONICAL",
        }:
            reasons.append("canonical_execution_topology_invalid")
        if len(canonical_values[2]) != 64 or any(
            char not in "0123456789abcdef" for char in canonical_values[2]
        ):
            reasons.append("canonical_execution_hash_invalid")
        if not str(data.get("source_hash") or ""):
            reasons.append("canonical_source_hash_missing")
    if data.get("workspace_isolated") is not True:
        reasons.append("workspace_not_isolated")
    if data.get("workspace_exists") is not True:
        reasons.append("workspace_missing")
    stages = data.get("stages")
    if not isinstance(stages, list):
        stages = []
        reasons.append("stages_missing")
    names = [str(stage.get("name") or "") for stage in stages if isinstance(stage, Mapping)]
    if names != list(WORLD_C_STAGES):
        reasons.append("stage_order_mismatch")
    for expected, stage in zip(WORLD_C_STAGES, stages):
        if not isinstance(stage, Mapping) or stage.get("name") != expected:
            continue
        if not stage.get("invoked"):
            reasons.append(f"{expected}_not_invoked")
        if not stage.get("completed"):
            reasons.append(f"{expected}_not_completed")
        refs = stage.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            reasons.append(f"{expected}_evidence_missing")
        attempts = stage.get("attempts")
        if not isinstance(attempts, list) or not any(
            isinstance(attempt, Mapping)
            and attempt.get("success") is True
            and attempt.get("output_evidence_present") is True
            and bool(attempt.get("output_evidence_hash"))
            for attempt in attempts
        ):
            reasons.append(f"{expected}_output_evidence_missing")
    verifier = data.get("authoritative_verifier")
    if not isinstance(verifier, Mapping) or verifier.get("gate_passed") is not True:
        reasons.append("authoritative_verifier_not_passed")
    claimed_hash = str(data.get("receipt_hash") or "")
    hash_payload = dict(data)
    hash_payload.pop("receipt_hash", None)
    if not claimed_hash or claimed_hash != _sha256_json(hash_payload):
        reasons.append("receipt_hash_mismatch")
    if reasons and data.get("receipt_complete") is True:
        reasons.append("false_complete_claim")
    if not reasons and data.get("receipt_complete") is not True:
        reasons.append("receipt_not_complete")
    return not reasons, reasons
