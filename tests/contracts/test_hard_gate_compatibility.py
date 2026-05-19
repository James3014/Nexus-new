from __future__ import annotations

from nexus.contracts.hard_gate_compatibility import (
    HARD_GATE_COMPATIBILITY_SCHEMA,
    build_hard_gate_compatibility,
    validate_hard_gate_compatibility,
)


def test_hard_gate_compatibility_passes_clean_g0_bundle() -> None:
    payload = build_hard_gate_compatibility(
        route_context_changed=True,
        route_hardened=True,
        mfp_confidence_min=0.98,
        router_acceptance_status="PASS",
        closeout_claim=True,
        completion_status="PASS",
        context_sources_dropped=True,
        hallucination_guard_status="PASS",
        mutation_assurance_required=True,
        mutation_assurance_status="PASS",
        bdd_acceptance_required=True,
        bdd_preflight_status="PASS",
        capability_contract_type="cost_capped",
        pre_model_rescue_planned=True,
        skill_tier_status="PASS",
        quarantined_skill_detected=False,
        research_supply_gap=True,
        live_benchmark_requested=False,
        forced_swarm=True,
        parallel_slot_planned=False,
        evidence_refs=("route:dry-run", "completion:envelope", "mutation:claim_always_true"),
    )

    assert payload["schema"] == HARD_GATE_COMPATIBILITY_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["blockers"] == []


def test_hard_gate_compatibility_blocks_missing_required_gates() -> None:
    payload = build_hard_gate_compatibility(
        route_context_changed=True,
        route_hardened=False,
        router_acceptance_status="RETURN",
        closeout_claim=True,
        completion_status="RETURN",
        context_sources_dropped=True,
        hallucination_guard_status="RETURN",
        mutation_assurance_required=True,
        mutation_assurance_status="FAIL",
        bdd_acceptance_required=True,
        bdd_preflight_status="RETURN",
        capability_contract_type="required",
        pre_model_rescue_planned=True,
        skill_tier_status="RETURN",
        quarantined_skill_detected=True,
        research_supply_gap=True,
        live_benchmark_requested=True,
        forced_swarm=True,
        parallel_slot_planned=True,
    )

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == [
        "bdd_preflight_not_pass",
        "completion_envelope_not_pass",
        "forced_swarm_must_be_serialized",
        "hallucination_guard_not_pass",
        "hardened_router_not_enabled",
        "mutation_assurance_not_pass",
        "quarantined_skill_detected",
        "required_capability_pre_model_rescue_planned",
        "research_supply_gap_blocks_live_benchmark",
        "router_acceptance_not_pass",
        "skill_tier_status_not_pass",
    ]


def test_hard_gate_compatibility_validator_rejects_unlock_attempts() -> None:
    blockers = validate_hard_gate_compatibility(
        {
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
        }
    )

    assert blockers == [
        "compatibility_contract_must_not_unlock_public_benchmark",
        "compatibility_contract_must_not_update_runtime",
    ]


def test_hard_gate_compatibility_blocks_execution_hygiene_gaps() -> None:
    payload = build_hard_gate_compatibility(
        jit_symbol_drift_detected=True,
        ast_graph_freshness_status="RETURN",
        phase_token_sentinel_status="RETURN",
        retry_pollution_detected=True,
        retry_pollution_isolated=False,
        memory_sanitizer_status="RETURN",
        private_leak_detected=True,
        dirty_worktree=True,
        spec_kit_init_requested=True,
        transient_output_root_status="RETURN",
    )

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == [
        "ast_graph_not_fresh",
        "dirty_worktree_blocks_spec_kit",
        "memory_sanitizer_not_pass",
        "phase_token_sentinel_not_pass",
        "private_leak_detected",
        "retry_pollution_not_isolated",
        "transient_output_root_not_pass",
    ]
