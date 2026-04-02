from pathlib import Path
import os
import json
import pytest
from nexus.core.state_io import StateIO
from nexus.core.state_contracts import NexusState

@pytest.fixture
def temp_repo(tmp_path):
    """建立臨時專案目錄進行測試。"""
    repo = tmp_path / "test_project"
    repo.mkdir()
    return repo

def test_state_io_lifecycle(temp_repo):
    """測試 StateIO 的載入與保存循環。"""
    io = StateIO(str(temp_repo))
    
    # 1. 預設狀態測試
    state = io.load_global_state()
    assert isinstance(state, NexusState)
    assert state.task_id == "new-task"
    assert state.current_phase is None
    
    # 2. 修改狀態測試
    state.current_phase = "D"
    state.skills_used.append({"skill": "test", "score": 1.0})
    io.save_global_state(state)
    
    # 3. 重新載入驗證
    reloaded = io.load_global_state()
    assert reloaded.current_phase == "D"
    assert len(reloaded.skills_used) == 1
    assert reloaded.skills_used[0]["skill"] == "test"

def test_state_io_file_creation(temp_repo):
    """測試 .musestate 是否正確建立。"""
    io = StateIO(str(temp_repo))
    state_file = io.state_file
    
    assert not state_file.exists()
    io.load_global_state() # 觸發預設載入但不保存
    assert not state_file.exists() 
    
    io.save_global_state(NexusState(task_id="test-task-001"))
    assert state_file.exists()
