import pytest
from nexus.core.context_hub import ContextHub
from nexus.core.state_contracts import NexusState, StepRecord
from datetime import datetime

def test_toon_renderer_compression():
    """驗證 ContextHub 的 TOON 壓縮功能 (Phase 3 RED)"""
    hub = ContextHub(".", run_dir="/tmp/nexus_run")
    state = NexusState(task_id="test-compression")
    
    # 注入大量歷史記錄
    for i in range(20):
        state.steps_history.append(StepRecord(
            phase="P", step_id=f"P-{i}", status="completed", 
            started_at=datetime.now(), summary=f"Very long summary for step {i} that should be compressed..."
        ))
    
    # 執行組裝 (假設 assemble_feature_pack 會調用 ToonRenderer)
    pack = hub.assemble_feature_pack()
    
    # 驗證歷史是否被壓縮 (TOON 視圖應該只顯示最近的或摘要)
    # 目前先預期它會有一個 [TOON_SUMMARY] 欄位
    assert "TOON_SUMMARY" in pack
    assert len(pack["TOON_SUMMARY"]) < 500 # 壓縮後應明顯變小
