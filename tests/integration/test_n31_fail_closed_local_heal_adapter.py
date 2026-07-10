from __future__ import annotations

from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)


def test_local_heal_adapter_rejects_manual_signal_snapshot():
    """RED: Adapter should reject manual signal_snapshot (no planner_version)."""
    request = LocalHealCapabilityRequest(
        task_id="test1",
        problem_statement="fix bug",
        evidence_refs=("ref1",),
        executor_controls={
            "route_context": {
                "signal_snapshot": {
                    "model_call_allowed": True,
                    "executor_provider": "ollama",
                    "executor_model": "qwen2.5-coder:7b",
                }
            },
            "enable_local_heal": True,
            "local_heal_mode": "active",
        },
    )
    response = LocalHealCapabilityAdapter.run(request)

    assert response.invoked is False
    assert "missing_planner_version" in response.hybrid_route.fallback_block_reason


def test_local_heal_adapter_accepts_planner_signal_snapshot():
    """RED: Adapter should accept CapabilityPlanner.plan() signal_snapshot (has planner_version)."""
    request = LocalHealCapabilityRequest(
        task_id="test2",
        problem_statement="fix bug",
        evidence_refs=("ref2",),
        executor_controls={
            "route_context": {
                "signal_snapshot": {
                    "planner_version": "capability_planner_v1",
                    "model_call_allowed": True,
                    "executor_provider": "ollama",
                    "executor_model": "qwen2.5-coder:7b",
                    "candidate_enabled": True,
                    "isolated_solve_enabled": True,
                    "mutation_allowed": True,
                    "verifier_allowed": True,
                    "source_root": "/tmp",
                    "target_file": "f.py",
                    "target_symbol": "foo",
                    "locked_search": "return",
                    "verifier_command": ["true"],
                    "work_dir": "",
                }
            },
            "enable_local_heal": True,
            "local_heal_mode": "active",
        },
        dry_run=True,
    )
    response = LocalHealCapabilityAdapter.run(request)

    assert response.hybrid_route.fallback_block_reason != "missing_planner_version"


def test_local_heal_adapter_rejects_fake_planner_version():
    """RED: Adapter should reject fake planner_version."""
    request = LocalHealCapabilityRequest(
        task_id="test3",
        problem_statement="fix bug",
        evidence_refs=("ref3",),
        executor_controls={
            "route_context": {
                "signal_snapshot": {
                    "planner_version": "fake_planner_v999",
                    "model_call_allowed": True,
                    "executor_provider": "ollama",
                    "executor_model": "qwen2.5-coder:7b",
                }
            },
            "enable_local_heal": True,
            "local_heal_mode": "active",
        },
    )
    response = LocalHealCapabilityAdapter.run(request)

    assert response.invoked is False
    assert "invalid_planner_version" in response.hybrid_route.fallback_block_reason


def test_local_heal_adapter_rejects_empty_signal_snapshot():
    """RED: Adapter should reject empty signal_snapshot (empty dict = missing planner_version or missing_signal_snapshot)."""
    request = LocalHealCapabilityRequest(
        task_id="test4",
        problem_statement="fix bug",
        evidence_refs=("ref4",),
        executor_controls={
            "route_context": {"signal_snapshot": {}},
            "enable_local_heal": True,
            "local_heal_mode": "active",
        },
    )
    response = LocalHealCapabilityAdapter.run(request)

    assert response.invoked is False
    reason = response.hybrid_route.fallback_block_reason
    assert "missing_planner_version" in reason or "missing_signal_snapshot" in reason


def test_local_heal_adapter_rejects_incomplete_planner_snapshot():
    """N31-C: Adapter should reject signal_snapshot with planner_version but missing required planner fields."""
    request = LocalHealCapabilityRequest(
        task_id="test5",
        problem_statement="fix bug",
        evidence_refs=("ref5",),
        executor_controls={
            "route_context": {
                "signal_snapshot": {
                    "planner_version": "capability_planner_v1",
                    "model_call_allowed": True,
                    "executor_provider": "ollama",
                    "executor_model": "qwen2.5-coder:7b",
                }
            },
            "enable_local_heal": True,
            "local_heal_mode": "active",
        },
    )
    response = LocalHealCapabilityAdapter.run(request)

    assert response.invoked is False
    assert "incomplete_signal_snapshot" in response.hybrid_route.fallback_block_reason
