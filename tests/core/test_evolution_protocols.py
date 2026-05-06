from __future__ import annotations

from nexus.core.evolution_protocols import (
    EvolutionTier,
    audit_shadow_isolation,
    build_l3_hard_block_warning,
    build_quiet_moment_event,
    decide_forgetting,
    enforce_evolution_mutation,
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


def test_l3_hard_block_warning_requires_voice_and_mtls_binding():
    warning = build_l3_hard_block_warning(EvolutionTier.L3_SWARM, reason_codes=["missing_explicit_approval"])

    assert warning.allowed is False
    assert warning.voice_warning_required is True
    assert warning.mtls_binding_required is True
    assert "missing_mtls_binding" in warning.reason_codes
    assert "missing_explicit_approval" in warning.reason_codes


def test_evolution_mutation_guard_blocks_l3_without_mtls_even_with_evidence():
    decision = enforce_evolution_mutation(
        EvolutionTier.L3_SWARM,
        evidence_refs=["EV-1"],
        explicit_approval=True,
        mtls_enabled=False,
    )

    assert decision.allowed is False
    assert decision.forgetting.allowed is True
    assert decision.warning.voice_warning_required is True
    assert decision.reason_codes == ("missing_mtls_binding",)


def test_shadow_isolation_blocks_production_write_targets(tmp_path):
    production = tmp_path / "production"
    shadow = tmp_path / "shadow"
    production.mkdir()
    shadow.mkdir()

    decision = audit_shadow_isolation(
        [
            {"target_path": str(shadow / "candidate.json")},
            {"target_path": str(production / "live.json")},
        ],
        production_roots=[str(production)],
    )

    assert decision.isolated is False
    assert decision.production_write_allowed is False
    assert decision.reason_codes == ("shadow_target_inside_production_root",)


def test_shadow_isolation_resolves_symlink_escape_to_production_root(tmp_path):
    production = tmp_path / "production"
    shadow = tmp_path / "shadow"
    production.mkdir()
    shadow.mkdir()
    symlink = shadow / "prod-link"
    symlink.symlink_to(production, target_is_directory=True)

    decision = audit_shadow_isolation(
        [{"target_path": str(symlink / "live.json")}],
        production_roots=[str(production)],
    )

    assert decision.isolated is False
    assert decision.reason_codes == ("shadow_target_inside_production_root",)


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
