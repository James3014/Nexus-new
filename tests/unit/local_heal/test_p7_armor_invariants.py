"""P7-A2: Cross-Phase Safety Invariant Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p7_armor_invariants import P7ArmorInvariantResult, evaluate_armor_invariants


def test_valid_invariants_pass():
    r = evaluate_armor_invariants()
    assert r.invariant_passed is True
    assert r.blocked_reasons == []


def test_missing_p3_closed_fails():
    r = evaluate_armor_invariants(p3_closed=False)
    assert r.invariant_passed is False
    assert "p3_not_closed" in r.blocked_reasons


def test_missing_p6_closed_fails():
    r = evaluate_armor_invariants(p6_closed=False)
    assert r.invariant_passed is False
    assert "p6_not_closed" in r.blocked_reasons


def test_p2_hash_missing_fails():
    r = evaluate_armor_invariants(p2_hash_truth_required=False)
    assert "p2_hash_truth_missing" in r.blocked_reasons


def test_p2_anchor_missing_fails():
    r = evaluate_armor_invariants(p2_anchor_truth_required=False)
    assert "p2_anchor_truth_missing" in r.blocked_reasons


def test_p4_verifier_missing_fails():
    r = evaluate_armor_invariants(p4_verifier_required=False)
    assert "p4_verifier_missing" in r.blocked_reasons


def test_p4_claim_gate_missing_fails():
    r = evaluate_armor_invariants(p4_claim_gate_required=False)
    assert "p4_claim_gate_missing" in r.blocked_reasons


def test_p6_not_advisory_fails():
    r = evaluate_armor_invariants(p6_advisory_only=False)
    assert "p6_not_advisory_only" in r.blocked_reasons


def test_real_provider_fails():
    r = evaluate_armor_invariants(real_provider_required=True)
    assert "real_provider_required" in r.blocked_reasons


def test_network_fails():
    r = evaluate_armor_invariants(network_required=True)
    assert "network_required" in r.blocked_reasons


def test_api_key_fails():
    r = evaluate_armor_invariants(api_key_required=True)
    assert "api_key_required" in r.blocked_reasons


def test_patch_apply_fails():
    r = evaluate_armor_invariants(patch_apply_allowed=True)
    assert "patch_apply_allowed" in r.blocked_reasons


def test_runtime_change_fails():
    r = evaluate_armor_invariants(runtime_behavior_changed=True)
    assert "runtime_behavior_changed" in r.blocked_reasons


def test_solved_claim_fails():
    r = evaluate_armor_invariants(solved_claim=True)
    assert "solved_claim" in r.blocked_reasons


def test_claim_eligible_fails():
    r = evaluate_armor_invariants(claim_eligible=True)
    assert "claim_eligible" in r.blocked_reasons


def test_public_claim_fails():
    r = evaluate_armor_invariants(public_claim_allowed=True)
    assert "public_claim_allowed" in r.blocked_reasons


def test_production_ready_fails():
    r = evaluate_armor_invariants(production_ready=True)
    assert "production_ready" in r.blocked_reasons


def test_p3_override_fails():
    r = evaluate_armor_invariants(p3_topology_override=True)
    assert "p3_topology_override" in r.blocked_reasons


def test_p4_override_fails():
    r = evaluate_armor_invariants(p4_verifier_override=True)
    assert "p4_verifier_override" in r.blocked_reasons


def test_claim_gate_override_fails():
    r = evaluate_armor_invariants(claim_gate_override=True)
    assert "claim_gate_override" in r.blocked_reasons


def test_p5_override_fails():
    r = evaluate_armor_invariants(p5_selection_override=True)
    assert "p5_selection_override" in r.blocked_reasons


def test_multiple_failures_all_recorded():
    r = evaluate_armor_invariants(solved_claim=True, production_ready=True, public_claim_allowed=True)
    assert "solved_claim" in r.blocked_reasons
    assert "production_ready" in r.blocked_reasons
    assert "public_claim_allowed" in r.blocked_reasons


def test_json_serializable():
    r = evaluate_armor_invariants()
    json.dumps({"invariant_passed": r.invariant_passed, "blocked_reasons": r.blocked_reasons})
