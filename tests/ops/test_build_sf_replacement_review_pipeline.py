from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sf_replacement_review_pipeline import build_sf_replacement_review_pipeline, main


def _sfv2() -> dict:
    return {
        "rows": [
            {
                "capability": "codeintel",
                "m1_intake": {
                    "primary_skill_id": "current-codeintel",
                    "source_class": "current_best",
                },
                "m2_shortlist": {"current_primary": "current-codeintel"},
                "m4_multi_skill_assembly": {"mode": "Mode A (Solo)"},
                "m6_mat_b_decision": {
                    "decision_state": "KEEP_SINGLE_PRIMARY",
                    "verdict": "KEEP_SINGLE_PRIMARY",
                },
                "m7_catalog_update": {"selected_skill_ids": ["current-codeintel"]},
                "m8_runtime_apply_review": {"review_state": "NO_RUNTIME_APPLY_NEEDED"},
            },
            {
                "capability": "artifact_gate",
                "m1_intake": {
                    "primary_skill_id": "current-artifact",
                    "source_class": "approved_external_reference",
                },
                "m2_shortlist": {"current_primary": "current-artifact"},
                "m4_multi_skill_assembly": {"mode": "Mode C (Swarm)"},
                "m6_mat_b_decision": {
                    "decision_state": "APPROVE_MULTI_ASSEMBLY",
                    "verdict": "APPROVE_HEEP_MODE_CANDIDATE",
                },
                "m7_catalog_update": {"selected_skill_ids": ["current-artifact", "audit-guard"]},
                "m8_runtime_apply_review": {"review_state": "READY_FOR_RUNTIME_APPLY_REVIEW"},
            },
        ]
    }


def _candidate_intake() -> dict:
    return {
        "skills": [
            {
                "skill_id": "next-codeintel",
                "source_tier": "nexus_curated_candidate",
                "safety_status": "PASS",
                "license_status": "PASS",
                "capability_hints": ["codeintel"],
                "intended_action": "replace_primary",
                "comparison_result": {
                    "status": "PASS",
                    "receipt_chain_pass": True,
                    "trust_mismatch": False,
                    "provider_token_cleanliness": "MEASURED",
                    "success_rate_delta": 0.0,
                    "pollution_pct_delta": 0.0,
                    "reopen_rate_delta": 0.0,
                    "evidence_seal_count_delta": 0,
                    "token_delta": -120,
                    "wall_delta": -1.5,
                },
            },
            {
                "skill_id": "artifact-audit-plus",
                "source_tier": "safe_candidate",
                "safety_status": "PASS",
                "license_status": "COMPATIBLE",
                "capability": "artifact_gate",
                "role": "Audit",
                "intended_action": "add_to_multi",
                "comparison_result": {
                    "status": "PASS",
                    "receipt_chain_pass": True,
                    "trust_mismatch": False,
                    "provider_token_cleanliness": "MEASURED",
                    "success_rate_delta": 0.0,
                    "pollution_pct_delta": 0.0,
                    "reopen_rate_delta": 0.0,
                    "evidence_seal_count_delta": 2,
                    "token_delta": 300,
                    "wall_delta": 0.4,
                },
            },
            {
                "skill_id": "candidate-skill-from-noisy",
                "source_path": ".codexworktrees/noisy/SKILL.md",
                "source_tier": "candidate_inbox",
                "safety_status": "PASS",
                "license_status": "PASS",
                "capability": "codeintel",
            },
        ]
    }


def test_sf_replacement_pipeline_decides_replace_add_and_reject() -> None:
    payload = build_sf_replacement_review_pipeline(
        sfv2_pipeline=_sfv2(),
        candidate_intake=_candidate_intake(),
    )

    assert payload["status"] == "PASS"
    assert payload["summary"]["capability_count"] == 2
    assert payload["summary"]["candidate_intake_count"] == 3
    assert payload["summary"]["candidate_intake_pass_count"] == 2
    assert payload["summary"]["comparison_queue_count"] == 2

    decisions = {row["candidate_skill_id"]: row for row in payload["decision_ledger"] if row["entry_type"] == "candidate"}
    assert decisions["next-codeintel"]["decision"] == "REPLACE_PRIMARY"
    assert decisions["artifact-audit-plus"]["decision"] == "ADD_TO_MULTI"
    assert decisions["candidate-skill-from-noisy"]["decision"] == "REJECT"
    assert "quarantine_tier_blocked" in decisions["candidate-skill-from-noisy"]["blockers"]
    assert payload["runtime_apply_review_packet"]["runtime_update_allowed"] is False
    assert payload["automation_hook"]["forbidden_actions"] == [
        "runtime_default_auto_apply",
        "public_benchmark_unlock",
        "quarantine_skill_mount",
    ]


def test_sf_replacement_pipeline_holds_without_live_compare() -> None:
    candidate = {
        "skills": [
            {
                "skill_id": "next-codeintel",
                "source_tier": "nexus_curated_candidate",
                "safety_status": "PASS",
                "license_status": "PASS",
                "capability_hints": ["codeintel"],
            }
        ]
    }

    payload = build_sf_replacement_review_pipeline(sfv2_pipeline=_sfv2(), candidate_intake=candidate)

    candidate_decisions = [row for row in payload["decision_ledger"] if row["entry_type"] == "candidate"]
    assert candidate_decisions[0]["decision"] == "HOLD_MORE_DATA"
    assert candidate_decisions[0]["reason"] == "needs_flash_nexus_compare"
    assert payload["comparison_queue"][0]["queue_state"] == "READY_FOR_COMPARISON"


def test_sf_replacement_pipeline_cli_writes_output(tmp_path: Path, capsys) -> None:
    sfv2_path = tmp_path / "sfv2.json"
    intake_path = tmp_path / "intake.json"
    output_path = tmp_path / "sf_r.json"
    sfv2_path.write_text(json.dumps(_sfv2()), encoding="utf-8")
    intake_path.write_text(json.dumps(_candidate_intake()), encoding="utf-8")

    rc = main(["--sfv2", str(sfv2_path), "--candidate-intake", str(intake_path), "--output", str(output_path)])
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output_path.exists()
    assert captured["status"] == "PASS"
    assert captured["output"] == str(output_path)
