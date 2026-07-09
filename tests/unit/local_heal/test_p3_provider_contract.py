from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_provider_contract import (
    P3ProviderRequest,
    P3ProviderResponse,
    build_p3_provider_request,
    process_p3_provider_request,
    p3_provider_request_to_dict,
    p3_provider_response_to_dict,
)


# ============================================================
# P3-K3-1: Valid dry-run request serializes
# ============================================================


def test_valid_dry_run_request():
    req = build_p3_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
        dry_run=True,
    )
    d = p3_provider_request_to_dict(req)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
    assert req.dry_run is True


# ============================================================
# P3-K3-2: Missing env guard blocks request
# ============================================================


def test_missing_env_guard_blocks():
    req = build_p3_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=False,
    )
    resp = process_p3_provider_request(req)
    assert resp.request_accepted is False
    assert "env_guard_missing" in resp.blocked_reason


# ============================================================
# P3-K3-3: Missing compact_prompt_hash blocks request
# ============================================================


def test_missing_prompt_hash_blocks():
    req = build_p3_provider_request(
        compact_prompt_hash="",
        env_guard_present=True,
    )
    resp = process_p3_provider_request(req)
    assert resp.request_accepted is False
    assert "compact_prompt_hash_missing" in resp.blocked_reason


# ============================================================
# P3-K3-4: non-dry-run blocks by default
# ============================================================


def test_non_dry_run_blocks():
    req = build_p3_provider_request(
        compact_prompt_hash="abc123",
        env_guard_present=True,
        dry_run=False,
    )
    resp = process_p3_provider_request(req)
    assert resp.request_accepted is False
    assert "non_dry_run_blocked" in resp.blocked_reason


# ============================================================
# P3-K3-5: provider_invoked=false always
# ============================================================


def test_provider_invoked_always_false():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.provider_invoked is False


# ============================================================
# P3-K3-6: network_invoked=false always
# ============================================================


def test_network_invoked_always_false():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.network_invoked is False


# ============================================================
# P3-K3-7: api_key_used=false always
# ============================================================


def test_api_key_used_always_false():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.api_key_used is False


# ============================================================
# P3-K3-8: candidate_generated=false by default
# ============================================================


def test_candidate_generated_false_by_default():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.candidate_generated is False


# ============================================================
# P3-K3-9: full_verifier_required=true
# ============================================================


def test_full_verifier_required_true():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.full_verifier_required is True


# ============================================================
# P3-K3-10: claim_gate_required=true
# ============================================================


def test_claim_gate_required_true():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.claim_gate_required is True


# ============================================================
# P3-K3-11: public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_false():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.public_claim_allowed is False


# ============================================================
# P3-K3-12: production_ready=false
# ============================================================


def test_production_ready_false():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    assert resp.production_ready is False


# ============================================================
# P3-K3-13: module imports no cloud SDK / network client
# ============================================================


def test_no_cloud_sdk_import():
    import nexus.services.local_heal.p3_provider_contract as mod
    source = open(mod.__file__).read()
    assert "openai" not in source.lower()
    assert "anthropic" not in source.lower()
    assert "google.cloud" not in source.lower()
    assert "requests" not in source.lower()
    assert "httpx" not in source.lower()
    assert "aiohttp" not in source.lower()


# ============================================================
# P3-K3-14: response JSON serializable
# ============================================================


def test_response_json_serializable():
    req = build_p3_provider_request(compact_prompt_hash="h", env_guard_present=True)
    resp = process_p3_provider_request(req)
    d = p3_provider_response_to_dict(resp)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
