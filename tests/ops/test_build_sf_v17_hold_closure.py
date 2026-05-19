from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sf_v17_hold_closure import build_v17_hold_closure


def _evidence(path: Path, tokens: int) -> str:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "route_cost_ledger": {
                    "arms": {
                        "with_nexus": {
                            "avg_tokens": tokens,
                            "provider_token_measured_rate": 1.0,
                            "clean_model_cost_evidence_rate": 1.0,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def _candidate(tmp_path: Path, *, capability: str, skill: str, verdict: str, effective: int) -> dict:
    return {
        "capability_id": capability,
        "arm_id": f"candidate_{skill}",
        "skill_id": skill,
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "trust_mismatch": False,
        "token_measured": True,
        "provider_token_measured_rate": None,
        "tokens": 100,
        "wall_sec": 10.0,
        "catalog_verdict": verdict,
        "effective_rows": effective,
        "evidence_path": _evidence(tmp_path / capability / skill / "evidence_bundle.json", 100),
        "receipt_path": str(tmp_path / capability / skill),
        "token_delta_vs_no_skill": -10,
        "wall_delta_vs_no_skill_sec": -1.5,
    }


def test_v17_hold_closure_uses_evidence_bundle_provider_rate(tmp_path):
    v16_rollup = {
        "decisions": [
            {
                "capability_id": "benchmark_meta_opt",
                "candidates": [
                    _candidate(
                        tmp_path,
                        capability="benchmark_meta_opt",
                        skill="nexus-benchmark-continuous-optimization",
                        verdict="keep",
                        effective=1,
                    )
                ],
            },
            {
                "capability_id": "policy_capability_gate",
                "candidates": [
                    _candidate(
                        tmp_path,
                        capability="policy_capability_gate",
                        skill="nexus-root-cause-probe",
                        verdict="keep",
                        effective=1,
                    )
                ],
            },
            {
                "capability_id": "delivery_acceptance_gate",
                "candidates": [
                    _candidate(
                        tmp_path,
                        capability="delivery_acceptance_gate",
                        skill="acceptance-evidence-failclosed",
                        verdict="reject",
                        effective=0,
                    )
                ],
            },
        ]
    }

    rollup, overlay, closure = build_v17_hold_closure(
        v16_rollup=v16_rollup,
        v16_overlay={"primary_skill_by_capability": {"repair_loop": "tdd"}, "applied_primary": []},
        v16_closure={"summary": {"runtime_primary_capability_count": 1}},
    )

    assert rollup["status"] == "PASS"
    assert rollup["summary"]["approve_primary_count"] == 2
    assert rollup["summary"]["documented_no_skill_primary_count"] == 1
    assert overlay["primary_skill_by_capability"]["benchmark_meta_opt"] == "nexus-benchmark-continuous-optimization"
    assert overlay["primary_skill_by_capability"]["policy_capability_gate"] == "nexus-root-cause-probe"
    assert "delivery_acceptance_gate" not in overlay["primary_skill_by_capability"]
    assert closure["summary"]["residual_held"] == 0
    assert closure["summary"]["documented_no_skill_primary"] == 1
