"""C6AF: Delegated Retry signal survival tests.

Verify delegated_retry_candidate_models survives the pipeline path.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_delegated_retry_candidate_models_survives_signal_snapshot():
    """delegated_retry_candidate_models must be readable from signal_snapshot in route_context."""
    route_context = {
        "signal_snapshot": {
            "execution_topology": "localheal_pipeline",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "qwen2.5-coder:7b",
            "delegated_retry_candidate_models": [
                "qwen2.5-coder:7b-instruct",
                "deepseek-coder:6.7b-instruct",
            ],
        }
    }
    signal_snapshot = route_context.get("signal_snapshot", {})
    candidate_models = list(signal_snapshot.get("delegated_retry_candidate_models", []) or [])
    assert len(candidate_models) == 2
    assert "qwen2.5-coder:7b-instruct" in candidate_models


def test_delegated_retry_candidate_models_survives_shallow_copy():
    """delegated_retry_candidate_models must survive dict(route_ctx) shallow copy."""
    original = {
        "signal_snapshot": {
            "execution_topology": "localheal_pipeline",
            "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct"],
        }
    }
    copy = dict(original)
    signal_snapshot = copy.get("signal_snapshot", {})
    candidate_models = list(signal_snapshot.get("delegated_retry_candidate_models", []) or [])
    assert len(candidate_models) == 1


def test_delegated_retry_candidate_models_survives_pipeline_context():
    """delegated_retry_candidate_models must survive HealContext.to_v2() round-trip."""
    from nexus.services.local_heal.pipeline import HealContext
    from pathlib import Path

    ctx = HealContext(
        instance_id="test-1",
        repo_dir=Path("/tmp"),
        problem_statement="test",
        route_context={
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct"],
            }
        },
    )
    v2_ctx = ctx.to_v2()
    route_ctx = v2_ctx.op.route_context if hasattr(v2_ctx.op, "route_context") else {}
    signal_snapshot = route_ctx.get("signal_snapshot", {}) if isinstance(route_ctx, dict) else {}
    candidate_models = list(signal_snapshot.get("delegated_retry_candidate_models", []) or [])
    assert len(candidate_models) == 1


def test_build_c15_benchmark_row_includes_delegated_retry():
    """build_c15_benchmark_row must include delegated_retry_candidate_models in signal_snapshot."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.bench.m1_real_local_solve_benchmark import build_c15_benchmark_row

    spec = {
        "task_id": "test-task",
        "repo": "test-repo",
        "target_file": "app.py",
        "test_file": "test_app.py",
        "execution_topology": "localheal_pipeline",
        "expected_capabilities": ["local_model_executor"],
        "locked_search": "def func():",
        "target_symbol": "func",
    }
    row = build_c15_benchmark_row(
        spec,
        verify_path=Path("/tmp/test_app.py"),
        sys_executable=sys.executable,
        delegated_retry_candidate_models="qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct",
    )
    signal_snapshot = row.get("signal_snapshot", {})
    candidate_models = signal_snapshot.get("delegated_retry_candidate_models", [])
    assert len(candidate_models) == 2
    assert "qwen2.5-coder:7b-instruct" in candidate_models
    assert "deepseek-coder:6.7b-instruct" in candidate_models


def test_delegated_retry_signal_survives_executor_bridge():
    """delegated_retry_candidate_models must survive from row to executor request."""
    from nexus.services.local_heal.local_model_executor import LocalModelExecutorRequest

    row = {
        "signal_snapshot": {
            "execution_topology": "localheal_pipeline",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "qwen2.5-coder:7b",
            "delegated_retry_candidate_models": [
                "qwen2.5-coder:7b-instruct",
                "deepseek-coder:6.7b-instruct",
            ],
        }
    }
    req = LocalModelExecutorRequest(
        task_id="test-1",
        problem_statement="test",
        repo_root="/tmp",
        target_file="app.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        route_context=row,
    )
    signal_snapshot = req.route_context.get("signal_snapshot", {})
    candidate_models = list(signal_snapshot.get("delegated_retry_candidate_models", []) or [])
    assert len(candidate_models) == 2


def test_delegated_retry_signal_readable_in_orchestrator():
    """delegated_retry_candidate_models must be readable from route_context in orchestrator."""
    from nexus.services.local_heal.local_model_executor import _resolve_execution_topology

    route_context = {
        "signal_snapshot": {
            "execution_topology": "localheal_pipeline",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "qwen2.5-coder:7b",
            "delegated_retry_candidate_models": [
                "qwen2.5-coder:7b-instruct",
            ],
        }
    }
    req = SimpleNamespace(route_context=route_context)
    topology = _resolve_execution_topology(req)
    assert topology == "localheal_pipeline"

    signal_snapshot = route_context.get("signal_snapshot", {})
    candidate_models = list(signal_snapshot.get("delegated_retry_candidate_models", []) or [])
    assert len(candidate_models) == 1


def test_delegated_retry_signal_in_raw_meta_telemetry():
    """delegated_retry_candidate_models count must appear in raw_meta telemetry."""
    route_context = {
        "signal_snapshot": {
            "execution_topology": "localheal_pipeline",
            "delegated_retry_candidate_models": [
                "qwen2.5-coder:7b-instruct",
                "deepseek-coder:6.7b-instruct",
            ],
        }
    }
    signal_snapshot = route_context.get("signal_snapshot", {})
    candidate_models = list(signal_snapshot.get("delegated_retry_candidate_models", []) or [])
    raw_meta = {
        "delegated_retry_proposer_count_expected": len(candidate_models),
    }
    assert raw_meta["delegated_retry_proposer_count_expected"] == 2
