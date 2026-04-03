"""
🛡️ Nexus P2-C Physical Simulation: Planner 整合與 Fallback 驗證 (Day 9)
驗證 metadata 結構穩定性與向量庫中斷時的 Fail-Closed 能力。
"""

import os
import json
import shutil
from pathlib import Path
from nexus.engine.phases.planner import PlannerPhaseHandler

def run_phys_sim():
    repo_root = Path("/Users/jameschen/Workspace/nexus")
    # 模擬 PlannerPhaseHandler 需要初始化參數
    planner = PlannerPhaseHandler(str(repo_root), str(repo_root / ".nexus" / "runs" / "test_run"))
    
    # --- 場景 A: 有診斷資訊時的自癒增強 ---
    print("\n🚀 [Sim:A] Testing Planner with Diagnosis (Predictive Self-Healing)")
    state_a = {
        "goal": "Fix authentication stability issues",
        "diagnosis": {
            "phase": "R",
            "traceback_snippet": "auth timeout in UTC comparison",
            "primary_category": "AUTH",
            "status": "FAILED"
        },
        "context": {},
        "metadata": {}
    }
    
    # 模擬執行 Planner 核心片段 (或者是直接 call run_internal)
    # 這裡我們模擬執行，並檢查 metadata 是否被 planner 注入
    # PlannerPhaseHandler.run(state, context) -> 
    # 因為 state 是 pydantic model，我們這裡模擬一個簡單的 object
    class MockState:
        def __init__(self, metadata): self.metadata = metadata
        def task_id(self): return "TASK_TEST"
    
    # 這裡我們直接測量 Planner 內部的邏輯會修改 state.metadata
    mock_state_a = MockState(state_a["metadata"])
    planner.run(mock_state_a, state_a)
    
    meta = mock_state_a.metadata
    print(f"📊 Metadata Keys: {list(meta.keys())}")
    
    # 驗證 P2-C 關鍵欄位 (對齊 v22 穩定性)
    assert "health_insights" in meta
    assert "repair_recommendations" in meta
    assert "phase_health_score" in meta
    assert "repair_template_count" in meta
    
    print(f"✅ [Sim:A] Health Score: {meta['phase_health_score']:.2f}")
    print(f"✅ [Sim:A] Repair Templates: {meta['repair_template_count']}")
    
    # --- 場景 B: 斷路測試 (LanceDB Fallback) ---
    print("\n🚀 [Sim:B] Testing LanceDB Fallback (Fail-Closed)")
    memory_dir = repo_root / ".nexus" / "memory"
    backup_dir = repo_root / ".nexus" / "memory_bak"
    
    try:
        # 移走向量庫模擬損壞/消失
        if memory_dir.exists():
            shutil.move(str(memory_dir), str(backup_dir))
        
        state_b = {
            "goal": "Verify fallback",
            "diagnosis": {"phase": "X", "traceback_snippet": "fallback check"},
            "context": {},
            "metadata": {}
        }
        
        mock_state_b = MockState(state_b["metadata"])
        planner.run(mock_state_b, state_b)
        
        # 檢查是否退回 legacy
        res = mock_state_b.metadata.get("lesson_resolution", {})
        backend = res.get("backend_used")
        print(f"📊 Backend Used: {backend}")
        
        # P2-B 規格：當 LanceDB 不可用時應退回 'legacy'
        assert backend == "legacy"
        print("✅ [Sim:B] Fallback to Legacy Successful")
        
    finally:
        # 恢復向量庫
        if backup_dir.exists():
            if memory_dir.exists():
                shutil.rmtree(str(memory_dir))
            shutil.move(str(backup_dir), str(memory_dir))

    print("\n🏆 [E2E:SUCCESS] Nexus P2-C Checkout is complete and stable.")

if __name__ == "__main__":
    run_phys_sim()
