from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_synthetic_provider_adapter import (
    P3SyntheticProviderAdapterResult,
    compute_synthetic_provider_adapter,
    p3_synthetic_adapter_to_dict,
)


# ============================================================
# P3-N3-1: disabled fixture does not invoke synthetic provider
# ============================================================


def test_disabled_fixture_no_invoke():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        synthetic_fixture_enabled=False,
    )
    assert result.synthetic_request_built is False
    assert result.synthetic_provider_invoked is False
    assert "synthetic_fixture_disabled" in result.blocked_reasons


# ============================================================
# P3-N3-2: enabled fixture with valid metadata invokes synthetic provider
# ============================================================


def test_enabled_fixture_invokes():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        synthetic_fixture_enabled=True,
    )
    assert result.synthetic_request_built is True
    assert result.synthetic_provider_invoked is True
    assert result.candidate_is_synthetic is True
    assert result.synthetic_candidate_id != ""


# ============================================================
# P3-N3-3: candidate id deterministic
# ============================================================


def test_candidate_id_deterministic():
    r1 = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        synthetic_fixture_enabled=True,
    )
    r2 = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        synthetic_fixture_enabled=True,
    )
    assert r1.synthetic_candidate_id == r2.synthetic_candidate_id


# ============================================================
# P3-N3-4: missing env guard blocks
# ============================================================


def test_missing_env_guard_blocks():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": ""},
        synthetic_fixture_enabled=True,
    )
    assert any("compact_prompt_hash_missing" in r for r in result.blocked_reasons)


# ============================================================
# P3-N3-5: missing compact prompt hash blocks
# ============================================================


def test_missing_prompt_hash_blocks():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": ""},
        synthetic_fixture_enabled=True,
    )
    assert any("compact_prompt_hash_missing" in r for r in result.blocked_reasons)


# ============================================================
# P3-N3-6: local_only does not invoke synthetic provider
# ============================================================


def test_local_only_no_invoke():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "local_only", "p3_task_difficulty": "easy"},
        synthetic_fixture_enabled=True,
    )
    assert result.synthetic_request_built is False
    assert "topology_local_only_no_provider_needed" in result.blocked_reasons


# ============================================================
# P3-N3-7: real_provider_invoked=false always
# ============================================================


def test_real_provider_invoked_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.real_provider_invoked is False


# ============================================================
# P3-N3-8: network_invoked=false always
# ============================================================


def test_network_invoked_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.network_invoked is False


# ============================================================
# P3-N3-9: api_key_used=false always
# ============================================================


def test_api_key_used_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.api_key_used is False


# ============================================================
# P3-N3-10: patch_apply_invoked=false always
# ============================================================


def test_patch_apply_invoked_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.patch_apply_invoked is False


# ============================================================
# P3-N3-11: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.runtime_behavior_changed is False


# ============================================================
# P3-N3-12: claim_eligible=false always
# ============================================================


def test_claim_eligible_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.claim_eligible is False


# ============================================================
# P3-N3-13: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.public_claim_allowed is False


# ============================================================
# P3-N3-14: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert result.production_ready is False


# ============================================================
# P3-N3-15: JSON serialization works
# ============================================================


def test_json_serializable():
    result = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    d = p3_synthetic_adapter_to_dict(result)
    assert isinstance(json.dumps(d), str)


# ============================================================
# P3-N3-16: no cloud SDK/network imports
# ============================================================


def test_no_cloud_sdk_imports():
    import nexus.services.local_heal.p3_synthetic_provider_adapter as mod
    source = open(mod.__file__).read()
    assert "import openai" not in source
    assert "import anthropic" not in source
    assert "import requests" not in source
    assert "import httpx" not in source
    assert "import aiohttp" not in source
