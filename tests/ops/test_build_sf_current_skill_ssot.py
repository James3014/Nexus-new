from __future__ import annotations

from scripts.ops.build_sf_current_skill_ssot import build_current_skill_ssot


def _smoke_case(capability: str, skill_id: str, *, used: bool = True) -> dict:
    return {
        "blocking_skill_mount_violations": [],
        "capability": capability,
        "expected_skill": skill_id,
        "runtime_final_receipt_chain": {
            "evidence_present": True,
            "gate_passed": True,
            "injected": True,
            "outcome_contributed": True,
            "selected": True,
            "used": used,
        },
        "status": "PASS",
    }


def test_build_current_skill_ssot_reconciles_overlay_provenance_and_smoke() -> None:
    manifest = build_current_skill_ssot(
        overlay={
            "status": "PASS",
            "runtime_update_allowed": True,
            "summary": {"capability_count": 1},
            "primary_skill_by_capability": {"repair_loop": "tdd"},
        },
        original_map={
            "rows": [
                {
                    "capability": "repair_loop",
                    "decision": "keep_current_best",
                    "original_skill_name": "tdd",
                    "original_source_path": "/skills/tdd/SKILL.md",
                    "primary_skill_id": "tdd",
                    "source_round_or_root": "repo-local",
                }
            ]
        },
        smoke={"status": "PASS", "cases": [_smoke_case("repair_loop", "tdd")]},
    )

    assert manifest["status"] == "PASS"
    assert manifest["runtime_update_allowed"] is True
    assert manifest["public_benchmark_allowed"] is False
    assert manifest["rows"][0]["original_skill_name"] == "tdd"
    assert manifest["rows"][0]["runtime_final_receipt_chain"]["outcome_contributed"] is True


def test_build_current_skill_ssot_returns_when_smoke_receipt_chain_is_incomplete() -> None:
    manifest = build_current_skill_ssot(
        overlay={
            "status": "PASS",
            "runtime_update_allowed": True,
            "summary": {"capability_count": 1},
            "primary_skill_by_capability": {"repair_loop": "tdd"},
        },
        original_map={"rows": [{"capability": "repair_loop", "primary_skill_id": "tdd"}]},
        smoke={"status": "PASS", "cases": [_smoke_case("repair_loop", "tdd", used=False)]},
    )

    assert manifest["status"] == "RETURN"
    assert manifest["runtime_update_allowed"] is False
    assert "repair_loop:tdd:receipt_chain_missing_used" in manifest["blockers"]


def test_build_current_skill_ssot_returns_on_original_map_mismatch() -> None:
    manifest = build_current_skill_ssot(
        overlay={
            "status": "PASS",
            "runtime_update_allowed": True,
            "summary": {"capability_count": 1},
            "primary_skill_by_capability": {"artifact_gate": "new-artifact-skill"},
        },
        original_map={
            "rows": [
                {
                    "capability": "artifact_gate",
                    "original_skill_name": "old-artifact",
                    "primary_skill_id": "old-artifact-skill",
                }
            ]
        },
        smoke={"status": "PASS", "cases": [_smoke_case("artifact_gate", "new-artifact-skill")]},
    )

    assert manifest["status"] == "RETURN"
    assert "artifact_gate:new-artifact-skill:original_map_primary_mismatch" in manifest["blockers"]
