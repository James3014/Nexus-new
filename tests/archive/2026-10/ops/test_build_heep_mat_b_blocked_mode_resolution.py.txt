from __future__ import annotations

from scripts.ops.build_heep_mat_b_blocked_mode_resolution import build_blocked_mode_resolution


def test_provider_token_blocker_can_resolve_non_cost_multi_skill_win() -> None:
    report = {
        "comparisons": [
            {
                "capability": "xray",
                "baseline_row_id": "base",
                "challenger_row_id": "multi",
                "baseline": {
                    "receipt_chain_pass": True,
                    "skill_mount_contract_status": "PASS",
                    "trust_mismatch": False,
                },
                "challenger": {
                    "receipt_chain_pass": True,
                    "skill_mount_contract_status": "PASS",
                    "trust_mismatch": False,
                },
                "delta": {
                    "evidence_seal_count_delta": 1,
                    "pollution_pct_delta": 0,
                    "wall_delta": -1.2,
                },
            }
        ]
    }
    queue = {
        "queue": [
            {
                "capability": "xray",
                "blocker": "BLOCKED_BY_PROVIDER_TOKEN_TRUTH",
            }
        ]
    }
    next_replay = {"first_return": {"token_data_contract_status": "DATA_CONTRACT_VIOLATION"}}

    out = build_blocked_mode_resolution(
        mat_b_report=report,
        blocker_queue=queue,
        next_replay_status=next_replay,
    )

    assert out["summary"]["multi_skill_non_cost_win_count"] == 1
    assert out["summary"]["runtime_update_allowed"] is False
    assert out["rows"][0]["mode_decision"] == "MULTI_SKILL_NON_COST_WIN"
    assert out["rows"][0]["provider_cost_status"] == "HOLD_PROVIDER_TOKEN_TRUTH"


def test_receipt_blocker_remains_undecided_until_executor_receipt_exists() -> None:
    report = {"comparisons": [{"capability": "drone", "baseline_row_id": "base", "challenger_row_id": "multi"}]}
    queue = {
        "queue": [
            {
                "capability": "drone",
                "blocker": "BLOCKED_BY_RECEIPT_DATA_CONTRACT",
                "missing_expected_capabilities": ["drone"],
            }
        ]
    }

    out = build_blocked_mode_resolution(mat_b_report=report, blocker_queue=queue)

    assert out["summary"]["receipt_chain_missing_count"] == 1
    assert out["rows"][0]["mode_decision"] == "UNDECIDED_RECEIPT_CHAIN_MISSING"
    assert out["rows"][0]["missing_expected_capabilities"] == ["drone"]
