from __future__ import annotations

from scripts.ops.build_heep_mat_b_update_packets import build_heep_mat_b_update_packets


def test_heep_mat_b_update_packets_promote_only_approved_modes() -> None:
    report = {
        "comparisons": [
            {
                "capability": "codeintel",
                "baseline_row_id": "base",
                "challenger_row_id": "challenger",
                "verdict": "APPROVE_HEEP_MODE_CANDIDATE",
                "reason_codes": [],
            },
            {
                "capability": "research",
                "baseline_row_id": "base-r",
                "challenger_row_id": "challenger-r",
                "verdict": "REJECT_MULTI_SKILL",
                "reason_codes": ["reliability_not_better_or_delivery_return"],
            },
            {
                "capability": "sandbox_replay",
                "baseline_row_id": "base-s",
                "challenger_row_id": "challenger-s",
                "verdict": "HOLD_MISSING_MAT_B_EVIDENCE",
                "reason_codes": ["baseline_infra_invalid:model_call_without_tokens"],
            },
        ]
    }
    map_gate = {
        "rows": [
            {"capability": "codeintel", "heep_mode_candidate": "Mode C (Swarm)", "map_update_allowed": True},
            {"capability": "research", "heep_mode_candidate": "Mode B (Guard)", "map_update_allowed": True},
            {"capability": "sandbox_replay", "heep_mode_candidate": "Mode B (Guard)", "map_update_allowed": True},
        ]
    }
    apply_packet = {
        "rows": [
            {"capability": "codeintel", "selected_mode": "Mode C (Swarm)", "disposition": "PENDING"},
            {"capability": "research", "selected_mode": "Mode B (Guard)", "disposition": "PENDING"},
            {"capability": "sandbox_replay", "selected_mode": "Mode B (Guard)", "disposition": "PENDING"},
        ]
    }

    packets = build_heep_mat_b_update_packets(mat_b_report=report, map_gate=map_gate, apply_packet=apply_packet)

    apply_rows = {row["capability"]: row for row in packets["apply_packet"]["rows"]}
    map_rows = {row["capability"]: row for row in packets["map_gate"]["rows"]}
    assert apply_rows["codeintel"]["disposition"] == "READY_FOR_RUNTIME_APPLY_REVIEW"
    assert apply_rows["codeintel"]["runtime_update_allowed"] is False
    assert map_rows["research"]["heep_mode_candidate"] == "Mode A (Solo)"
    assert map_rows["research"]["map_update_allowed"] is True
    assert map_rows["sandbox_replay"]["map_update_allowed"] is False
    assert packets["catalog"]["summary"]["approved_mode_candidate_count"] == 1
