from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sf_final_capability_skill_settlement import (
    build_sf_final_capability_skill_settlement,
    main,
)


def _inventory() -> dict:
    return {
        "summary": {
            "total_skill_files": 1759,
            "candidate_inbox_count": 574,
        },
        "skills": [
            {
                "name": "code-symbol-scout",
                "path": "/tmp/code-symbol-scout/SKILL.md",
                "sha256": "sha-code",
                "status": "reference",
                "family": "codeintel",
                "description": "Scan repo symbols and impact.",
            },
            {
                "name": "artifact-audit-gate",
                "path": "/tmp/artifact-audit-gate/SKILL.md",
                "sha256": "sha-artifact",
                "status": "reference",
                "family": "governance",
                "description": "Audit delivery evidence and artifact gates.",
            },
            {
                "name": "candidate-skill-from-noisy",
                "path": "/tmp/candidate-skill-from-noisy/SKILL.md",
                "sha256": "sha-noisy",
                "status": "candidate_inbox",
                "family": "candidate",
                "description": "Noisy candidate must stay quarantined.",
            },
            {
                "name": "unmatched-reference",
                "path": "/tmp/unmatched-reference/SKILL.md",
                "sha256": "sha-unmatched",
                "status": "reference",
                "family": "misc",
                "description": "No route terms.",
            },
        ],
    }


def _fair_pool() -> dict:
    return {
        "summary": {
            "total_candidates": 1759,
            "ablation_eligible_count": 3,
            "runtime_eligible_count": 1,
            "quarantine_count": 1,
        },
        "candidates": [
            {
                "skill_id": "code-symbol-scout",
                "path": "/tmp/code-symbol-scout/SKILL.md",
                "sha256": "sha-code",
                "capability_candidates": ["repair_and_coding"],
                "load_when": "codeintel repo symbol scan impact",
                "safety_status": "runtime_reviewed",
                "ablation_eligible": True,
                "runtime_eligible": True,
            },
            {
                "skill_id": "artifact-audit-gate",
                "path": "/tmp/artifact-audit-gate/SKILL.md",
                "sha256": "sha-artifact",
                "capability_candidates": ["governance_and_trust"],
                "load_when": "artifact evidence audit gate",
                "safety_status": "ablation_only",
                "ablation_eligible": True,
                "runtime_eligible": False,
            },
            {
                "skill_id": "candidate-skill-from-noisy",
                "path": "/tmp/candidate-skill-from-noisy/SKILL.md",
                "sha256": "sha-noisy",
                "capability_candidates": ["repair_and_coding"],
                "load_when": "candidate inbox code scan",
                "safety_status": "quarantined",
                "ablation_eligible": True,
                "runtime_eligible": False,
            },
        ],
    }


def _sfv2() -> dict:
    return {
        "rows": [
            {
                "capability": "codeintel",
                "m2_shortlist": {"current_primary": "current-codeintel"},
                "m6_mat_b_decision": {"decision_state": "KEEP_SINGLE_PRIMARY"},
                "m8_runtime_apply_review": {"review_state": "NO_RUNTIME_APPLY_NEEDED"},
            },
            {
                "capability": "artifact_gate",
                "m2_shortlist": {"current_primary": "current-artifact"},
                "m6_mat_b_decision": {"decision_state": "APPROVE_MULTI_ASSEMBLY"},
                "m8_runtime_apply_review": {"review_state": "READY_FOR_RUNTIME_APPLY_REVIEW"},
            },
        ]
    }


def test_sf_final_settlement_reconciles_historical_pool_and_excludes_quarantine() -> None:
    payload = build_sf_final_capability_skill_settlement(
        inventory=_inventory(),
        fair_pool=_fair_pool(),
        sfv2_pipeline=_sfv2(),
        top_k=4,
    )

    assert payload["status"] == "PASS"
    assert payload["summary"]["historical_total_skill_files"] == 1759
    assert payload["summary"]["historical_fair_pool_total_candidates"] == 1759
    assert payload["summary"]["processed_ablation_eligible_count"] == 3
    assert payload["summary"]["quarantine_count"] == 1
    assert payload["summary"]["capability_count"] == 2
    assert payload["summary"]["capabilities_with_shortlist_count"] == 2
    assert payload["summary"]["runtime_update_allowed"] is False
    assert payload["summary"]["public_benchmark_allowed"] is False

    code_shortlist = payload["capability_buckets"]["by_capability"]["codeintel"]["shortlist"]
    assert {row["skill_id"] for row in code_shortlist} == {"code-symbol-scout"}
    assert "candidate-skill-from-noisy" not in {row["skill_id"] for row in payload["sf_r_candidate_intake"]["skills"]}
    assert payload["inventory_reconciliation"]["reconciled_counts"]["quarantine"] == 1


def test_sf_final_settlement_cli_writes_report(tmp_path: Path, capsys) -> None:
    inventory_path = tmp_path / "inventory.json"
    fair_pool_path = tmp_path / "fair_pool.json"
    sfv2_path = tmp_path / "sfv2.json"
    output_path = tmp_path / "settlement.json"
    inventory_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    fair_pool_path.write_text(json.dumps(_fair_pool()), encoding="utf-8")
    sfv2_path.write_text(json.dumps(_sfv2()), encoding="utf-8")

    rc = main(
        [
            "--inventory",
            str(inventory_path),
            "--fair-pool",
            str(fair_pool_path),
            "--sfv2",
            str(sfv2_path),
            "--output",
            str(output_path),
        ]
    )
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output_path.exists()
    assert captured["status"] == "PASS"
    assert captured["historical_total_skill_files"] == 1759
    assert captured["processed_ablation_eligible_count"] == 3
    assert captured["output"] == str(output_path)
