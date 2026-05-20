from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.ops import build_heep_mat_b_closure_packets as closure


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_executor_trio_status_classifies_failed_replay(tmp_path: Path) -> None:
    replay_root = tmp_path / "replay"
    _write(replay_root / "live_summary.json", {"status": "RETURN", "summary": {"planned_rows": 6, "completed_rows": 1}})
    _write(
        replay_root / "row" / "failed.row.json",
        {
            "row_id": "heep::drone::task::mode_a",
            "status": "FAILED",
            "skill_mount_contract_status": "RETURN",
            "token_data_contract_status": "DATA_CONTRACT_VIOLATION",
            "token_data_contract_reason": "model_call_without_measured_provider_tokens",
            "expected_capability_receipt_coverage": {"missing": ["drone"]},
        },
    )

    out = closure.build_executor_trio_replay_status(replay_root=replay_root)

    assert out["status"] == "BLOCKED"
    assert out["first_blocker"]["capability"] == "drone"
    assert "model_call_without_measured_provider_tokens" in out["first_blocker"]["blocker_reasons"]
    assert "missing_expected_capability_receipts:drone" in out["first_blocker"]["blocker_reasons"]
    assert out["summary"]["public_benchmark_allowed"] is False


def test_closure_packets_keep_runtime_and_public_blocked(tmp_path: Path) -> None:
    final_decisions = tmp_path / "final.json"
    runtime_packet = tmp_path / "runtime.json"
    replay_root = tmp_path / "replay"
    _write(
        final_decisions,
        {
            "decisions": [
                {"capability": "xray", "decision": "USE_MULTI_SKILL", "selected_mode": "multi", "selected_skill_ids": ["a", "b"]},
                {"capability": "drone", "decision": "USE_SINGLE_PRIMARY_FALLBACK", "selected_mode": "single", "selected_skill_ids": ["c"]},
            ]
        },
    )
    _write(runtime_packet, {"summary": {"ready_for_runtime_apply_review_count": 1}, "rows": [{"capability": "codeintel"}]})
    _write(replay_root / "live_summary.json", {"status": "RETURN", "summary": {"planned_rows": 6, "completed_rows": 1}})
    _write(replay_root / "row" / "failed.row.json", {"status": "FAILED", "capability": "drone"})

    args = SimpleNamespace(
        final_decisions=str(final_decisions),
        runtime_packet=str(runtime_packet),
        replay_root=str(replay_root),
        replay_status_output=str(tmp_path / "replay_status.json"),
        rollup_output=str(tmp_path / "rollup.json"),
        mode_gate_output=str(tmp_path / "mode_gate.json"),
        runtime_review_output=str(tmp_path / "runtime_review.json"),
        public_gate_output=str(tmp_path / "public_gate.json"),
        taskcard_status_output=str(tmp_path / "taskcards.json"),
    )
    artifacts = closure.build_all(args)

    assert artifacts["rollup"]["summary"]["internal_multi_skill_selection_count"] == 1
    assert artifacts["mode_gate"]["summary"]["single_fallback_count"] == 1
    assert artifacts["runtime_review"]["summary"]["hold_for_provider_clean_count"] == 1
    assert artifacts["runtime_review"]["summary"]["hold_for_skill_specific_replay_count"] == 1
    assert artifacts["public_gate"]["status"] == "BLOCKED"
    assert artifacts["public_gate"]["summary"]["public_benchmark_allowed"] is False
    assert artifacts["taskcard_status"]["summary"]["taskcard_count"] == 6
    assert artifacts["taskcard_status"]["summary"]["blocked_count"] == 5
