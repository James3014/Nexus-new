import pytest
import os
from unittest.mock import MagicMock
from nexus.engine.autonomic_router import AutonomicRouter
from nexus.core.state_contracts import NexusState
from nexus.engine.extension_guard import ExtensionGuard
from nexus.engine.hazard_mapper import HazardMapper

@pytest.fixture
def router(tmp_path):
    # Create a dummy policy file to avoid errors
    knowledge_dir = tmp_path / "nexus" / "knowledge"
    knowledge_dir.mkdir(parents=True)
    policy_file = knowledge_dir / "policy_memory.jsonl"
    policy_file.write_text("")
    return AutonomicRouter(project_root=str(tmp_path))

def test_p0_extension_guard_blocks_code_in_l1(router, monkeypatch):
    # Enable V4 Hardening
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    router.v4_hardened = True
    
    # Task with code file
    task = "Fix a bug in the router"
    state = NexusState(task_id="test_p0")
    forecast = {"target_files": ["nexus/core/router.py"]}
    
    plan = router.route(task, state, forecast)
    
    # Should be upgraded to swarm because it's a code file
    assert plan.mode == "swarm"

def test_p0_extension_guard_allows_docs_in_l1(router, monkeypatch):
    # Enable V4 Hardening
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    router.v4_hardened = True
    
    # Task with only doc files
    task = "Update README"
    state = NexusState(task_id="test_p0_docs")
    forecast = {"target_files": ["README.md", "docs/info.txt"]}
    
    # Ensure it would normally be 'standard'
    plan = router.route(task, state, forecast)
    assert plan.mode == "standard"

def test_p1_hazard_mapper_detects_red_zone(router, monkeypatch):
    # Enable V4 Hardening
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    router.v4_hardened = True
    
    # Impact map involving red zone (auth)
    impact_map = {
        "utils/helper.py": {
            "direct_dependents": ["nexus/core/auth.py"],
            "indirect_dependents": []
        }
    }
    
    task = "Modify helper"
    state = NexusState(task_id="test_p1")
    forecast = {"impact_map": impact_map, "target_files": ["utils/helper.py"]}
    
    plan = router.route(task, state, forecast)
    
    # Should force swarm because auth.py is red zone
    assert plan.mode == "swarm"

def test_v4_disabled_by_default(router):
    # Ensure disabled
    router.v4_hardened = False
    
    # Task with code file
    task = "Fix bug"
    state = NexusState(task_id="test_disabled")
    forecast = {"target_files": ["nexus/core/router.py"]}
    
    plan = router.route(task, state, forecast)
    
    # Should be 'standard' because V4 is off and matches are low
    assert plan.mode == "standard"


def test_p2_mfp_blocks_when_entropy_high(router, monkeypatch):
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    router.v4_hardened = True
    task = "Update docs entry"
    state = NexusState(task_id="test_p2_entropy")
    forecast = {
        "target_files": ["README.md"],
        "confidence": 0.999,
        "semantic_entropy": 0.7,
        "history_success_rate": 0.99,
    }
    plan = router.route(task, state, forecast)
    assert plan.mode == "swarm"


def test_p2_mfp_blocks_when_history_low(router, monkeypatch):
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    router.v4_hardened = True
    task = "Update docs entry"
    state = NexusState(task_id="test_p2_history")
    forecast = {
        "target_files": ["README.md"],
        "confidence": 0.999,
        "semantic_entropy": 0.01,
        "history_success_rate": 0.2,
    }
    plan = router.route(task, state, forecast)
    assert plan.mode == "swarm"


def test_p2_mfp_allows_when_all_factors_pass(router, monkeypatch):
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    router.v4_hardened = True
    task = "Update docs entry"
    state = NexusState(task_id="test_p2_pass")
    forecast = {
        "target_files": ["README.md"],
        "confidence": 0.999,
        "semantic_entropy": 0.01,
        "history_success_rate": 0.99,
    }
    plan = router.route(task, state, forecast)
    assert plan.mode == "standard"


def test_p3_policy_pruning_keeps_global_only_when_tags_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    knowledge_dir = tmp_path / "nexus" / "knowledge"
    knowledge_dir.mkdir(parents=True)
    policy_file = knowledge_dir / "policy_memory.jsonl"
    policy_file.write_text(
        "\n".join(
            [
                '{"rule_id":"R_UI", "condition":"ui policy auth token", "tags":["ui"]}',
                '{"rule_id":"R_GLOBAL", "condition":"global policy auth token", "scope":"GLOBAL"}',
            ]
        ),
        encoding="utf-8",
    )
    local_router = AutonomicRouter(project_root=str(tmp_path))
    local_router.v4_hardened = True
    task = "router auth token issue"
    state = NexusState(task_id="test_p3")
    forecast = {"target_files": ["README.md"], "impact_map": {"nexus/core/auth.py": {}}}
    plan = local_router.route(task, state, forecast)
    assert any(item.startswith("R_GLOBAL") for item in plan.matched_policies)
    assert not any(item.startswith("R_UI") for item in plan.matched_policies)


def test_p4_classifier_outlier_forces_swarm(router, monkeypatch):
    monkeypatch.setenv("NEXUS_ROUTING_V4_HARDENED", "1")
    monkeypatch.setenv("NEXUS_GEMMA_CLASSIFIER_ENABLED", "1")
    router.v4_hardened = True
    task = "Update docs entry"
    state = NexusState(task_id="test_p4_outlier")
    forecast = {
        "target_files": ["README.md"],
        "classifier_scores": [0.1, 0.12, 0.9],
        "confidence": 0.999,
        "semantic_entropy": 0.01,
        "history_success_rate": 0.99,
    }
    plan = router.route(task, state, forecast)
    assert plan.mode == "swarm"
