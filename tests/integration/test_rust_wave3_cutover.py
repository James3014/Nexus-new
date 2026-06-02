import os
import json
import pytest
from pathlib import Path
from nexus.bridge.cutover_manager import RustCutoverManager

class MockFSM:
    def validate_transition(self, current, next_state):
        # 模擬 Python 端的合法性檢查
        from nexus.engine.capability_contracts import FlowState
        if current == FlowState.INTAKE and next_state == FlowState.PLAN:
            return True
        return False

@pytest.fixture
def temp_ledger(tmp_path):
    return tmp_path / "mismatch_ledger.jsonl"

def test_dual_run_matches(temp_ledger):
    # Arrange: 啟用 Dual-run
    os.environ["RUST_DUAL_RUN"] = "1"
    os.environ["USE_RUST_FLOW_ENGINE"] = "0"
    os.environ["RUST_PRIMARY_ONLY"] = "0"
    
    manager = RustCutoverManager(ledger_path=temp_ledger)
    fsm = MockFSM()
    
    # Act: 執行一個兩邊一致的轉移 (INTAKE -> PLAN)
    result = manager.validate_flow_transition("INTAKE", "PLAN", py_fsm=fsm)
    
    # Assert
    assert result is True
    assert not temp_ledger.exists() # 無 Mismatch 不應產出檔案

def test_dual_run_mismatch_recording(temp_ledger):
    # Arrange: 啟用 Dual-run，但讓兩邊不一致
    os.environ["RUST_DUAL_RUN"] = "1"
    
    manager = RustCutoverManager(ledger_path=temp_ledger)
    fsm = MockFSM()
    
    # Act: 執行一個兩邊不一致的轉移 (INTAKE -> EXECUTE)
    # Python 回傳 False, Rust 回傳 False (因為非法轉移)
    # 我們需要模擬一個 Rust 回傳 True 但 Python 回傳 False 的情況來測試 Mismatch
    # 這裡我們模擬 INTAKE -> CLARIFY，假設 Rust 判定為 True, Python 也判定為 True，
    # 為了測試 Mismatch，我們手動觸發一個不匹配的調用
    
    # 在當前的 Rust 實作中，INTAKE -> PLAN 是 True
    # 如果我們讓 Python 回傳 False，就會觸發 Mismatch
    
    result = manager.validate_flow_transition("INTAKE", "PLAN", py_fsm=None) # py_fsm=None 會讓 _legacy 回傳 True
    # 這裡兩邊都回傳 True，匹配。
    
    # 模擬 Mismatch: INTAKE -> CLOSE
    # Rust 回傳 False (非法), Python 回傳 True (模擬)
    class DivergentFSM:
        def validate_transition(self, c, n): return True
        
    result = manager.validate_flow_transition("INTAKE", "CLOSE", py_fsm=DivergentFSM())
    
    # Assert
    assert result is True # 回傳 Python 結果，因為 USE_RUST_FLOW=0
    assert temp_ledger.exists()
    
    with open(temp_ledger, "r") as f:
        ledger_data = json.loads(f.read())
        assert ledger_data["module_name"] == "flow_machine"
        assert ledger_data["match"] is False
        assert ledger_data["diff_reason"] == "OUTPUT_VALUE_MISMATCH"

def test_primary_only_cutover():
    # Arrange: 啟用 Primary Only
    os.environ["RUST_PRIMARY_ONLY"] = "1"
    os.environ["USE_RUST_FLOW_ENGINE"] = "1"
    
    manager = RustCutoverManager()
    
    # Act
    result = manager.validate_flow_transition("INTAKE", "PLAN")
    
    # Assert
    assert result is True # 直接回傳 Rust 結果
