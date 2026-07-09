from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_route_provider_adapter import (
    P3RouteProviderAdapterResult,
    compute_route_provider_adapter,
    p3_adapter_to_dict,
)


# ============================================================
# P3-K4-1: local_only does not build provider request
# ============================================================


def test_local_only_no_request():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "local_only", "p3_task_difficulty": "easy"},
    )
    assert result.request_built is False
    assert result.provider_request is None
    assert "topology_local_only_no_provider_needed" in result.blocked_reasons


# ============================================================
# P3-K4-2: medium cloud_with_local_assist builds dry-run request
# ============================================================


def test_medium_cloud_builds_request():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        guard_state="shadow_only",
    )
    assert result.request_built is True
    assert result.provider_request is not None
    assert result.provider_request.dry_run is True
    assert result.provider_response is not None
    assert result.provider_response.provider_invoked is False


# ============================================================
# P3-K4-3: hard cloud_with_local_assist builds dry-run request
# ============================================================


def test_hard_cloud_builds_request():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "hard"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "def456"},
    )
    assert result.request_built is True
    assert result.provider_request.dry_run is True


# ============================================================
# P3-K4-4: missing env guard blocks
# ============================================================


def test_missing_env_guard_blocks():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        guard_state="shadow_only",
        env_guard_override=False,
    )
    assert result.env_guard_present is False
    assert any("env_guard_missing" in r for r in result.blocked_reasons)


# ============================================================
# P3-K4-5: missing compact prompt hash blocks
# ============================================================


def test_missing_prompt_hash_blocks():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": ""},
    )
    assert any("compact_prompt_hash_missing" in r for r in result.blocked_reasons)


# ============================================================
# P3-K4-6: provider_invoked=false always
# ============================================================


def test_provider_invoked_always_false():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
    )
    assert result.provider_invoked is False


# ============================================================
# P3-K4-7: network_invoked=false always
# ============================================================


def test_network_invoked_always_false():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
    )
    assert result.network_invoked is False


# ============================================================
# P3-K4-8: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
    )
    assert result.runtime_behavior_changed is False


# ============================================================
# P3-K4-9: full_verifier_required=true
# ============================================================


def test_full_verifier_required_true():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
    )
    assert result.full_verifier_required is True


# ============================================================
# P3-K4-10: claim_gate_required=true
# ============================================================


def test_claim_gate_required_true():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
    )
    assert result.claim_gate_required is True


# ============================================================
# P3-K4-11: public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_false():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
    )
    assert result.public_claim_allowed is False


# ============================================================
# P3-K4-12: result JSON serializable
# ============================================================


def test_result_json_serializable():
    result = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
    )
    d = p3_adapter_to_dict(result)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)


# ============================================================
# P3-K4-13: no router import required
# ============================================================


def test_no_router_import():
    import nexus.services.local_heal.p3_route_provider_adapter as mod
    source = open(mod.__file__).read()
    assert "nexus.core.router" not in source


# ============================================================
# P3-K4-14: no capability_planner import required
# ============================================================


def test_no_capability_planner_import():
    import nexus.services.local_heal.p3_route_provider_adapter as mod
    source = open(mod.__file__).read()
    assert "capability_planner" not in source


# ============================================================
# P3-K4-15: no P6 runtime hook import required
# ============================================================


def test_no_p6_import():
    import nexus.services.local_heal.p3_route_provider_adapter as mod
    source = open(mod.__file__).read()
    assert "p6_runtime_hook" not in source
