import pytest
from unittest.mock import patch, MagicMock
from nexus.core.policy_manager import PolicyManager
from nexus.core.state_contracts import NexusState

@pytest.fixture
def mock_state():
    # 🧬 模擬 NexusState 物件性質分析性質內容。
    state = MagicMock(spec=NexusState)
    state.metadata = {}
    state.intent = ""
    state.policy_applied = False
    return state

def test_safe_intent_bridge(mock_state):
    """驗證 SAFE 意圖之物理導通"""
    mock_state.intent = "read /tmp/task_plan.json"
    pm = PolicyManager(project_root=".")
    
    # 🛡️ 模擬 sentinel 回傳 SAFE (S)
    with patch('nexus.plugins.sentinel_plugin.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {"content": "S"}
        pm.apply_policy_to_state(mock_state, "test description")
        
    assert mock_state.metadata.get("neural_veto") is False
    assert mock_state.metadata["neural_veto"] == False

def test_risk_intent_bridge(mock_state):
    """驗證 RISK 意圖之物理攔截"""
    mock_state.intent = "rm -rf str(__import__("pathlib").Path(__file__).resolve().parents[2])"
    pm = PolicyManager(project_root=".")
    
    # 🛡️ 模擬 sentinel 回傳 RISK (R)
    with patch('nexus.plugins.sentinel_plugin.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {"content": "R"}
        pm.apply_policy_to_state(mock_state, "test description")
        
    assert mock_state.metadata.get("neural_veto") is True
    assert mock_state.policy_applied is False

def test_sentinel_offline_fallback(mock_state):
    """驗證哨兵離線時之 Fail-open 導通 (SAFE-first)"""
    mock_state.intent = "critical action"
    pm = PolicyManager(project_root=".")
    
    # 🛡️ 模擬網路異常/離線性能分析。
    with patch('nexus.plugins.sentinel_plugin.requests.post') as mock_post:
        mock_post.side_effect = Exception("Connection refused")
        pm.apply_policy_to_state(mock_state, "test description")
        
    # 🧬 Fail-open: 離線時應為 False (SAFE) 性質內容。內容且性能。
    assert mock_state.metadata.get("neural_veto") is False
