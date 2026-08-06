from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def _clean_env():
    saved = {}
    for key in (
        "NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW",
        "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL",
        "NEXUS_P3_DIFFICULTY",
    ):
        saved[key] = os.environ.get(key)
    yield
    for key, val in saved.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def test_difficulty_easy_routes_local_only():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="test", task_type="bug", route={"difficulty": "easy", "pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("execution_topology") == "ASSISTED_CANONICAL"
    assert ss.get("executor_topology") == "single_local_model"
    assert ss.get("suggested_executor_topology") == "local_only"
    assert ss.get("p3_shadow_route") is False
    assert ss.get("route_selected_by") is None
    assert ss.get("p3_advisory_reason") == "difficulty=easy"
    assert ss.get("task_difficulty") == "easy"


def test_difficulty_medium_routes_cloud_with_assist():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="test", task_type="bug", route={"difficulty": "medium", "pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("execution_topology") == "ASSISTED_CANONICAL"
    assert ss.get("executor_topology") == "single_local_model"
    assert ss.get("suggested_executor_topology") == "cloud_with_local_assist"
    assert ss.get("p3_shadow_route") is True
    assert ss.get("route_selected_by") is None
    assert ss.get("p3_advisory_reason") == "difficulty=medium_shadow_enabled"


def test_difficulty_hard_routes_cloud_with_assist():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="test", task_type="bug", route={"difficulty": "hard", "pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("execution_topology") == "ASSISTED_CANONICAL"
    assert ss.get("executor_topology") == "single_local_model"
    assert ss.get("suggested_executor_topology") == "cloud_with_local_assist"
    assert ss.get("p3_shadow_route") is True
    assert ss.get("route_selected_by") is None
    assert ss.get("p3_advisory_reason") == "difficulty=hard_shadow_enabled"


def test_difficulty_flag_off_preserves_existing():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "local_committee_only"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="test", task_type="bug", route={"difficulty": "hard", "pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("execution_topology") == "ASSISTED_CANONICAL"
    assert ss.get("executor_topology") == "local_committee_only"
    assert ss.get("p3_shadow_route") is None or ss.get("p3_shadow_route") is False
    assert ss.get("task_difficulty") is None or ss.get("task_difficulty") == ""


def test_difficulty_router_receipt_fields_present():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="test", task_type="bug", route={"difficulty": "medium", "pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("task_difficulty") == "medium"
    assert ss.get("p3_difficulty_advisory_version") == "p3_difficulty_advisory_v1"
    assert ss.get("route_selected_by") is None
    assert ss.get("p3_advisory_reason") == "difficulty=medium_shadow_enabled"


def test_difficulty_heuristic_hard():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="complex cross-module refactor", task_type="bugfix", route={"pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("task_difficulty") == "hard"


def test_difficulty_heuristic_easy():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="simple typo fix", task_type="bugfix", route={"pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("task_difficulty") == "easy"


def test_difficulty_heuristic_default_medium():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="something random", task_type="bugfix", route={"pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("task_difficulty") == "medium"


def test_difficulty_env_var_override():
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    os.environ["NEXUS_P3_DIFFICULTY"] = "hard"

    planner = CapabilityPlanner()
    plan = planner.plan(task_desc="simple fix", task_type="bugfix", route={"pillar_signals": {}})
    ss = plan.signal_snapshot
    assert ss.get("task_difficulty") == "hard"
