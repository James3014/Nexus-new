from __future__ import annotations

import json
import pytest
from pathlib import Path
from scripts.local_heal.run_june_regression_pack import run_pack, repo_root

def test_real_model_wiring_probe_contract() -> None:
    """
    Phase 56G.0 — A/B/C Wiring Probe Contract Verification
    """
    # 執行 real_model 探針
    res = run_pack(replay_mode="real_model")
    
    assert res["status"] == "completed"
    results = res["results"]
    
    # 1. 斷言只執行了 astropy-13236 單一任務
    assert len(results) == 1, f"Probe should only run astropy-13236, got {len(results)}"
    probe_task = results[0]
    assert probe_task["task_id"] == "astropy__astropy-13236"
    
    # 2. 確保 replay_mode 為 real_model
    assert probe_task["replay_mode"] == "real_model"
    
    # 3 & 4. 確保 mock_oracle / oracle_patch 未被使用
    assert probe_task["mock_oracle_used"] is False
    assert probe_task["oracle_patch_used"] is False
    
    # 5. 確保 phase_trace 欄位存在
    assert "phase_trace" in probe_task
    trace = probe_task["phase_trace"]
    
    # 6. 確保 phase_trace 包含所有 required phases
    required_phases = ["reproduction", "planning", "localization", "patch_synthesis", "verification"]
    for phase_name in required_phases:
        assert phase_name in trace, f"Missing required phase: {phase_name}"
        p = trace[phase_name]
        assert "name" in p
        assert "class_name" in p
        assert "is_fake" in p
        assert "ran" in p
        assert "success" in p
        assert "receipt_present" in p

    # 7. 如果有任何 phase 是 FakePhase，驗證限制
    has_fake = any(p["is_fake"] is True for p in trace.values())
    if has_fake:
        # used_full_phase_sequence 必須是 False
        assert probe_task["used_full_phase_sequence"] is False, "used_full_phase_sequence must be False if any phase is fake"
        
        # classification 不得是 REAL_MODEL_MAINLINE_PASS
        assert probe_task["final_classification"] != "REAL_MODEL_MAINLINE_PASS"
        
        # classification 必須是 WIRING_GAP 或 SEAM_SMOKE_ONLY 或 INFRA_BLOCKED
        allowed_classes_with_fake = {"WIRING_GAP", "SEAM_SMOKE_ONLY", "INFRA_BLOCKED"}
        assert probe_task["final_classification"] in allowed_classes_with_fake, (
            f"Invalid classification when fake phase exists: {probe_task['final_classification']}"
        )

    # 8. 若 used_full_phase_sequence 為 True，所有 required phases 必須是 non-fake 且 receipt_present = True
    if probe_task["used_full_phase_sequence"] is True:
        for phase_name in required_phases:
            p = trace[phase_name]
            assert p["is_fake"] is False, f"Phase {phase_name} must not be fake if used_full_phase_sequence is True"
            assert p["receipt_present"] is True, f"Phase {phase_name} must have receipt if used_full_phase_sequence is True"

    # 9 & 10. 本測試不要求 solved/pass，且不把 FakePhase 當作 A/B/C 已接好
    # 我們在此處只驗收合約架構的正直性與精準的 final_classification 標記
    print(f"\n✅ Real Model Wiring Probe Contract Verification Passed.")
    print(f"   Task: {probe_task['task_id']}")
    print(f"   Classification: {probe_task['final_classification']}")
    print(f"   Verdict: {probe_task['final_verdict']}")
    print(f"   Phase Trace:")
    for name in required_phases:
        p = trace[name]
        print(f"     - {name}: ran={p['ran']}, is_fake={p['is_fake']}, success={p['success']}, receipt_present={p['receipt_present']}")
