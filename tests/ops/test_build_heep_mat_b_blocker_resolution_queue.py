from __future__ import annotations

from scripts.ops.build_heep_mat_b_blocker_resolution_queue import build_heep_mat_b_blocker_resolution_queue


def test_blocker_resolution_queue_splits_token_and_receipt_lanes() -> None:
    report = {
        "comparisons": [
            {
                "capability": "xray",
                "verdict": "BLOCKED_BY_PROVIDER_TOKEN_TRUTH",
                "reason_codes": ["baseline_infra_invalid:model_call_without_tokens"],
                "baseline_row_id": "base-token",
                "challenger_row_id": "challenger-token",
            },
            {
                "capability": "drone",
                "verdict": "BLOCKED_BY_RECEIPT_DATA_CONTRACT",
                "reason_codes": ["baseline_infra_invalid:receipt_data_contract_violation"],
                "baseline": {"receipt_data_contract_missing": ["drone"]},
                "challenger": {"receipt_data_contract_missing": ["drone"]},
            },
            {"capability": "codeintel", "verdict": "APPROVE_HEEP_MODE_CANDIDATE", "reason_codes": []},
        ]
    }

    queue = build_heep_mat_b_blocker_resolution_queue(mat_b_report=report)

    assert queue["summary"]["blocked_count"] == 2
    assert queue["summary"]["decided_count"] == 1
    assert queue["summary"]["provider_token_truth_replay_count"] == 1
    assert queue["summary"]["receipt_invocation_replay_count"] == 1
    rows = {row["capability"]: row for row in queue["queue"]}
    assert rows["xray"]["lane"] == "PROVIDER_TOKEN_TRUTH_REPLAY"
    assert rows["xray"]["can_update_runtime_before_replay"] is False
    assert rows["drone"]["lane"] == "RECEIPT_INVOCATION_REPLAY"
    assert rows["drone"]["missing_expected_capabilities"] == ["drone"]
    assert queue["summary"]["public_benchmark_allowed"] is False
