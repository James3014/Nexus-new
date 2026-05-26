import pytest
from unittest.mock import MagicMock

from nexus.research.flow.auto_flow_decision import decide_auto_flow_routing, enrich_route_on_plateau

def test_decide_auto_flow_routing_learn_gate_blocked():
    # 🧪 Case A: learn_gate_blocked = True, chosen_flow = hyper_sprint, not is_hard_task -> baseline
    res = decide_auto_flow_routing(
        chosen_flow="hyper_sprint",
        force_flow=None,
        execution_profile={"is_hard_task": False},
        learn_gate_blocked=True,
        plateau_detected=False,
        recent_window=[],
        history_fail_threshold=2,
    )
    assert res["chosen_flow"] == "baseline"
    assert res["plateau_hard_pivot"] is False
    assert res["nightshift_recommended"] is False
    assert res["history_forced_baseline"] is False
    assert res["recent_hyper_fails"] == 0
    assert res["stage1_fail_signals"] == 0

    # 🧪 Case B: is_hard_task = True -> Keep hyper_sprint
    res_hard = decide_auto_flow_routing(
        chosen_flow="hyper_sprint",
        force_flow=None,
        execution_profile={"is_hard_task": True},
        learn_gate_blocked=True,
        plateau_detected=False,
        recent_window=[],
        history_fail_threshold=2,
    )
    assert res_hard["chosen_flow"] == "hyper_sprint"


def test_decide_auto_flow_routing_plateau_pivot():
    # 🧪 Case A: plateau_detected = True, chosen_flow = baseline -> hyper_sprint
    res = decide_auto_flow_routing(
        chosen_flow="baseline",
        force_flow=None,
        execution_profile={"is_hard_task": False},
        learn_gate_blocked=False,
        plateau_detected=True,
        recent_window=[],
        history_fail_threshold=2,
    )
    assert res["chosen_flow"] == "hyper_sprint"
    assert res["plateau_hard_pivot"] is True


def test_decide_auto_flow_routing_nightshift_and_history_forced():
    # 🧪 Case A: 2 hyper fails -> nightshift_recommended = True, history_forced_baseline = True
    recent_history = [
        {"flow": "hyper_sprint", "status": "FAILED", "reason": "some error"},
        {"flow": "hyper_sprint", "status": "FAILED", "reason": "another error"},
    ]
    res = decide_auto_flow_routing(
        chosen_flow="hyper_sprint",
        force_flow=None,
        execution_profile={"is_hard_task": False},
        learn_gate_blocked=False,
        plateau_detected=False,
        recent_window=recent_history,
        history_fail_threshold=2,
    )
    assert res["chosen_flow"] == "baseline"
    assert res["nightshift_recommended"] is True
    assert res["history_forced_baseline"] is True
    assert res["recent_hyper_fails"] == 2
    assert res["stage1_fail_signals"] == 0

    # 🧪 Case B: Stage 1 no passing candidate -> nightshift_recommended = True
    recent_history_s1 = [
        {"flow": "hyper_sprint", "status": "FAILED", "reason": "stage1_no_passing_candidate and some context"},
    ]
    res_s1 = decide_auto_flow_routing(
        chosen_flow="hyper_sprint",
        force_flow=None,
        execution_profile={"is_hard_task": False},
        learn_gate_blocked=False,
        plateau_detected=False,
        recent_window=recent_history_s1,
        history_fail_threshold=2,
    )
    assert res_s1["chosen_flow"] == "hyper_sprint"  # fail_threshold is 2, only 1 fail here
    assert res_s1["nightshift_recommended"] is True
    assert res_s1["history_forced_baseline"] is False


def test_enrich_route_on_plateau():
    route = {
        "route_features": {"some_feat": 123},
        "research_context": {"risk_flags": ["exist"], "blocked_assumptions": ["old_assump"]},
    }
    
    mock_capability_plan = MagicMock()
    mock_capability_plan.to_dict.return_value = {"mocked_plan": True}
    
    def dummy_build_capability_plan(rt):
        return mock_capability_plan, "mocked_decision"

    enrich_route_on_plateau(
        route=route,
        task_desc="some complex task",
        task_type="feature",
        plateau={"detected": True, "detail": "locked"},
        asi_ledger=[],
        build_capability_plan_fn=dummy_build_capability_plan,
    )

    assert route["route_features"]["plateau_detected"] is True
    assert route["route_features"]["route_pivot"] == "distant_scout"
    assert "plateau_detected" in route["research_context"]["risk_flags"]
    assert "local_micro_tuning_is_enough" in route["research_context"]["blocked_assumptions"]
    assert route["research_context"]["route_pivot"] == "distant_scout"
    assert route["distant_scout_plan"] is not None
    assert route["capability_plan"] == {"mocked_plan": True}
    assert route["route_decision"] == "mocked_decision"
