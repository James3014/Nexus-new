from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sf_final_compare_report import build_sf_final_compare_report, main


def _settlement() -> dict:
    return {
        "status": "PASS",
        "canonical_compare_matrix": [
            {
                "capability": "codeintel",
                "current_primary_skill_id": "current-codeintel",
                "candidate_skill_id": "candidate-symbol-scout",
                "candidate_role": "Scout",
                "candidate_source_tier": "approved_external_reference",
                "canonical_source_path": "/tmp/candidate-symbol-scout/SKILL.md",
                "static_fit_score": 70,
                "fit_reason": "term_hits:4",
                "mirror_count": 3,
                "precheck_status": "PASS",
                "precheck_blockers": [],
            },
            {
                "capability": "artifact_gate",
                "current_primary_skill_id": "current-artifact",
                "candidate_skill_id": "worktree-noisy",
                "candidate_role": "Audit",
                "candidate_source_tier": "approved_external_reference",
                "canonical_source_path": "/tmp/worktree-noisy/SKILL.md",
                "static_fit_score": 50,
                "fit_reason": "term_hits:2",
                "mirror_count": 1,
                "precheck_status": "RETURN",
                "precheck_blockers": ["quarantine_tier_blocked"],
            },
            {
                "capability": "repair_loop",
                "current_primary_skill_id": "current-repair",
                "candidate_skill_id": "current-repair",
                "candidate_role": "Logic",
                "candidate_source_tier": "nexus_curated_candidate",
                "canonical_source_path": "/tmp/current-repair/SKILL.md",
                "static_fit_score": 85,
                "fit_reason": "term_hits:5",
                "mirror_count": 1,
                "precheck_status": "PASS",
                "precheck_blockers": [],
            },
        ],
    }


def test_sf_final_compare_report_normalizes_ready_reject_and_keep_current() -> None:
    payload = build_sf_final_compare_report(settlement=_settlement())

    assert payload["status"] == "PASS"
    assert payload["summary"]["compare_row_count"] == 3
    assert payload["summary"]["ready_for_live_compare_count"] == 1
    assert payload["summary"]["reject_precheck_count"] == 1
    assert payload["summary"]["keep_current_no_live_evidence_count"] == 1
    assert payload["summary"]["runtime_update_allowed"] is False
    assert payload["summary"]["public_benchmark_allowed"] is False

    ready = [row for row in payload["compare_rows"] if row["decision"] == "READY_FOR_LIVE_COMPARE"][0]
    assert ready["challenger_arm"]["mode"] == "candidate_multi_skill"
    assert ready["challenger_arm"]["skill_ids"] == ["current-codeintel", "candidate-symbol-scout"]
    assert payload["live_compare_batches"][0]["capability"] == "codeintel"
    assert payload["live_compare_batches"][0]["runner_contract"]["trust_mismatch_required"] == 0


def test_sf_final_compare_cli_writes_report(tmp_path: Path, capsys) -> None:
    settlement_path = tmp_path / "settlement.json"
    output_path = tmp_path / "compare.json"
    settlement_path.write_text(json.dumps(_settlement()), encoding="utf-8")

    rc = main(["--settlement", str(settlement_path), "--output", str(output_path)])
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output_path.exists()
    assert captured["status"] == "PASS"
    assert captured["compare_row_count"] == 3
    assert captured["ready_for_live_compare_count"] == 1
    assert captured["output"] == str(output_path)
