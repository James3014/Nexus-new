from __future__ import annotations

import tempfile
import json
from pathlib import Path
from scripts.bench.audited_combine_gate import run_audited_combine


def test_combine_telemetry_missing_fail_closed():
    """
    測試當 telemetry 缺失時，即使其餘指標正常且無 blocker 殘留，
    整個 combine 也必須維持 RED (fail-closed)。
    """
    # 建立 10 個乾淨的 chunks，但其中第 5 個 chunk 的 token_cleanliness_passed 為 False
    mock_chunks = []
    for i in range(10):
        mock_chunks.append({
            "id": f"chunk-{i}",
            "delivery_passed": True,
            "cost_passed": True,
            "ledger_passed": True,
            "token_passed": True,
            "token_cleanliness_passed": True if i != 5 else False, # 故意第 5 個 chunk 為 False
            "promotion_readiness_passed": True
        })

    # 使用一個臨時的空白 policy JSON 以保證 blocker 零殘留
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = Path(tmpdir) / "blockers.json"
        with open(policy_path, "w") as f:
            json.dump({"blockers": []}, f)

        success, report = run_audited_combine(
            chunks_path=None,
            policy_path=policy_path,
            mock_chunks=mock_chunks
        )
        
        assert success is False
        assert report["verdict"] == "RED"
        assert report["five_dimensions_ok"] is False
        assert report["blockers_clean"] is True


def test_combine_blockers_remained_fail_closed():
    """
    測試當 100/100 Chunks 全 PASS 且 telemetry 乾淨，
    但有 non-refillable blocker 殘留時，整體 combine 必須維持 RED (fail-closed)。
    """
    # 建立 10 個全部 PASS 的 chunks
    mock_chunks = []
    for i in range(10):
        mock_chunks.append({
            "id": f"chunk-{i}",
            "delivery_passed": True,
            "cost_passed": True,
            "ledger_passed": True,
            "token_passed": True,
            "token_cleanliness_passed": True,
            "promotion_readiness_passed": True
        })

    # 模擬有一個 non-refillable blocker 殘留
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = Path(tmpdir) / "blockers.json"
        with open(policy_path, "w") as f:
            json.dump({
                "blockers": [
                    {
                        "task_id": "pub-bug-004",
                        "rca_category": "non_refillable_model_required",
                        "action": "non-refillable",
                        "reasons": "causality blocker",
                        "evidence_bundle_ref": "evidence://ref"
                    }
                ]
            }, f)

        success, report = run_audited_combine(
            chunks_path=None,
            policy_path=policy_path,
            mock_chunks=mock_chunks
        )
        
        assert success is False
        assert report["verdict"] == "RED"
        assert report["five_dimensions_ok"] is True  # 五維全過
        assert report["blockers_clean"] is False     # 但有 blocker 殘留


def test_combine_all_pass_turn_green():
    """
    測試當五維度全 PASS，且零 blockers 殘留時，
    整體 combine 順利轉 GREEN！
    """
    mock_chunks = []
    for i in range(10):
        mock_chunks.append({
            "id": f"chunk-{i}",
            "delivery_passed": True,
            "cost_passed": True,
            "ledger_passed": True,
            "token_passed": True,
            "token_cleanliness_passed": True,
            "promotion_readiness_passed": True
        })

    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = Path(tmpdir) / "blockers.json"
        with open(policy_path, "w") as f:
            json.dump({"blockers": []}, f) # 零殘留

        success, report = run_audited_combine(
            chunks_path=None,
            policy_path=policy_path,
            mock_chunks=mock_chunks
        )
        
        assert success is True
        assert report["verdict"] == "GREEN"
        assert report["five_dimensions_ok"] is True
        assert report["blockers_clean"] is True
