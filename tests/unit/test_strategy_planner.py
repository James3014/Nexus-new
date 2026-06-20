"""Tests for StrategyPlanner."""

import sys
sys.path.insert(0, "/Users/jameschen/Workspace/nexus")

from nexus.strategy import StrategyPlanner


def test_planner_creates_envelope():
    planner = StrategyPlanner()
    e = planner.plan(instance_id="astropy__astropy-13236", issue_summary="table bug")
    assert e.instance_id == "astropy__astropy-13236"
    assert e.trace_only is True
    assert e.has_execution_effect() is False


def test_planner_no_llm():
    planner = StrategyPlanner()
    e = planner.plan(instance_id="test")
    assert e.strategy_source == "deterministic_planner"


def test_planner_handles_missing_metadata():
    planner = StrategyPlanner()
    e = planner.plan(instance_id="test")
    assert e.bug_hypothesis == "unknown"
    assert e.strategy_quality == "low"


if __name__ == "__main__":
    test_planner_creates_envelope()
    test_planner_no_llm()
    test_planner_handles_missing_metadata()
    print("All StrategyPlanner tests PASS")
