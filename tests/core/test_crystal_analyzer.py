import pytest
from unittest.mock import MagicMock
from nexus.core.crystal_analyzer import TraumaEngine

def test_trauma_engine_process_failures():
    """驗證 TraumaEngine 是否能正確識別 A 階段失敗並更新權重。"""
    state = MagicMock()
    
    # 建立一個失敗的 A 階段紀錄
    step_a = MagicMock()
    step_a.phase = "A"
    step_a.status = "rejected"
    step_a.metadata = {"error_type": "ValidationError"}
    
    state.steps_history = [step_a]
    state.autonomic_weights.trauma_records = []
    state.retry_count = 1
    
    TraumaEngine.process_failures(state)
    
    # 應新增一筆 Trauma 紀錄
    assert len(state.autonomic_weights.trauma_records) == 1
    assert state.autonomic_weights.trauma_records[0].failure_signature == "ValidationError"
    # 計算 Learning Velocity: 1.0 - (1 * 0.2) - (1 * 0.1) = 0.7
    assert pytest.approx(state.learning_velocity) == 0.7

def test_trauma_engine_success_no_trauma():
    """驗證當 A 階段成功時不應產生 Trauma。"""
    state = MagicMock()
    
    step_a = MagicMock()
    step_a.phase = "A"
    step_a.status = "passed"
    
    state.steps_history = [step_a]
    state.autonomic_weights.trauma_records = []
    
    TraumaEngine.process_failures(state)
    assert len(state.autonomic_weights.trauma_records) == 0

def test_trauma_engine_empty_history():
    """驗證當沒有歷史紀錄時不應崩潰。"""
    state = MagicMock()
    state.steps_history = []
    
    TraumaEngine.process_failures(state) # 應不報錯
