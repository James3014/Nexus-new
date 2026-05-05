from __future__ import annotations

from nexus.core.evolution_protocols import (
    EvolutionTier,
    build_quiet_moment_event,
    decide_forgetting,
    evaluate_shadow_promotion,
)


def test_l3_forgetting_requires_evidence_and_approval():
    decision = decide_forgetting(EvolutionTier.L3_SWARM)

    assert decision.allowed is False
    assert decision.reason_codes == ("missing_forgetting_evidence", "missing_explicit_approval")


def test_l3_forgetting_allows_with_evidence_and_explicit_approval():
    decision = decide_forgetting(EvolutionTier.L3_SWARM, evidence_refs=["EV-1"], explicit_approval=True)

    assert decision.allowed is True
    assert decision.reason_codes == ()


def test_quiet_moment_event_is_non_mutating():
    event = build_quiet_moment_event(
        reason="swarm divergence",
        affected_nodes=["node-a", "node-b"],
        resume_after_seconds=-5,
    )

    assert event["schema_version"] == "nexus_quiet_moment.v1"
    assert event["production_writes_allowed"] is False
    assert event["allowed_actions"] == ["observe", "report", "rollback"]
    assert event["resume_after_seconds"] == 0


def test_shadow_promotion_remains_shadow_only_when_evidence_is_weak():
    decision = evaluate_shadow_promotion(
        [
            {"passed": True, "evidence_ref": "EV-1"},
            {"passed": False, "evidence_ref": "EV-2"},
        ],
        allow_production_writes=True,
    )

    assert decision.status == "shadow_only"
    assert decision.production_write_allowed is False
    assert "shadow_must_not_write_production" in decision.reason_codes
    assert "insufficient_shadow_rows" in decision.reason_codes


def test_shadow_promotion_can_be_eligible_but_still_non_mutating():
    decision = evaluate_shadow_promotion(
        [
            {"passed": True, "evidence_ref": "EV-1"},
            {"passed": True, "evidence_ref": "EV-2"},
            {"passed": True, "evidence_ref": "EV-3"},
        ]
    )

    assert decision.status == "eligible"
    assert decision.production_write_allowed is False
    assert decision.reason_codes == ()
