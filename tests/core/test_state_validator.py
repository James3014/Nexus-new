import pytest
from unittest.mock import MagicMock
from nexus.core.state_validator import StateValidator

def test_state_validator_forbidden_transition_p_to_r():
    """驗證非法狀態轉移：禁止從 P 直接跳到 R。"""
    state = MagicMock()
    state.batch_id = None
    state.steps_history = [MagicMock(phase="P")]
    state.current_phase = "R"
    
    with pytest.raises(ValueError, match="Forbidden Transition"):
        StateValidator.validate_protocols(state)

def test_state_validator_legal_transition_p_to_d():
    """驗證合法狀態轉移：P -> D。"""
    state = MagicMock()
    state.batch_id = None
    state.steps_history = [MagicMock(phase="P")]
    state.current_phase = "D"
    
    # 應正常通過，不拋出異常
    StateValidator.validate_protocols(state)

def test_state_validator_budget_check():
    """驗證 Batch 模式下的預算限制。"""
    state = MagicMock()
    state.batch_id = "B123"
    state.current_phase = "P"
    state.config.budget_token = 0
    state.steps_history = []
    
    with pytest.raises(ValueError, match="budget_token > 0"):
        StateValidator.validate_protocols(state)

def test_state_validator_shortcut_matrix():
    """驗證轉移矩陣中的多個禁地。"""
    state = MagicMock()
    state.batch_id = None
    
    # D -> C (非法)
    state.steps_history = [MagicMock(phase="D")]
    state.current_phase = "C"
    with pytest.raises(ValueError, match="shortcut detected from D to C"):
        StateValidator.validate_protocols(state)
        
    # X -> A (非法)
    state.steps_history = [MagicMock(phase="X")]
    state.current_phase = "A"
    with pytest.raises(ValueError, match="shortcut detected from X to A"):
        StateValidator.validate_protocols(state)
