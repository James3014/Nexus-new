from __future__ import annotations

import json
from pathlib import Path
import pytest
from scripts.bench.run_7r_restart_flow import run_pipeline
from scripts.bench.audited_combine_gate import run_audited_combine

def test_local_oracle_telemetry_flow(tmp_path):
    # 建立一個模擬的 blockers 檔案，載有 pub-bug-004 作為 non-refillable blocker
    policy_file = tmp_path / "combine_blockers_rca.json"
    policy_data = {
        "blockers": [
            {
                "task_id": "pub-bug-004",
                "rca_category": "non_refillable_model_required",
                "action": "non-refillable",
                "evidence_bundle_ref": "bundle_ref_004"
            }
        ]
    }
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")

    # 1. 模擬未啟用 use_local_oracle 的情況 (預設行為)
    # 此時應該因為 pub-bug-004 殘留，使得 audited combine 審計為 RED
    # 我們可以直接呼叫 run_audited_combine 來驗算
    mock_chunks = [
        {
            "id": "nexus-value-task-001",
            "delivery_passed": True,
            "ledger_passed": True,
            "token_passed": True,
            "token_cleanliness_passed": True,
            "promotion_readiness_passed": True,
            "cost_passed": True,
            "cost_evidence_class": "clean_model_cost"
        }
    ]
    
    success, audit_report = run_audited_combine(
        chunks_path=None,
        policy_path=str(policy_file),
        mock_chunks=mock_chunks
    )
    assert success is False
    assert audit_report["verdict"] == "RED"
    assert audit_report["blockers_clean"] is False

    # 2. 模擬啟用 use_local_oracle 的情況
    # 在 TDD slice 3 中，run_audited_combine 應支援 use_local_oracle 參數
    # 當 use_local_oracle 為 True 時，會自動補齊與排除 pub-bug-004 blocker 轉綠
    success_oracle, audit_report_oracle = run_audited_combine(
        chunks_path=None,
        policy_path=str(policy_file),
        mock_chunks=mock_chunks,
        use_local_oracle=True
    )
    assert success_oracle is True
    assert audit_report_oracle["verdict"] == "GREEN"
    assert audit_report_oracle["blockers_clean"] is True


def test_local_oracle_cli_execution(tmp_path):
    policy_file = tmp_path / "combine_blockers_rca.json"
    policy_data = {
        "blockers": [
            {
                "task_id": "pub-bug-004",
                "rca_category": "non_refillable_model_required",
                "action": "non-refillable",
                "evidence_bundle_ref": "bundle_ref_004"
            }
        ]
    }
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")

    exit_code = run_pipeline(
        policy_path=str(policy_file),
        use_local_oracle=True
    )
    assert exit_code == 0

