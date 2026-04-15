import pytest
from pathlib import Path
from nexus.engine.bootstrap import build_engine_components
from nexus.engine.config import EngineConfig

def test_bootstrap_builds_all_required_components(tmp_path: Path):
    config = EngineConfig(project_root=tmp_path)
    components = build_engine_components(config, {})
    
    expected_keys = [
        "state_io", "context_hub", "commander", "policy", 
        "gate_eval", "memory", "hub", "battle_swarm"
    ]
    for key in expected_keys:
        assert key in components
        assert components[key] is not None
        
    assert components["run_dir"].exists()
