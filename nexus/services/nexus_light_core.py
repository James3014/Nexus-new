"""Governed Light Route Core (Nexus Light) — Low-risk deterministic execution path.

This module resolves the missing `nexus.services.nexus_light_core` seam in `UnifiedRuntime`.
It provides deterministic capability invokers and light route governance without creating
a parallel router or planner. CapabilityPlanner remains the sole selection authority,
and UnifiedRuntime remains the sole lifecycle/receipt authority.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

CapabilityInvoker = Callable[[Mapping[str, Any]], Mapping[str, Any]]

# Deterministic capabilities supported on the governed light route
LIGHT_DETERMINISTIC_CAPABILITIES: frozenset[str] = frozenset({
    "acceptance_check",
    "architecture_scout",
    "artifact_gate",
    "asi_constraint_extractor",
    "bdd_acceptance_skill",
    "belief",
    "benchmark",
    "claim_gate",
    "codeintel",
    "delivery_gate",
    "drone",
    "file_lock",
    "forecast_gate",
    "formal_report",
    "harness_preflight_sensor",
    "jit_validation",
    "lancedb",
    "learn_mode",
    "learn_phase_slo",
    "memory",
    "mempalace_gate",
    "meta_opt",
    "plan_quality_gate",
    "pregate",
    "research",
    "sandbox",
    "semantic_failure_sensor",
    "semantic_searcher",
    "stress_test",
    "ultra_review",
    "xray",
})


def classify_light_route(
    task_statement: str,
    route: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Classify whether a task qualifies for the governed light route.

    Returns (is_light, classification_reason).
    Boundary violation (e.g. asking for generative repair, full model synthesis)
    requires escalation to Local/Online lanes.
    """
    route_map = dict(route or {})
    if bool(route_map.get("nexus_light") or route_map.get("deterministic_core")):
        return True, "explicit_opt_in_nexus_light"

    statement_lower = str(task_statement or "").lower()
    heavy_keywords = {"repair", "fix bug", "generate patch", "complex refactor", "synthesis"}
    if any(kw in statement_lower for kw in heavy_keywords):
        return False, "requires_generative_model_repair_lane"

    light_keywords = {"check", "lint", "inspect", "audit", "pregate", "verify", "scan", "status"}
    if any(kw in statement_lower for kw in light_keywords):
        return True, "deterministic_inspection_task"

    return True, "default_governed_light_candidate"


def build_nexus_light_capability_invokers(
    workspace_root: str = ".",
    compression: bool = False,
) -> dict[str, CapabilityInvoker]:
    """Build deterministic capability invokers for the governed light route.

    Invokers perform pure Python/tool/sensor operations with zero LLM provider calls.
    Uses `CapabilityRegistry` as the single underlying capability authority.
    """
    from nexus.services.capability_registry import build_default_mainchain_invokers

    workspace = str(Path(workspace_root).resolve())
    codeintel_context = {"workspace_root": workspace}

    # Fetch default mainchain invokers from authority
    base_invokers = build_default_mainchain_invokers(
        codeintel=codeintel_context,
        include_postflight_gates=True,
    )

    def _wrap_optional_sensor(name: str, invoker: CapabilityInvoker) -> CapabilityInvoker:
        def _wrapped(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
            res = invoker(ctx)
            if isinstance(res, Mapping):
                resp = res.get("response")
                if isinstance(resp, Mapping):
                    outcome = resp.get("outcome")
                    if isinstance(outcome, Mapping) and outcome.get("semantic_status") == "BLOCKED":
                        err = str(outcome.get("error") or "")
                        if err in {"EXPLICIT_VERIFY_COMMANDS_REQUIRED", "MEMPALACE_ARTIFACT_CONTEXT_REQUIRED"}:
                            task_id = str(ctx.get("task_id") or "")
                            return {
                                "task_id": task_id,
                                "invoked": True,
                                "skipped": True,
                                "skip_reason": f"nexus_light_sensor_optional:{err}",
                                "gate_passed": True,
                                "status": "SKIPPED",
                                "evidence_refs": [f"capability:{name}:{task_id}:nexus_light_skipped"],
                            }
            return res
        return _wrapped

    light_invokers: dict[str, CapabilityInvoker] = {}
    for cap_name in LIGHT_DETERMINISTIC_CAPABILITIES:
        if cap_name in base_invokers:
            if cap_name in {"harness_preflight_sensor", "mempalace_gate"}:
                light_invokers[cap_name] = _wrap_optional_sensor(cap_name, base_invokers[cap_name])
            else:
                light_invokers[cap_name] = base_invokers[cap_name]

    if compression:
        from nexus.services.unified_runtime import build_prompt_compression_capability_invoker
        light_invokers["prompt_compression"] = build_prompt_compression_capability_invoker()

    return light_invokers


def build_nexus_light_verifier(context: Mapping[str, Any]) -> dict[str, Any]:
    """Default proportional verifier for the governed light route."""
    task_id = str(context.get("task_id") or "")
    workspace_revision = str(context.get("workspace_revision") or "")
    task_statement = str(context.get("task_statement") or "")
    source_raw = f"{workspace_revision}:{task_statement}".encode("utf-8")
    source_hash = hashlib.sha256(source_raw).hexdigest()

    cap_results = context.get("capability_results") or {}
    has_failed_light = False
    if isinstance(cap_results, Mapping):
        for name, res in cap_results.items():
            if name in {"codeintel", "prompt_compression", "pregate"} and isinstance(res, Mapping):
                st = str(res.get("status", "")).upper()
                if st in {"FAILED", "BLOCKED"}:
                    has_failed_light = True
                    break

    all_passed = not has_failed_light

    proof_bytes = f"nexus_light_verifier:{task_id}:{source_hash}:{all_passed}".encode("utf-8")
    art_hash = hashlib.sha256(proof_bytes).hexdigest()

    return {
        "task_id": task_id,
        "verifier_task_id": task_id,
        "invoked": True,
        "evidence_present": True,
        "evidence_refs": [f"verifier:nexus_light:{task_id}"],
        "gate_passed": all_passed,
        "status": "SUCCEEDED" if all_passed else "FAILED",
        "verifier_status": "pass" if all_passed else "fail",
        "verifier_artifact": f"sha256:{art_hash}",
        "source_hash": source_hash,
        "verifier_source_hash": source_hash,
    }


def build_nexus_light_learning(context: Mapping[str, Any]) -> dict[str, Any]:
    """Default proportional learning stage for the governed light route."""
    task_id = str(context.get("task_id") or "")
    return {
        "task_id": task_id,
        "invoked": True,
        "evidence_present": True,
        "evidence_refs": [f"learning:nexus_light:{task_id}"],
        "gate_passed": True,
        "status": "SUCCEEDED",
        "learning_result": "minimal_light_route_learning_complete",
    }


def create_light_route_receipt(
    task_id: str,
    planner_decision_id: str,
    selected_capabilities: list[str],
    invoked_capabilities: list[str],
    skipped_stages: dict[str, str],
    gate_passed: bool,
    observable_effect: dict[str, Any],
) -> dict[str, Any]:
    """Build minimal reproducible receipt for governed light route execution."""
    receipt_payload = {
        "schema": "nexus.governed_light_route_receipt.v1",
        "task_id": task_id,
        "planner_decision_id": planner_decision_id,
        "route_classification": "nexus_light",
        "provider_calls": 0,
        "selected_capabilities": list(selected_capabilities),
        "invoked_capabilities": list(invoked_capabilities),
        "skipped_stages": dict(skipped_stages),
        "gate_passed": bool(gate_passed),
        "observable_effect": dict(observable_effect),
        "receipt_complete": True,
        "public_claim_allowed": False,
    }

    raw = json.dumps(receipt_payload, sort_keys=True, separators=(",", ":"))
    receipt_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    receipt_payload["receipt_hash"] = receipt_hash
    return receipt_payload
