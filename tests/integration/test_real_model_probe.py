from __future__ import annotations

import json
import pytest
from pathlib import Path
from scripts.local_heal.run_june_regression_pack import run_pack, repo_root

def test_real_model_wiring_probe() -> None:
    """
    Phase 56G — Real Model A/B/C Wiring Probe Test
    
    這個測試的目的在於：
    1. 驗證實體模型模式（real_model）下只會執行單一探針任務 astropy-13236。
    2. 確保結果僅限四大輸出分類：REAL_MODEL_MAINLINE_PASS, REAL_MODEL_CONTROLLED_FAIL, INFRA_BLOCKED, WIRING_GAP.
    3. 斷言關鍵的 A/B/C 主路徑證據鏈欄位完整性。
    """
    # 執行 real_model 探針
    res = run_pack(replay_mode="real_model")
    
    assert res["status"] == "completed"
    results = res["results"]
    
    # 斷言只執行了 astropy-13236 單一任務
    assert len(results) == 1, f"Probe task should only run 1 task, got {len(results)}"
    probe_task = results[0]
    assert probe_task["task_id"] == "astropy__astropy-13236"
    assert probe_task["june_group"] == "A_PASSED"
    assert probe_task["replay_mode"] == "real_model"
    assert probe_task["mock_oracle_used"] is False
    assert probe_task["oracle_patch_used"] is False
    
    # 四大分類限制
    ALLOWED_CLASSIFICATIONS = {
        "REAL_MODEL_MAINLINE_PASS",
        "REAL_MODEL_CONTROLLED_FAIL",
        "INFRA_BLOCKED",
        "WIRING_GAP",
    }
    
    fc = probe_task["final_classification"]
    assert fc in ALLOWED_CLASSIFICATIONS, f"Invalid classification for real model probe: {fc}"
    
    # 嚴防假宣稱
    assert fc != "MAINLINE_RECOVERED"
    assert fc != "FULL_MAINLINE_RECOVERED"
    assert fc != "MOCK_ORACLE_REPLAY_PASS"
    assert fc != "MOCK_ORACLE_REPLAY_FAIL"
    
    # 檢查核心 telemetry 欄位
    assert "used_heal_orchestrator_run" in probe_task
    assert "used_full_phase_sequence" in probe_task
    assert "used_reproduction_phase" in probe_task
    assert "used_planning_phase" in probe_task
    assert "used_localization_phase" in probe_task
    assert "used_patch_synthesis_phase" in probe_task
    assert "used_verification_phase" in probe_task
    
    # 輸出正直報告
    print(f"\n📡 Probe Task Real Evidence Result:")
    print(f"   Task ID: {probe_task['task_id']}")
    print(f"   Final Classification: {fc}")
    print(f"   Final Verdict: {probe_task['final_verdict']}")
    print(f"   Real Model Called: {probe_task['real_model_called']}")
    print(f"   Used HealOrchestrator Run: {probe_task['used_heal_orchestrator_run']}")
    print(f"   Patch Evidence: {probe_task.get('patch_applied_evidence')}")
