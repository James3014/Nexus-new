from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sfv2_skill_selection_pipeline import build_sfv2_skill_selection_pipeline, main


def _original_map() -> dict:
    return {
        "rows": [
            {
                "capability": "codeintel",
                "primary_skill_id": "code-scout",
                "original_skill_name": "Code Scout",
                "original_source_path": "/private/tmp/round/code-scout/SKILL.md",
                "source_round_or_root": "round7",
            },
            {
                "capability": "direct_master_loop",
                "primary_skill_id": "direct-primary",
                "original_skill_name": "Direct Primary",
                "source_round_or_root": "current_best",
            },
        ]
    }


def _assembly() -> dict:
    return {
        "rows": [
            {
                "capability": "codeintel",
                "primary_skill_id": "code-scout",
                "recommended_mode": "Mode C (Swarm)",
                "assembly": [
                    {"role": "Scout", "skill_id": "code-scout"},
                    {"role": "Logic", "skill_id": "route-logic"},
                    {"role": "Audit", "skill_id": "audit-guard"},
                ],
            },
            {
                "capability": "direct_master_loop",
                "primary_skill_id": "direct-primary",
                "recommended_mode": "Mode A (Solo)",
                "assembly": [{"role": "primary", "skill_id": "direct-primary"}],
            },
        ]
    }


def _mat_b() -> dict:
    return {
        "comparisons": [
            {"capability": "codeintel", "verdict": "APPROVE_HEEP_MODE_CANDIDATE", "reason_codes": []},
            {
                "capability": "direct_master_loop",
                "verdict": "BLOCKED_BY_PROVIDER_TOKEN_TRUTH",
                "reason_codes": ["baseline_infra_invalid:model_call_without_tokens"],
            },
        ]
    }


def _queue() -> dict:
    return {
        "rows": [
            {
                "capability": "codeintel",
                "challenger_arm": {"skill_ids": ["code-scout", "route-logic", "audit-guard"]},
            },
            {"capability": "direct_master_loop", "challenger_arm": {"skill_ids": ["direct-primary"]}},
        ]
    }


def _overlay() -> dict:
    return {
        "status": "PASS",
        "skill_assembly_by_capability": {
            "codeintel": [
                {"role": "skill_1", "skill_id": "code-scout"},
                {"role": "skill_2", "skill_id": "route-logic"},
                {"role": "skill_3", "skill_id": "audit-guard"},
            ]
        },
    }


def _smoke() -> dict:
    return {"cases": [{"capability": "codeintel", "status": "PASS"}]}


def test_sfv2_pipeline_generates_all_milestones_and_role_ablation() -> None:
    payload = build_sfv2_skill_selection_pipeline(
        original_map=_original_map(),
        assembly_catalog=_assembly(),
        mat_b_report=_mat_b(),
        compare_queue=_queue(),
        runtime_overlay=_overlay(),
        post_apply_smoke=_smoke(),
    )

    assert payload["status"] == "PASS"
    assert payload["summary"]["capability_count"] == 2
    assert payload["summary"]["approve_multi_assembly_count"] == 1
    assert payload["summary"]["hold_provider_token_truth_count"] == 1
    assert payload["summary"]["role_ablation_matrix_count"] == 4
    assert all(item["status"] == "PASS" for key, item in payload["milestones"].items() if key.startswith("M"))

    codeintel = payload["rows"][0]
    assert codeintel["m6_mat_b_decision"]["decision_state"] == "APPROVE_MULTI_ASSEMBLY"
    assert codeintel["m5_role_ablation"]["status"] == "READY_FOR_ROLE_CONTRIBUTION_REPLAY"
    assert [row["arm_id"] for row in codeintel["m5_role_ablation"]["matrix"]] == [
        "full_assembly",
        "minus_scout",
        "minus_logic",
        "minus_audit",
    ]
    assert codeintel["m8_runtime_apply_review"]["review_state"] == "RUNTIME_OVERLAY_SMOKE_PASS"


def test_sfv2_pipeline_blocks_quarantined_primary() -> None:
    original = _original_map()
    original["rows"][0]["primary_skill_id"] = "candidate-skill-from-noisy"
    original["rows"][0]["original_source_path"] = ".codexworktrees/noisy/SKILL.md"

    payload = build_sfv2_skill_selection_pipeline(
        original_map=original,
        assembly_catalog=_assembly(),
        mat_b_report=_mat_b(),
        compare_queue=_queue(),
        runtime_overlay=_overlay(),
        post_apply_smoke=_smoke(),
    )

    assert payload["status"] == "RETURN"
    assert "codeintel:quarantined_primary_skill" in payload["blockers"]


def test_sfv2_pipeline_cli_writes_output(tmp_path: Path, capsys) -> None:
    original = tmp_path / "original.json"
    assembly = tmp_path / "assembly.json"
    mat_b = tmp_path / "mat_b.json"
    queue = tmp_path / "queue.json"
    overlay = tmp_path / "overlay.json"
    smoke = tmp_path / "smoke.json"
    output = tmp_path / "sfv2.json"
    for path, payload in (
        (original, _original_map()),
        (assembly, _assembly()),
        (mat_b, _mat_b()),
        (queue, _queue()),
        (overlay, _overlay()),
        (smoke, _smoke()),
    ):
        path.write_text(json.dumps(payload), encoding="utf-8")

    rc = main(
        [
            "--original-map",
            str(original),
            "--assembly",
            str(assembly),
            "--mat-b",
            str(mat_b),
            "--queue",
            str(queue),
            "--runtime-overlay",
            str(overlay),
            "--post-apply-smoke",
            str(smoke),
            "--output",
            str(output),
        ]
    )
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output.exists()
    assert captured["status"] == "PASS"
    assert captured["output"] == str(output)
