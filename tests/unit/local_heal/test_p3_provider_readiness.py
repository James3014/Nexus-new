from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_provider_readiness import (
    P3ProviderReadiness,
    compute_p3_provider_readiness,
    p3_provider_readiness_to_dict,
)


# ============================================================
# P3-M4-1: missing provider config blocks
# ============================================================


def test_missing_provider_config_blocks():
    readiness = compute_p3_provider_readiness(provider_config_present=False)
    assert readiness.ready_for_real_invocation is False
    assert "provider_config_missing" in readiness.blocked_reasons


# ============================================================
# P3-M4-2: missing env guard blocks
# ============================================================


def test_missing_env_guard_blocks():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=False,
    )
    assert readiness.ready_for_real_invocation is False
    assert "env_guard_missing" in readiness.blocked_reasons


# ============================================================
# P3-M4-3: api_key_present does not enable invocation
# ============================================================


def test_api_key_present_no_invocation():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
        api_key_env_var="NONEXISTENT_KEY_FOR_TEST",
    )
    assert readiness.provider_invocation_allowed is False
    assert readiness.ready_for_real_invocation is False


# ============================================================
# P3-M4-4: full config still dry_run_only
# ============================================================


def test_full_config_still_dry_run():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    assert readiness.dry_run_only is True
    assert readiness.ready_for_real_invocation is False


# ============================================================
# P3-M4-5: provider_invocation_allowed=false always
# ============================================================


def test_provider_invocation_allowed_always_false():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    assert readiness.provider_invocation_allowed is False


# ============================================================
# P3-M4-6: network_allowed=false always
# ============================================================


def test_network_allowed_always_false():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    assert readiness.network_allowed is False


# ============================================================
# P3-M4-7: sdk_import_allowed=false always
# ============================================================


def test_sdk_import_allowed_always_false():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    assert readiness.sdk_import_allowed is False


# ============================================================
# P3-M4-8: ready_for_real_invocation=false always
# ============================================================


def test_ready_for_real_invocation_always_false():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    assert readiness.ready_for_real_invocation is False


# ============================================================
# P3-M4-9: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    assert readiness.public_claim_allowed is False


# ============================================================
# P3-M4-10: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    assert readiness.production_ready is False


# ============================================================
# P3-M4-11: JSON serializable
# ============================================================


def test_json_serializable():
    readiness = compute_p3_provider_readiness(
        provider_config_present=True,
        env_guard_override=True,
    )
    d = p3_provider_readiness_to_dict(readiness)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)


# ============================================================
# P3-M4-12: no cloud SDK imports
# ============================================================


def test_no_cloud_sdk_imports():
    import nexus.services.local_heal.p3_provider_readiness as mod
    source = open(mod.__file__).read()
    assert "openai" not in source.lower()
    assert "anthropic" not in source.lower()
    assert "google.cloud" not in source.lower()
    assert "requests" not in source.lower()
    assert "httpx" not in source.lower()
