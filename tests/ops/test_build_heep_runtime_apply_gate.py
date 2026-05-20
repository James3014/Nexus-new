from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_heep_runtime_apply_gate import build_heep_runtime_apply_gate


def test_heep_runtime_apply_gate_blocks_reference_only_skills(tmp_path: Path) -> None:
    status_report = tmp_path / "status.json"
    status_report.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "candidate-guard",
                        "path": ".agents/skills/candidate-guard/SKILL.md",
                        "skill_status": "external_reference_candidate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = {
        "comparisons": [
            {"capability": "codeintel", "verdict": "APPROVE_HEEP_MODE_CANDIDATE"},
        ]
    }
    matrix = {
        "rows": [
            {
                "capability": "codeintel",
                "arm_id": "heep_multi_skill",
                "heep_mode": "Mode B (Guard)",
                "skill_mount_requests": ["candidate-guard"],
            }
        ]
    }

    gate = build_heep_runtime_apply_gate(
        mat_b_report=report,
        execution_matrix=matrix,
        skill_status_report=str(status_report),
    )

    assert gate["status"] == "RETURN"
    assert gate["summary"]["runtime_update_allowed"] is False
    assert gate["cases"][0]["skill_checks"][0]["runtime_final_receipt_chain"]["selected"] is True
    assert gate["cases"][0]["skill_checks"][0]["runtime_final_receipt_chain"]["injected"] is False
    assert "codeintel:candidate-guard:reference_only_status:external_reference_candidate" in gate["blockers"]


def test_heep_runtime_apply_gate_passes_runtime_curated_skill(tmp_path: Path) -> None:
    status_report = tmp_path / "status.json"
    status_report.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "curated-guard",
                        "path": ".agents/skills/curated-guard/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "codeintel",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = {
        "comparisons": [
            {"capability": "codeintel", "verdict": "APPROVE_HEEP_MODE_CANDIDATE"},
        ]
    }
    matrix = {
        "rows": [
            {
                "capability": "codeintel",
                "arm_id": "heep_multi_skill",
                "heep_mode": "Mode B (Guard)",
                "skill_mount_requests": ["curated-guard"],
            }
        ]
    }

    gate = build_heep_runtime_apply_gate(
        mat_b_report=report,
        execution_matrix=matrix,
        skill_status_report=str(status_report),
    )

    assert gate["status"] == "PASS"
    assert gate["summary"]["runtime_update_allowed"] is True
    chain = gate["cases"][0]["skill_checks"][0]["runtime_final_receipt_chain"]
    assert all(chain.values())
