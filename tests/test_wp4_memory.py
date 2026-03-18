import pytest
from nexus.core.memory.schema import EpisodicMemory
from datetime import datetime

def test_episodic_memory_validation():
    data = {
        "run_id": "run-001",
        "task_id": "task-001",
        "state_before": {"status": "start"},
        "action": {"cmd": "ls"},
        "state_after": {"status": "done"},
        "reward": 1.0,
        "timestamp": datetime.now()
    }
    memory = EpisodicMemory(**data)
    assert memory.run_id == "run-001"
    assert memory.reward == 1.0
    
def test_episodic_memory_json_schema():
    # Pydantic v2 uses model_json_schema()
    schema = EpisodicMemory.model_json_schema()
    assert "run_id" in schema["properties"]
    assert "task_id" in schema["properties"]
    assert "state_before" in schema["properties"]
    assert "action" in schema["properties"]
    assert "state_after" in schema["properties"]
    assert "reward" in schema["properties"]
    assert "timestamp" in schema["properties"]

def test_episodic_memory_missing_field():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        # Missing run_id
        EpisodicMemory(task_id="task-1", action={})
