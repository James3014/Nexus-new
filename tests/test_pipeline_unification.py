import pytest
from unittest.mock import MagicMock
from nexus.engine.coordinator import NexusEngine
from nexus.core.state_contracts import NexusState

from nexus.engine.config import EngineConfig

@pytest.fixture
def engine(tmp_path):
    # Setup a mock project root and engine
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cases").mkdir()
    return NexusEngine(EngineConfig(project_root=project_root))

def test_pipeline_bug_flow(engine, monkeypatch):
    # Mock handlers and state_io to simulate a bug run
    mock_state = NexusState(task_id="test-bug")
    engine.state_io.load_global_state = MagicMock(return_value=mock_state)
    engine.state_io.save_global_state = MagicMock()
    
    # Mock internal phase logic if possible or just check if it calls the right things
    # For now, we want to ensure run_bug actually calls the new pipeline
    # We can use a spy if we had one, but let's just run it and see if it works
    # once refactored.
    pass

def test_unified_pipeline_exists(engine):
    assert hasattr(engine, "_run_task_pipeline")
