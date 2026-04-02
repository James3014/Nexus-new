from pathlib import Path
import json
import os
import pytest
from nexus.core.memory.ingest import ingest_task_result
from nexus.core.memory.schema import EpisodicMemory

@pytest.fixture
def mock_task_result(tmp_path):
    run_id = "test-run-123"
    run_dir = tmp_path / ".nexus" / "runs" / run_id
    run_dir.mkdir(parents=True)
    
    task_result = {
        "task_id": "test-task-456",
        "state_before": {"status": "init"},
        "action": {"type": "test_action"},
        "state_after": {"status": "done"},
        "reward": 1.0,
        "timestamp": "2024-03-19T12:00:00Z"
    }
    
    result_file = run_dir / "task_result.json"
    with open(result_file, "w") as f:
        json.dump(task_result, f)
    
    return run_id, str(result_file)

def test_ingest_task_result(mock_task_result, tmp_path):
    run_id, task_result_path = mock_task_result
    output_path = tmp_path / "episodic_memory.jsonl"
    
    # Run ingestion
    ingest_task_result(run_id, task_result_path, str(output_path))
    
    # Verify output exists
    assert output_path.exists()
    
    # Read and verify content
    with open(output_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        
        entry = json.loads(lines[0])
        assert entry["run_id"] == run_id
        assert entry["task_id"] == "test-task-456"
        assert entry["reward"] == 1.0
        assert entry["action"]["type"] == "test_action"

    # Verify it can be parsed back to EpisodicMemory
    with open(output_path, "r") as f:
        data = json.loads(f.readline())
        memory = EpisodicMemory(**data)
        assert memory.run_id == run_id
