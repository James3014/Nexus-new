from __future__ import annotations

import json

from scripts.ops.build_sf_replacement_cleanliness_manifest import build_manifest_from_sf_rollup


def _arm(skill_id: str, *, tokens: int, wall: float, measured: bool = True, effective: bool = True):
    return {
        "benchmark_status": "SUCCESS",
        "effective": effective,
        "model_calls": 2,
        "provider_token_measured": measured,
        "semantic_status": "VERIFIED",
        "skill_id": skill_id,
        "skill_mount_contract_status": "PASS",
        "status": "PASS",
        "total_tokens": tokens,
        "trust_mismatch": False,
        "wall_duration_sec": wall,
    }


def test_build_manifest_from_sf_rollup_counts_replacements_and_keeps(tmp_path):
    source = tmp_path / "rollup.json"
    output = tmp_path / "cleanliness.json"
    source.write_text(
        json.dumps(
            {
                "schema": "nexus.sf_systematic_all_capability_live_rollup.v32",
                "rows": [
                    {
                        "capability": "artifact_gate",
                        "current_best": _arm("old", tokens=200, wall=20.0),
                        "challenger": _arm("new", tokens=100, wall=10.0),
                        "token_delta_challenger_minus_current": -100,
                        "wall_delta_challenger_minus_current": -10.0,
                        "verdict": "replace_candidate",
                    },
                    {
                        "capability": "research_control_plane",
                        "current_best": _arm("old-r", tokens=100, wall=20.0),
                        "challenger": _arm("new-r", tokens=80, wall=30.0),
                        "token_delta_challenger_minus_current": -20,
                        "wall_delta_challenger_minus_current": 10.0,
                        "verdict": "keep_current_best_cost_or_wall",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_manifest_from_sf_rollup(rollup_path=source, output_path=output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert summary["replace_count"] == 1
    assert summary["no_replacement_count"] == 1
    assert payload["rollup_verdict_counts"] == {
        "keep_current_best_cost_or_wall": 1,
        "replace_candidate": 1,
    }


def test_build_manifest_from_sf_rollup_holds_missing_provider_tokens(tmp_path):
    source = tmp_path / "rollup.json"
    output = tmp_path / "cleanliness.json"
    source.write_text(
        json.dumps(
            {
                "schema": "nexus.sf_systematic_all_capability_live_rollup.v32",
                "rows": [
                    {
                        "capability": "artifact_gate",
                        "current_best": _arm("old", tokens=200, wall=20.0),
                        "challenger": _arm("new", tokens=100, wall=10.0, measured=False),
                        "token_delta_challenger_minus_current": -100,
                        "wall_delta_challenger_minus_current": -10.0,
                        "verdict": "replace_candidate",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_manifest_from_sf_rollup(rollup_path=source, output_path=output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "RETURN"
    assert summary["hold_count"] == 1
    assert payload["decisions"][0]["reason"] == "blocked_by_cleanliness_window"
    assert "blocked_by_missing_cost_truth:challenger" in payload["decisions"][0]["blockers"]


def test_build_manifest_from_sf_rollup_dry_run_does_not_write(tmp_path):
    source = tmp_path / "rollup.json"
    output = tmp_path / "cleanliness.json"
    source.write_text(json.dumps({"rows": []}), encoding="utf-8")

    summary = build_manifest_from_sf_rollup(rollup_path=source, output_path=output, dry_run=True)

    assert summary["status"] == "PASS"
    assert output.exists() is False
