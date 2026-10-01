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
    assert components["context_hub"].strict_deps is True
    assert components["context_hub"].memory_service is components["memory"]
    assert components["context_hub"].wisdom_vault is components["wisdom_vault"]
    assert components["context_hub"].prompt_builder is components["prompt_builder"]
    assert components["context_hub"].knowledge_injector is components["knowledge_injector"]
    assert components["context_hub"].knowledge_injector.wisdom_vault is components["wisdom_vault"]
    assert {"P", "X", "D", "A"} <= set(components["phase_executors"])


def test_bootstrap_commander_r_stage_harness_contract(tmp_path: Path, monkeypatch):
    """Witness: Bootstrapped Commander consumes repaired R-stage harness preflight contract."""
    from nexus.core.state_contracts import NexusState
    from nexus.governance.capability_gate import CapabilityGate

    config = EngineConfig(project_root=tmp_path)
    components = build_engine_components(config, {})

    commander = components["commander"]
    state_io = components["state_io"]

    # 1. Normal allowed R-stage preflight returns RUN_SKILL:repair
    state = NexusState(task_id="boot-normal-r", current_phase="R")
    state.metadata["budget_token"] = 5000
    state.total_token_usage = 0
    state_io.save_global_state(state)

    result = commander.next_step()
    assert result == "RUN_SKILL:repair"

    # 2. Canonical hard denial at CapabilityGate produces HARNESS_BLOCKED
    monkeypatch.setattr(
        CapabilityGate,
        "get_tools",
        lambda self, phase: ["read_file"],
    )

    state_denial = NexusState(task_id="boot-denial-r", current_phase="R")
    state_denial.metadata["budget_token"] = 5000
    state_denial.total_token_usage = 0
    state_io.save_global_state(state_denial)

    result_denial = commander.next_step()
    assert result_denial == "HARNESS_BLOCKED"
