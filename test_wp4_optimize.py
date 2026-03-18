import json
import yaml
import pytest
from pathlib import Path
from nexus.core.optimize.loop import optimize_loop

@pytest.fixture
def mock_project(tmp_path):
    """
    Setup a mock project with configs/skills_router.yaml and policy_updates.json
    """
    project_root = tmp_path
    configs_dir = project_root / "configs"
    configs_dir.mkdir()
    
    # 1. Initial skills_router.yaml
    router_config = {
        "skill_weights": {
            "tdd_weight": 2.5,
            "refactor_weight": 3.0
        }
    }
    router_path = configs_dir / "skills_router.yaml"
    with open(router_path, "w", encoding="utf-8") as f:
        yaml.dump(router_config, f)
        
    # 2. policy_updates.json
    policy_updates = {
        "skill_weights": {
            "tdd_weight": 3.5,
            "investigate_weight": 4.5
        }
    }
    policy_path = project_root / "policy_updates.json"
    with open(policy_path, "w", encoding="utf-8") as f:
        json.dump(policy_updates, f)
        
    return project_root

def test_optimize_loop_updates_weights(mock_project):
    # Execute the loop
    optimize_loop(str(mock_project))
    
    # Verify the results
    router_path = mock_project / "configs" / "skills_router.yaml"
    with open(router_path, "r", encoding="utf-8") as f:
        updated_config = yaml.safe_load(f)
        
    weights = updated_config.get("skill_weights", {})
    
    # tdd_weight should be updated from 2.5 to 3.5
    assert weights.get("tdd_weight") == 3.5
    
    # refactor_weight should remain 3.0
    assert weights.get("refactor_weight") == 3.0
    
    # investigate_weight should be added
    assert weights.get("investigate_weight") == 4.5

def test_optimize_loop_missing_policy(mock_project):
    # Remove policy updates file
    (mock_project / "policy_updates.json").unlink()
    
    # Should not crash
    optimize_loop(str(mock_project))
    
    # Verify no change to router config
    router_path = mock_project / "configs" / "skills_router.yaml"
    with open(router_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    assert config["skill_weights"]["tdd_weight"] == 2.5
