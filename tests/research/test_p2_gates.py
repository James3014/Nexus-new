import pytest
from pathlib import Path
from nexus.research.experiment_scheduler import ExperimentScheduler

def test_scheduler_scope_enforcement(tmp_path):
    workspace = tmp_path / "nexus"
    workspace.mkdir()
    
    scheduler = ExperimentScheduler(workspace)
    scope = ["src/core.py", "nexus/logic/"]
    
    scheduler.create_candidate("v1", "Test hypothesis", scope)
    
    # 驗證合法路徑
    assert scheduler.validate_write("v1", "src/core.py") is True
    assert scheduler.validate_write("v1", "nexus/logic/engine.py") is True
    
    # 驗證非法路徑
    assert scheduler.validate_write("v1", "scripts/attack.py") is False
    assert scheduler.validate_write("v1", "nexus/core/dangerous.py") is False

def test_candidate_lifecycle_transitions(tmp_path):
    workspace = tmp_path / "nexus"
    workspace.mkdir()
    
    scheduler = ExperimentScheduler(workspace)
    c_id = "v2"
    
    # 1. Created
    scheduler.create_candidate(c_id, "Fast math", ["math.py"])
    assert scheduler.get_candidate(c_id)["status"] == "created"
    
    # 2. Running
    scheduler.start_experiment(c_id)
    assert scheduler.get_candidate(c_id)["status"] == "running"
    
    # 3. Evaluated
    scheduler.finish_evaluation(c_id, {"score": 0.95})
    candidate = scheduler.get_candidate(c_id)
    assert candidate["status"] == "evaluated"
    assert candidate["metrics"]["score"] == 0.95
