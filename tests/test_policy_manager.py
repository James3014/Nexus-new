import pytest
from nexus.core.policy_manager import PolicyManager
from nexus.core.state_contracts import NexusState

def test_policy_hit_os_rule():
    """驗證 PolicyManager 能根據任務描述命中規則 (Week 2 M2)"""
    pm = PolicyManager(".")
    state = NexusState(task_id="test-os-task")
    
    # 模擬包含 'os' 的任務描述
    pm.apply_policy_to_state(state, "Fix missing os.path imports in utils.py")
    
    # 驗證
    assert state.policy_applied is True
    assert "POL-001" in state.policy_hit_ids
    print(f"✅ Policy hit success: {state.policy_hit_ids}")

def test_episode_recording():
    """驗證 Episode 能正確寫入文件 (Week 1 M1)"""
    pm = PolicyManager(".")
    state = NexusState(task_id="test-episode-1")
    state.health_score = 95.0
    
    pm.record_episode(state)
    
    assert pm.episode_file.exists()
    print(f"✅ Episode recorded to: {pm.episode_file}")
