"""P7-A5: Armor Readiness Decision Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p7_armor_readiness import P7ArmorReadinessDecision, evaluate_armor_readiness


GOOD = dict(manifest_complete=True, invariants_passed=True, synthetic_trace_present=True,
            receipts_present=True, all_receipts_complete=True, p3_closed=True, p6_closed=True)


def test_valid_returns_synthetic_e2e_ready():
    d = evaluate_armor_readiness(**GOOD)
    assert d.decision == "P7_CLOSED_ARMOR_SYNTHETIC_E2E_READY"


def test_missing_manifest_blocks():
    d = evaluate_armor_readiness(**{**GOOD, "manifest_complete": False})
    assert "manifest_incomplete" in d.blocked_reasons


def test_missing_invariants_blocks():
    d = evaluate_armor_readiness(**{**GOOD, "invariants_passed": False})
    assert "invariants_failed" in d.blocked_reasons


def test_provider_invoked_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, provider_invoked=True)
    assert d.decision == "P7_CLOSED_ROLLBACK_REQUIRED"
    assert "provider_invoked" in d.blocked_reasons


def test_network_invoked_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, network_invoked=True)
    assert "network_invoked" in d.blocked_reasons


def test_api_key_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, api_key_used=True)
    assert "api_key_used" in d.blocked_reasons


def test_patch_apply_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, patch_apply_invoked=True)
    assert "patch_apply_invoked" in d.blocked_reasons


def test_runtime_change_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, runtime_behavior_changed=True)
    assert "runtime_behavior_changed" in d.blocked_reasons


def test_solved_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, solved_claim=True)
    assert "solved_claim" in d.blocked_reasons


def test_public_claim_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, public_claim_allowed=True)
    assert "public_claim_allowed" in d.blocked_reasons


def test_production_ready_triggers_rollback():
    d = evaluate_armor_readiness(**GOOD, production_ready=True)
    assert "production_ready" in d.blocked_reasons


def test_p3_not_closed_blocks():
    d = evaluate_armor_readiness(**{**GOOD, "p3_closed": False})
    assert "p3_not_closed" in d.blocked_reasons


def test_p6_not_closed_blocks():
    d = evaluate_armor_readiness(**{**GOOD, "p6_closed": False})
    assert "p6_not_closed" in d.blocked_reasons


def test_json_serializable():
    d = evaluate_armor_readiness(**GOOD)
    json.dumps({"decision": d.decision, "blocked_reasons": d.blocked_reasons})
