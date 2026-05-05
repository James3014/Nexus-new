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
    assert components["context_hub"].belief_engine is components["belief_engine"]
    assert components["context_hub"].memory_service is components["memory"]
    assert components["context_hub"].wisdom_vault is components["wisdom_vault"]
    assert components["context_hub"].prompt_builder is components["prompt_builder"]
    assert components["context_hub"].knowledge_injector is components["knowledge_injector"]
    assert components["context_hub"].knowledge_injector.wisdom_vault is components["wisdom_vault"]
