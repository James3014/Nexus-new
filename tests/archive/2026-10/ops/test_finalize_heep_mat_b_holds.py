from __future__ import annotations

from scripts.ops.finalize_heep_mat_b_holds import finalize_heep_mat_b_holds


def test_finalize_heep_mat_b_holds_converts_replayed_token_holds_to_final_blocker() -> None:
    report = {
        "comparisons": [
            {
                "capability": "xray",
                "verdict": "HOLD_MISSING_MAT_B_EVIDENCE",
                "reason_codes": ["baseline_infra_invalid:model_call_without_tokens"],
            },
            {"capability": "codeintel", "verdict": "APPROVE_HEEP_MODE_CANDIDATE", "reason_codes": []},
        ]
    }
    replay = {
        "comparisons": [
            {
                "capability": "xray",
                "baseline_row_id": "replay-base",
                "challenger_row_id": "replay-challenger",
                "verdict": "HOLD_MISSING_MAT_B_EVIDENCE",
                "reason_codes": ["baseline_infra_invalid:model_call_without_tokens"],
            }
        ]
    }

    finalized = finalize_heep_mat_b_holds(report=report, clean_replay_report=replay)

    rows = {row["capability"]: row for row in finalized["comparisons"]}
    assert rows["xray"]["verdict"] == "BLOCKED_BY_PROVIDER_TOKEN_TRUTH"
    assert rows["codeintel"]["verdict"] == "APPROVE_HEEP_MODE_CANDIDATE"
    assert finalized["summary"]["hold_count"] == 0
    assert finalized["summary"]["final_blocker_count"] == 1
    assert finalized["summary"]["runtime_update_allowed"] is False


def test_finalize_heep_mat_b_holds_converts_receipt_holds_to_final_blocker() -> None:
    report = {
        "comparisons": [
            {
                "capability": "swarm_multi_agent",
                "verdict": "HOLD_MISSING_MAT_B_EVIDENCE",
                "reason_codes": ["baseline_infra_invalid:receipt_data_contract_violation"],
            }
        ]
    }
    replay = {
        "comparisons": [
            {
                "capability": "swarm_multi_agent",
                "verdict": "HOLD_MISSING_MAT_B_EVIDENCE",
                "reason_codes": ["baseline_infra_invalid:receipt_data_contract_violation"],
            }
        ]
    }

    finalized = finalize_heep_mat_b_holds(report=report, clean_replay_report=replay)

    assert finalized["comparisons"][0]["verdict"] == "BLOCKED_BY_RECEIPT_DATA_CONTRACT"
