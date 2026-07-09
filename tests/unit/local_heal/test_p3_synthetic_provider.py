from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_synthetic_provider import (
    P3SyntheticProviderRequest,
    P3SyntheticProviderResponse,
    compute_synthetic_provider_request,
    process_synthetic_provider_request,
    p3_synthetic_request_to_dict,
    p3_synthetic_response_to_dict,
    _compute_synthetic_candidate_id,
)


# ============================================================
# P3-N2-1: valid request produces deterministic synthetic candidate
# ============================================================


def test_valid_request_produces_synthetic_candidate():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
        allow_synthetic_candidate=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.request_accepted is True
    assert resp.synthetic_provider_invoked is True
    assert resp.candidate_is_synthetic is True
    assert resp.synthetic_candidate_id != ""


# ============================================================
# P3-N2-2: same input produces same synthetic_candidate_id
# ============================================================


def test_same_input_produces_same_id():
    id1 = _compute_synthetic_candidate_id("fixture1", "hash1")
    id2 = _compute_synthetic_candidate_id("fixture1", "hash1")
    assert id1 == id2


# ============================================================
# P3-N2-3: missing env guard blocks
# ============================================================


def test_missing_env_guard_blocks():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=False,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.request_accepted is False
    assert resp.synthetic_provider_invoked is False
    assert "env_guard_missing" in resp.blocked_reasons


# ============================================================
# P3-N2-4: missing prompt hash blocks
# ============================================================


def test_missing_prompt_hash_blocks():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.request_accepted is False
    assert "compact_prompt_hash_missing" in resp.blocked_reasons


# ============================================================
# P3-N2-5: dry_run_only=false blocks
# ============================================================


def test_dry_run_false_blocks():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
        dry_run_only=False,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.request_accepted is False
    assert "non_dry_run_blocked" in resp.blocked_reasons


# ============================================================
# P3-N2-6: allow_synthetic_candidate=false blocks
# ============================================================


def test_allow_synthetic_false_blocks():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
        allow_synthetic_candidate=False,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.request_accepted is False
    assert "synthetic_candidate_not_allowed" in resp.blocked_reasons


# ============================================================
# P3-N2-7: real_provider_invoked=false always
# ============================================================


def test_real_provider_invoked_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.real_provider_invoked is False


# ============================================================
# P3-N2-8: network_invoked=false always
# ============================================================


def test_network_invoked_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.network_invoked is False


# ============================================================
# P3-N2-9: api_key_used=false always
# ============================================================


def test_api_key_used_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.api_key_used is False


# ============================================================
# P3-N2-10: patch_apply_invoked=false always
# ============================================================


def test_patch_apply_invoked_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.patch_apply_invoked is False


# ============================================================
# P3-N2-11: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.runtime_behavior_changed is False


# ============================================================
# P3-N2-12: claim_eligible=false always
# ============================================================


def test_claim_eligible_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.claim_eligible is False


# ============================================================
# P3-N2-13: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.public_claim_allowed is False


# ============================================================
# P3-N2-14: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    assert resp.production_ready is False


# ============================================================
# P3-N2-15: JSON serialization works
# ============================================================


def test_json_serializable():
    req = compute_synthetic_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
    )
    resp = process_synthetic_provider_request(req)
    req_d = p3_synthetic_request_to_dict(req)
    resp_d = p3_synthetic_response_to_dict(resp)
    assert isinstance(json.dumps(req_d), str)
    assert isinstance(json.dumps(resp_d), str)


# ============================================================
# P3-N2-16: module imports no cloud SDKs and no network clients
# ============================================================


def test_no_cloud_sdk_imports():
    import nexus.services.local_heal.p3_synthetic_provider as mod
    source = open(mod.__file__).read()
    assert "openai" not in source.lower()
    assert "anthropic" not in source.lower()
    assert "google.cloud" not in source.lower()
    assert "requests" not in source.lower()
    assert "httpx" not in source.lower()
    assert "aiohttp" not in source.lower()
