from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sfv2_role_ablation_probe import build_sfv2_role_ablation_probe, main


def _sfv2() -> dict:
    return {
        "rows": [
            {
                "capability": "codeintel",
                "m4_multi_skill_assembly": {"mode": "Mode C (Swarm)"},
                "m5_role_ablation": {
                    "matrix": [
                        {"arm_id": "full_assembly", "skill_ids": ["scout", "logic", "audit"]},
                        {"arm_id": "minus_scout", "dropped_role": "Scout", "skill_ids": ["logic", "audit"]},
                        {"arm_id": "minus_logic", "dropped_role": "Logic", "skill_ids": ["scout", "audit"]},
                        {"arm_id": "minus_audit", "dropped_role": "Audit", "skill_ids": ["scout", "logic"]},
                    ]
                },
                "m6_mat_b_decision": {
                    "decision_state": "APPROVE_MULTI_ASSEMBLY",
                    "verdict": "APPROVE_HEEP_MODE_CANDIDATE",
                    "delta": {"token_delta": -10},
                },
            },
            {
                "capability": "xray",
                "m5_role_ablation": {"matrix": []},
                "m6_mat_b_decision": {"decision_state": "KEEP_SINGLE_PRIMARY"},
            },
        ]
    }


def test_role_ablation_probe_generates_full_and_minus_arms() -> None:
    payload = build_sfv2_role_ablation_probe(sfv2_pipeline=_sfv2())

    assert payload["status"] == "PASS"
    assert payload["summary"]["approved_multi_assembly_count"] == 1
    assert payload["summary"]["arm_count"] == 4
    assert payload["summary"]["ready_for_live_role_ablation_count"] == 1
    assert payload["rows"][0]["role_contribution_state"] == "READY_FOR_LIVE_ROLE_ABLATION"
    assert payload["rows"][0]["arms"][1]["runner_env"]["NEXUS_SFV2_DROPPED_ROLE"] == "Scout"


def test_role_ablation_probe_returns_when_approved_row_lacks_matrix() -> None:
    sfv2 = _sfv2()
    sfv2["rows"][0]["m5_role_ablation"]["matrix"] = []

    payload = build_sfv2_role_ablation_probe(sfv2_pipeline=sfv2)

    assert payload["status"] == "RETURN"
    assert "codeintel:missing_role_ablation_matrix" in payload["blockers"]


def test_role_ablation_probe_cli_writes_output(tmp_path: Path, capsys) -> None:
    sfv2 = tmp_path / "sfv2.json"
    output = tmp_path / "probe.json"
    sfv2.write_text(json.dumps(_sfv2()), encoding="utf-8")

    rc = main(["--sfv2", str(sfv2), "--output", str(output)])
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output.exists()
    assert captured["status"] == "PASS"
    assert captured["arm_count"] == 4
