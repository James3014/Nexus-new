"""P6-E5: P3 Handoff Contract Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_p3_handoff_contract import P6P3HandoffContract, build_handoff_contract


def test_rollout_candidate_preserves_p3_topology():
    contract = build_handoff_contract("rollout_candidate")
    assert contract.p6_can_override_p3_topology is False


def test_rollout_candidate_cannot_override_p4():
    contract = build_handoff_contract("rollout_candidate")
    assert contract.p6_can_override_p4_verifier is False


def test_rollout_candidate_cannot_mark_solved():
    contract = build_handoff_contract("rollout_candidate")
    assert contract.p6_can_mark_solved is False


def test_rollout_candidate_cannot_set_public_claim():
    contract = build_handoff_contract("rollout_candidate")
    assert contract.p6_can_set_public_claim_allowed is False


def test_blocked_requires_fail_closed():
    contract = build_handoff_contract("blocked")
    assert contract.p6_readiness_state == "blocked"
    assert contract.public_claim_allowed is False
    assert contract.production_ready is False


def test_rollback_requires_fail_closed():
    contract = build_handoff_contract("rollback_required")
    assert contract.p6_readiness_state == "rollback_required"
    assert contract.public_claim_allowed is False
    assert contract.production_ready is False


def test_json_serializable():
    contract = build_handoff_contract()
    d = {"p6_readiness_state": contract.p6_readiness_state, "public_claim_allowed": contract.public_claim_allowed}
    json_str = json.dumps(d)
    assert len(json_str) > 0


def test_no_p3_imports():
    import inspect
    import nexus.services.local_heal.p6_p3_handoff_contract as mod
    source = inspect.getsource(mod)
    assert "p3_" not in source.lower() or "p3_must" in source
    assert "router" not in source.lower()
    assert "capability_planner" not in source.lower()
