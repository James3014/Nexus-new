from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p3_runtime_guard import compute_p3_runtime_guard
from nexus.services.local_heal.p3_route_provider_adapter import compute_route_provider_adapter
from nexus.services.local_heal.p3_synthetic_provider_adapter import compute_synthetic_provider_adapter
from nexus.services.local_heal.p3_synthetic_provider_receipt import compute_synthetic_provider_receipt, p3_synthetic_receipt_to_dict
from nexus.services.local_heal.p3_dry_run_schema import validate_p3_dry_run_schema
from nexus.services.local_heal.p3_dry_run_invariants import validate_p3_dry_run_receipt


@dataclass(frozen=True)
class P3SyntheticE2ETraceResult:
    """P3-O2: Synthetic end-to-end trace result.

    Runs complete dry-run provider seam:
    runtime guard → route-provider adapter → synthetic provider adapter → receipt → schema → invariants.
    """
    trace_version: str
    scenario_id: str
    runtime_state: str
    env_guard_present: bool
    intended_topology: str
    task_difficulty: str
    compact_prompt_hash_present: bool
    route_provider_request_built: bool
    synthetic_fixture_enabled: bool
    synthetic_provider_invoked: bool
    real_provider_invoked: bool
    network_invoked: bool
    api_key_used: bool
    candidate_is_synthetic: bool
    canonical_candidate_available: bool
    synthetic_candidate_id: str
    synthetic_raw_output_hash: str
    patch_apply_invoked: bool
    runtime_behavior_changed: bool
    strict_schema_passed: bool
    invariant_passed: bool
    full_verifier_required: bool
    claim_gate_required: bool
    claim_eligible: bool
    public_claim_allowed: bool
    production_ready: bool
    blocked_reasons: list[str] = field(default_factory=list)


def compute_synthetic_e2e_trace(
    scenario_id: str,
    *,
    env_flag_enabled: bool = False,
    task_difficulty: str = "medium",
    intended_topology: str = "cloud_with_local_assist",
    compact_prompt_ready: bool = True,
    synthetic_fixture_enabled: bool = True,
    is_unsafe: bool = False,
    unsafe_field: str = "",
) -> P3SyntheticE2ETraceResult:
    """Compute synthetic E2E trace result.

    Runs full provider seam without real provider/network/API key.
    """
    guard_state = "env_guarded_dry_run" if env_flag_enabled else "shadow_only"
    guard = compute_p3_runtime_guard(requested_state=guard_state, env_guard_override=env_flag_enabled)

    prompt_hash = "abc123" if compact_prompt_ready else ""

    route_adapter = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": intended_topology, "p3_task_difficulty": task_difficulty},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": prompt_hash} if prompt_hash else None,
        guard_state=guard.runtime_state,
        env_guard_override=env_flag_enabled,
    )

    synthetic_adapter = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": intended_topology, "p3_task_difficulty": task_difficulty},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": prompt_hash} if prompt_hash else None,
        synthetic_fixture_enabled=synthetic_fixture_enabled,
    )

    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": intended_topology, "p3_task_difficulty": task_difficulty},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": prompt_hash} if prompt_hash else None,
        synthetic_fixture_enabled=synthetic_fixture_enabled,
    )

    receipt_dict = p3_synthetic_receipt_to_dict(receipt)
    if is_unsafe and unsafe_field and unsafe_field in receipt_dict:
        if unsafe_field in ("p3_n_full_verifier_required", "p3_n_claim_gate_required"):
            receipt_dict[unsafe_field] = False
        else:
            receipt_dict[unsafe_field] = True

    schema_result = validate_p3_dry_run_schema(receipt_dict)

    synthetic_invariant_passed = (
        not receipt_dict.get("p3_n_real_provider_invoked", False)
        and not receipt_dict.get("p3_n_network_invoked", False)
        and not receipt_dict.get("p3_n_api_key_used", False)
        and not receipt_dict.get("p3_n_patch_apply_invoked", False)
        and not receipt_dict.get("p3_n_runtime_behavior_changed", False)
        and receipt_dict.get("p3_n_full_verifier_required", True)
        and receipt_dict.get("p3_n_claim_gate_required", True)
        and not receipt_dict.get("p3_n_claim_eligible", False)
        and not receipt_dict.get("p3_n_public_claim_allowed", False)
        and not receipt_dict.get("p3_n_production_ready", False)
    )

    blocked_reasons = list(synthetic_adapter.blocked_reasons)

    return P3SyntheticE2ETraceResult(
        trace_version="1.0",
        scenario_id=scenario_id,
        runtime_state=guard.runtime_state,
        env_guard_present=guard.env_guard_present,
        intended_topology=intended_topology,
        task_difficulty=task_difficulty,
        compact_prompt_hash_present=bool(prompt_hash),
        route_provider_request_built=route_adapter.request_built,
        synthetic_fixture_enabled=synthetic_fixture_enabled,
        synthetic_provider_invoked=synthetic_adapter.synthetic_provider_invoked,
        real_provider_invoked=False,
        network_invoked=False,
        api_key_used=False,
        candidate_is_synthetic=synthetic_adapter.candidate_is_synthetic,
        canonical_candidate_available=synthetic_adapter.candidate_is_synthetic,
        synthetic_candidate_id=synthetic_adapter.synthetic_candidate_id,
        synthetic_raw_output_hash=synthetic_adapter.synthetic_raw_output_hash,
        patch_apply_invoked=False,
        runtime_behavior_changed=False,
        strict_schema_passed=schema_result.schema_passed,
        invariant_passed=synthetic_invariant_passed,
        full_verifier_required=True,
        claim_gate_required=True,
        claim_eligible=False,
        public_claim_allowed=False,
        production_ready=False,
        blocked_reasons=blocked_reasons,
    )


def p3_synthetic_e2e_trace_to_dict(trace: P3SyntheticE2ETraceResult) -> dict[str, Any]:
    """Convert P3SyntheticE2ETraceResult to JSON-serializable dict."""
    return {
        "p3_trace_version": trace.trace_version,
        "p3_trace_scenario_id": trace.scenario_id,
        "p3_trace_runtime_state": trace.runtime_state,
        "p3_trace_env_guard_present": trace.env_guard_present,
        "p3_trace_intended_topology": trace.intended_topology,
        "p3_trace_task_difficulty": trace.task_difficulty,
        "p3_trace_compact_prompt_hash_present": trace.compact_prompt_hash_present,
        "p3_trace_route_provider_request_built": trace.route_provider_request_built,
        "p3_trace_synthetic_fixture_enabled": trace.synthetic_fixture_enabled,
        "p3_trace_synthetic_provider_invoked": trace.synthetic_provider_invoked,
        "p3_trace_real_provider_invoked": trace.real_provider_invoked,
        "p3_trace_network_invoked": trace.network_invoked,
        "p3_trace_api_key_used": trace.api_key_used,
        "p3_trace_candidate_is_synthetic": trace.candidate_is_synthetic,
        "p3_trace_canonical_candidate_available": trace.canonical_candidate_available,
        "p3_trace_synthetic_candidate_id": trace.synthetic_candidate_id,
        "p3_trace_synthetic_raw_output_hash": trace.synthetic_raw_output_hash,
        "p3_trace_patch_apply_invoked": trace.patch_apply_invoked,
        "p3_trace_runtime_behavior_changed": trace.runtime_behavior_changed,
        "p3_trace_strict_schema_passed": trace.strict_schema_passed,
        "p3_trace_invariant_passed": trace.invariant_passed,
        "p3_trace_full_verifier_required": trace.full_verifier_required,
        "p3_trace_claim_gate_required": trace.claim_gate_required,
        "p3_trace_claim_eligible": trace.claim_eligible,
        "p3_trace_public_claim_allowed": trace.public_claim_allowed,
        "p3_trace_production_ready": trace.production_ready,
        "p3_trace_blocked_reasons": trace.blocked_reasons,
    }
