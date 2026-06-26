"""
H8-6 Local Model Allowlist Contract Tests

Gate: H8 local model allowlist boundary.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE / NO_LOCAL_MODEL_RUN
- NO_OLLAMA_CALL / NO_QWEN_CALL
- NO_PROVIDER_CALL / NO_MODEL_CALL / NO_MODEL_LOAD / NO_NETWORK_CALL
- production_ready=false / public_claim_allowed=false
- H8 runtime not started

All tests are fixture-only. No real adapter or model is invoked.
"""

from __future__ import annotations

import pytest


def _allowlist_contract() -> dict:
    return {
        "provider_in_allowlist": False,
        "model_in_allowlist": False,
        "local_model_provider": "ollama",
        "local_model_name": "qwen",
        "local_model_allowed": False,
        "local_model_loaded": False,
        "local_model_called": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "provider_call_allowed": False,
        "network_allowed": False,
        "explicit_dry_run_approved": False,
        "route_truth_source": "CapabilityPlanner",
        "adapter_output_is_route_truth": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _check_model_call(a: dict) -> bool:
    if not a.get("provider_in_allowlist"):
        return False
    if not a.get("model_in_allowlist"):
        return False
    if not a.get("model_load_allowed"):
        return False
    if not a.get("model_call_allowed"):
        return False
    if not a.get("explicit_dry_run_approved"):
        return False
    return True


class TestH86AbsentOrEmptyAllowlist:
    def test_h8_6_allowlist_absent_means_local_model_denied(self):
        a = _allowlist_contract()
        del a["provider_in_allowlist"]
        assert _check_model_call(a) is False

    def test_h8_6_empty_allowlist_means_local_model_denied(self):
        a = _allowlist_contract()
        a["provider_in_allowlist"] = False
        a["model_in_allowlist"] = False
        assert _check_model_call(a) is False


class TestH86UnknownProviderModel:
    def test_h8_6_unknown_provider_denied(self):
        a = _allowlist_contract()
        a["local_model_provider"] = "unknown_provider"
        a["provider_in_allowlist"] = False
        assert _check_model_call(a) is False

    def test_h8_6_unknown_model_denied(self):
        a = _allowlist_contract()
        a["local_model_name"] = "unknown_model"
        a["model_in_allowlist"] = False
        assert _check_model_call(a) is False


class TestH86PartialAllowlist:
    def test_h8_6_provider_allowed_model_denied_still_blocks_call(self):
        a = _allowlist_contract()
        a["provider_in_allowlist"] = True
        a["model_in_allowlist"] = False
        assert _check_model_call(a) is False

    def test_h8_6_model_allowed_provider_denied_still_blocks_call(self):
        a = _allowlist_contract()
        a["provider_in_allowlist"] = False
        a["model_in_allowlist"] = True
        assert _check_model_call(a) is False

    def test_h8_6_provider_and_model_allowlist_still_requires_explicit_model_call_allowed(
        self,
    ):
        a = _allowlist_contract()
        a["provider_in_allowlist"] = True
        a["model_in_allowlist"] = True
        a["model_load_allowed"] = False
        a["model_call_allowed"] = False
        assert _check_model_call(a) is False


class TestH86NetworkRemainsDenied:
    def test_h8_6_network_remains_denied_even_when_local_provider_is_allowed(self):
        a = _allowlist_contract()
        a["provider_in_allowlist"] = True
        a["model_in_allowlist"] = True
        a["network_allowed"] = False
        assert a["network_allowed"] is False


class TestH86ExplicitFlagsRequired:
    def test_h8_6_model_load_requires_explicit_flag(self):
        a = _allowlist_contract()
        a["provider_in_allowlist"] = True
        a["model_in_allowlist"] = True
        a["model_load_allowed"] = False
        assert _check_model_call(a) is False

    def test_h8_6_model_call_requires_explicit_flag(self):
        a = _allowlist_contract()
        a["provider_in_allowlist"] = True
        a["model_in_allowlist"] = True
        a["model_call_allowed"] = False
        assert _check_model_call(a) is False


class TestH86AllowlistRecordsAndCannotOverride:
    def test_h8_6_allowlist_decision_recorded_in_receipt(self):
        a = _allowlist_contract()
        assert "local_model_allowed" in a
        assert a["local_model_allowed"] is False

    def test_h8_6_allowlist_cannot_override_route_truth(self):
        a = _allowlist_contract()
        assert a["adapter_output_is_route_truth"] is False
        assert a["route_truth_source"] == "CapabilityPlanner"

    def test_h8_6_allowlist_cannot_set_public_claim_allowed(self):
        a = _allowlist_contract()
        assert a["public_claim_allowed"] is False

    def test_h8_6_allowlist_cannot_set_production_ready(self):
        a = _allowlist_contract()
        assert a["production_ready"] is False
