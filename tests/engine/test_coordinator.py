from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from nexus.core.state_contracts import NexusState
from nexus.engine.config import EngineConfig
from nexus.engine.coordinator import NexusEngine


def _build_engine(config: EngineConfig, reporter: MagicMock | None = None):
    stack = ExitStack()
    patches = {
        "state_io_cls": stack.enter_context(patch("nexus.engine.coordinator.StateIO")),
        "workspace_mgr_cls": stack.enter_context(patch("nexus.engine.coordinator.WorkspaceManager")),
        "policy_load": stack.enter_context(patch("nexus.engine.coordinator.PolicyLoader.load", return_value={"env": "dev"})),
        "gate_eval_cls": stack.enter_context(patch("nexus.engine.coordinator.GateEvaluator")),
        "metrics_agg_cls": stack.enter_context(patch("nexus.engine.coordinator.MetricsAggregator")),
        "validator_cls": stack.enter_context(patch("nexus.engine.coordinator.NexusHardenedValidator")),
        "latent_forecaster": stack.enter_context(patch("nexus.engine.coordinator.get_latent_forecaster")),
        "ash_selector": stack.enter_context(patch("nexus.engine.coordinator.get_self_healing_selector")),
        "memory_cls": stack.enter_context(patch("nexus.engine.coordinator.MemoryService")),
        "hub_cls": stack.enter_context(patch("nexus.engine.hub.NexusHub")),
        "federation_cls": stack.enter_context(patch("nexus.engine.coordinator.FederationLayer")),
        "vector_cache_cls": stack.enter_context(patch("nexus.engine.coordinator.VectorCache")),
        "sota_searcher_cls": stack.enter_context(patch("nexus.engine.coordinator.SOTASearcher")),
        "aggregator_cls": stack.enter_context(patch("nexus.engine.coordinator.NexusNeuralAggregator")),
        "planner_cls": stack.enter_context(patch("nexus.engine.coordinator.HierarchicalGraphPlanner")),
        "tx_cls": stack.enter_context(patch("scripts.engine.nexus_transaction.TransactionManager")),
    }
    engine = NexusEngine(config=config, reporter=reporter or MagicMock())
    return engine, patches, stack


def test_engine_init_uses_current_dependencies():
    config = EngineConfig(
        project_root=Path("/tmp/nexus_test"),
        run_dir=Path("/tmp/nexus_test/runs/test-run"),
        fast_mode=True,
        audit_level="standard",
        silent=True,
    )
    reporter = MagicMock()

    engine, patches, stack = _build_engine(config, reporter=reporter)
    try:
        assert engine.project_root == config.project_root
        assert engine.run_dir == config.run_dir
        assert engine.reporter is reporter
        patches["policy_load"].assert_called_once_with(str(config.project_root), env="dev")
        patches["workspace_mgr_cls"].assert_called_once_with(config.project_root)
        patches["state_io_cls"].assert_called_once_with(config.project_root, run_dir=config.run_dir)
    finally:
        stack.close()


def test_run_bug_prepares_workspace_and_routes_workflow():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    reporter = MagicMock()
    engine, patches, stack = _build_engine(config, reporter=reporter)
    try:
        engine._execute_task_workflow = MagicMock(return_value=True)

        result = engine.run_bug(bug_id="bug-123", desc="fix it")

        assert result is True
        engine.workspace_mgr.prepare_physical_sandbox.assert_called_once_with(config.run_dir)
        call = engine._execute_task_workflow.call_args
        assert call.args[:2] == ("bug-123", "nexus:bug")
        state = call.kwargs["state"]
        assert isinstance(state, NexusState)
        assert state.task_id == "bug-123"
        assert state.metadata["task_description"] == "fix it"
        reporter.voice_notify.assert_called_once()
        reporter.log_trace.assert_called_once()
    finally:
        stack.close()


def test_run_feature_sets_swarm_context_before_workflow():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    reporter = MagicMock()
    engine, _, stack = _build_engine(config, reporter=reporter)
    try:
        engine._execute_task_workflow = MagicMock(return_value=True)

        result = engine.run_feature(task_id="feat-1", task="build it", context={"swarm_mode": True})

        assert result is True
        call = engine._execute_task_workflow.call_args
        assert call.args[:2] == ("feat-1", "nexus:feature")
        state = call.kwargs["state"]
        assert state.metadata["swarm_mode"] is True
        assert state.metadata["task_description"] == "build it"
        reporter.voice_notify.assert_called_once()
        reporter.log_trace.assert_called_once()
    finally:
        stack.close()


def test_execute_task_workflow_rejects_and_triggers_self_heal():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    engine, patches, stack = _build_engine(config, reporter=MagicMock())
    try:
        patches["latent_forecaster"].return_value.forecast_roi.return_value = {"est_tokens": 42, "roi_score": 0.1}
        patches["latent_forecaster"].return_value.predict_risk.return_value = {"reject_prob": 0.9}
        engine.gate_eval.should_proceed.return_value = (False, "too risky")
        engine.ash_selector.trigger_ash.return_value = {"selected_strategy": "rollback"}

        state = NexusState(task_id="risk-1")
        state.metadata["task_description"] = "risky fix"
        result = engine._execute_task_workflow("risk-1", "nexus:bug", state=state)

        assert result is None
        engine.ash_selector.trigger_ash.assert_called_once()
        assert state.metadata["last_rejection_reason"] == "too risky"
        assert state.metadata["ash_selected_strategy"] == "rollback"
        engine.state_io.save_global_state.assert_called_once_with(state)
    finally:
        stack.close()


def test_run_benchmark_returns_current_result_shape():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    engine, _, stack = _build_engine(config, reporter=MagicMock())
    try:
        result = engine.run_benchmark(framework="swe-bench", swarm_mode=True)

        assert isinstance(result, list)
        assert result[0]["status"] == "PASS"
        assert result[0]["framework"] == "swe-bench"
        assert result[0]["swarm_density"] == "High"
    finally:
        stack.close()
