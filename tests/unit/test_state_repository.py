import pytest
import os
from pathlib import Path
from nexus.core.state_repository import StateRepository
from nexus.core.state_contracts import NexusState

def test_state_repository_save_load(tmp_path):
    repo = StateRepository(tmp_path / "state.json")
    state = NexusState(task_id="test-123")
    repo.save(state)
    
    loaded = repo.load()
    assert loaded.task_id == "test-123"

def test_state_repository_fail_closed_on_corruption(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text("{ corrupt json data", encoding="utf-8")
    
    repo = StateRepository(state_file)
    with pytest.raises(RuntimeError) as exc_info:
        repo.load()
    assert "State corruption detected" in str(exc_info.value)
