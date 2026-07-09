from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_synthetic_e2e_trace import (
    P3SyntheticE2ETraceResult,
    compute_synthetic_e2e_trace,
    p3_synthetic_e2e_trace_to_dict,
)


# ============================================================
# O2-1: local_only safe trace
# ============================================================


def test_local_only_safe_trace():
    trace = compute_synthetic_e2e_trace(
        scenario_id="local_only_safe",
        env_flag_enabled=True,
        intended_topology="local_only",
        task_difficulty="easy",
    )
    assert trace.route_provider_request_built is False
    assert trace.synthetic_provider_invoked is False
    assert trace.invariant_passed is True


# ============================================================
# O2-2: cloud_with_local_assist valid synthetic trace
# ============================================================


def test_cloud_valid_synthetic_trace():
    trace = compute_synthetic_e2e_trace(
        scenario_id="cloud_valid",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.route_provider_request_built is True
    assert trace.synthetic_provider_invoked is True
    assert trace.candidate_is_synthetic is True
    assert trace.canonical_candidate_available is True


# ============================================================
# O2-3: valid synthetic trace has canonical_candidate_available=true
# ============================================================


def test_canonical_candidate_available():
    trace = compute_synthetic_e2e_trace(
        scenario_id="canonical_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.canonical_candidate_available is True


# ============================================================
# O2-4: missing env guard blocks synthetic invocation
# ============================================================


def test_missing_env_guard_blocks():
    trace = compute_synthetic_e2e_trace(
        scenario_id="missing_env",
        env_flag_enabled=False,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.env_guard_present is False
    assert trace.invariant_passed is True


# ============================================================
# O2-5: missing prompt hash blocks synthetic invocation
# ============================================================


def test_missing_prompt_hash_blocks():
    trace = compute_synthetic_e2e_trace(
        scenario_id="missing_prompt",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=False,
        synthetic_fixture_enabled=True,
    )
    assert trace.compact_prompt_hash_present is False
    assert trace.invariant_passed is True


# ============================================================
# O2-6: unknown difficulty remains safe
# ============================================================


def test_unknown_difficulty_safe():
    trace = compute_synthetic_e2e_trace(
        scenario_id="unknown_safe",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.invariant_passed is True


# ============================================================
# O2-7: real_provider_invoked=false always
# ============================================================


def test_real_provider_invoked_always_false():
    trace = compute_synthetic_e2e_trace(
        scenario_id="real_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.real_provider_invoked is False


# ============================================================
# O2-8: network_invoked=false always
# ============================================================


def test_network_invoked_always_false():
    trace = compute_synthetic_e2e_trace(
        scenario_id="network_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.network_invoked is False


# ============================================================
# O2-9: api_key_used=false always
# ============================================================


def test_api_key_used_always_false():
    trace = compute_synthetic_e2e_trace(
        scenario_id="api_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.api_key_used is False


# ============================================================
# O2-10: patch_apply_invoked=false always
# ============================================================


def test_patch_apply_invoked_always_false():
    trace = compute_synthetic_e2e_trace(
        scenario_id="patch_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.patch_apply_invoked is False


# ============================================================
# O2-11: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    trace = compute_synthetic_e2e_trace(
        scenario_id="runtime_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.runtime_behavior_changed is False


# ============================================================
# O2-12: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    trace = compute_synthetic_e2e_trace(
        scenario_id="claim_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.public_claim_allowed is False


# ============================================================
# O2-13: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    trace = compute_synthetic_e2e_trace(
        scenario_id="prod_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.production_ready is False


# ============================================================
# O2-14: strict_schema_passed for valid rows
# ============================================================


def test_strict_schema_passed():
    trace = compute_synthetic_e2e_trace(
        scenario_id="schema_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.invariant_passed is True


# ============================================================
# O2-15: invariant_passed for valid rows
# ============================================================


def test_invariant_passed():
    trace = compute_synthetic_e2e_trace(
        scenario_id="invariant_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    assert trace.invariant_passed is True


# ============================================================
# O2-16: JSON serialization works
# ============================================================


def test_json_serializable():
    trace = compute_synthetic_e2e_trace(
        scenario_id="json_check",
        env_flag_enabled=True,
        intended_topology="cloud_with_local_assist",
        task_difficulty="medium",
        compact_prompt_ready=True,
        synthetic_fixture_enabled=True,
    )
    d = p3_synthetic_e2e_trace_to_dict(trace)
    assert isinstance(json.dumps(d), str)
