"""M0: formal_from_pilot — pair_count>0 honest REVISE/KEEP; claim stays false."""
from __future__ import annotations

from nexus.services.formal_fused_projection import (
    efficiency_revise_demo_pilot,
    formal_from_pilot,
)


def test_formal_from_demo_pilot_pair_count_and_honest_revise():
    pilot = efficiency_revise_demo_pilot()
    decision = formal_from_pilot(pilot)
    assert decision["phase"] == "formal"
    assert int(decision["pair_count"]) > 0
    assert int(decision["comparable_count"]) > 0
    assert decision["verdict"] in {
        "REVISE_PACKET",
        "KEEP_PACKET",
        "KEEP_PACKET_SELECTIVE",
        "EXPERIMENT_INVALID",
        "STOP_PACKET",
    }
    # Empty tokens → efficiency miss → REVISE (not glue INVALID with pair_count=0)
    assert decision["verdict"] == "REVISE_PACKET"
    assert "efficiency" in str(decision.get("reason") or "").lower() or decision.get(
        "efficiency_gate", {}
    ).get("ok") is False
    assert decision["public_claim_allowed"] is False
    assert decision["routing_surface_changed"] is False
    assert decision.get("production_ready") is False
    assert decision["token_samples_numeric"] == {"b": [], "d": []}


def test_formal_unavailable_tokens_do_not_count_as_numeric():
    pilot = efficiency_revise_demo_pilot()
    pilot["token_samples"] = {"b": ["UNAVAILABLE", None], "d": ["UNAVAILABLE"]}
    decision = formal_from_pilot(pilot)
    assert decision["token_samples_numeric"] == {"b": [], "d": []}
    assert decision["public_claim_allowed"] is False


def test_formal_zero_pairs_is_not_false_keep():
    pilot = {
        "schema": "nexus.fused_live_pilot.v1",
        "pair_count": 0,
        "comparable_count": 0,
        "pairs": [],
        "b_solve_mean": 1.0,
        "d_solve_mean": 1.0,
        "token_samples": {"b": [10], "d": [8]},
    }
    decision = formal_from_pilot(pilot)
    assert decision["pair_count"] == 0
    assert decision["verdict"] != "KEEP_PACKET"
    assert decision["public_claim_allowed"] is False


def test_formal_keep_still_blocks_public_claim():
    """Even if quality+efficiency pass, projection must not unlock public claim."""
    pilot = {
        "schema": "nexus.fused_live_pilot.v1",
        "pair_count": 4,
        "comparable_count": 4,
        "infra_invalid_count": 0,
        "safety_violations": 0,
        "b_solve_mean": 0.5,
        "d_solve_mean": 0.9,
        "token_samples": {"b": [100, 110, 90, 105], "d": [70, 75, 80, 65]},
        "pairs": [
            {
                "comparable": True,
                "treatment_equal": True,
                "d_assist_credited": True,
                "b_infra": False,
                "d_infra": False,
            }
            for _ in range(4)
        ],
    }
    decision = formal_from_pilot(pilot)
    assert decision["public_claim_allowed"] is False
    assert decision.get("production_ready") is False
    # If decision logic returns KEEP, claim still false
    if decision["verdict"] in {"KEEP_PACKET", "KEEP_PACKET_SELECTIVE"}:
        assert decision["public_claim_allowed"] is False
