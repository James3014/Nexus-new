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


def test_run_task_pipeline_binds_explicit_spec_into_direct_mode_context():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    engine, _, stack = _build_engine(config, reporter=MagicMock())
    try:
        engine.pipeline = MagicMock()
        engine.pipeline.run.return_value = True
        engine.phases = {"P": MagicMock(run=MagicMock())}

        task_desc = """
        失敗測試:
        uv run pytest tests/engine/test_pipeline_stages.py::test_stage_plan -q
        根因: routing drift
        修法:
        - nexus/engine/pipeline.py:339
        """
        ok = engine._run_task_pipeline(
            task_desc=task_desc,
            task_type="bug",
            task_id="direct-1",
            context={},
        )

        assert ok is True
        kwargs = engine.pipeline.run.call_args.kwargs
        ctx = kwargs["context"]
        assert ctx["direct_mode"] is True
        assert "nexus/engine/pipeline.py" in ctx["target_files"]
        assert ctx["verify_commands"] == [
            "uv run pytest tests/engine/test_pipeline_stages.py::test_stage_plan -q"
        ]
    finally:
        stack.close()


def test_execute_task_workflow_skips_autonomic_routing_in_direct_mode():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    engine, patches, stack = _build_engine(config, reporter=MagicMock())
    try:
        state = NexusState(task_id="direct-exec-1")
        state.metadata["task_description"] = "explicit direct repair"
        state.metadata["direct_mode"] = True
        state.metadata["direct_mode_reason"] = "explicit_user_repair_spec"
        state.metadata["sim_lewm"] = True
        state.metadata["lewm_sim_status"] = "REJECTED"

        patches["latent_forecaster"].return_value.forecast_roi.return_value = {"est_tokens": 42, "roi_score": 0.5}
        patches["latent_forecaster"].return_value.predict_risk.return_value = {"reject_prob": 0.1}
        engine.gate_eval.should_proceed.return_value = (True, "ok")
        engine.context_hub = MagicMock()
        engine.metrics_agg.aggregate_crystallize_payload.return_value = {
            "lessons": [],
            "weight_delta": {},
            "update_target": "none",
            "why": "test",
        }

        _ = engine._execute_task_workflow("direct-exec-1", "nexus:bug", state=state)

        assert state.metadata["autonomic_route"] == "direct_mode"
        assert state.metadata["autonomic_reason"] == "explicit_user_repair_spec"
        engine.context_hub.make_pre_routing_decision.assert_not_called()
    finally:
        stack.close()


def test_execute_task_workflow_short_circuits_when_forecast_gate_rejects():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    engine, _, stack = _build_engine(config, reporter=MagicMock())
    try:
        state = NexusState(task_id="preflight-stop-1")
        state.metadata["task_description"] = "preflight stop"
        engine.forecast_gate = MagicMock()
        engine.forecast_gate.evaluate.return_value = {
            "proceed": False,
            "reason": "blocked",
            "forecast": {"est_tokens": 1, "roi_score": 0.1},
            "risk": {"reject_prob": 0.9},
        }
        engine.autonomic_routing = MagicMock()

        result = engine._execute_task_workflow("preflight-stop-1", "nexus:bug", state=state)

        assert result is None
        engine.forecast_gate.evaluate.assert_called_once()
        engine.autonomic_routing.apply.assert_not_called()
    finally:
        stack.close()


def test_execute_task_workflow_calls_context_enrichment_before_validator_reject():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    engine, _, stack = _build_engine(config, reporter=MagicMock())
    try:
        state = NexusState(task_id="ctx-enrich-1")
        state.metadata["task_description"] = "context enrich path"
        engine.forecast_gate = MagicMock()
        engine.forecast_gate.evaluate.return_value = {
            "proceed": True,
            "reason": "ok",
            "forecast": {"est_tokens": 10, "roi_score": 0.5},
            "risk": {"reject_prob": 0.1},
        }
        engine.autonomic_routing = MagicMock()
        engine.context_enrichment = MagicMock()
        engine.repair_setup = MagicMock()
        engine.repair_setup.prepare.return_value = {
            "proceed": False,
            "reason": "validator_rejected",
            "verify_cmds": [],
            "skip_pregate": False,
        }

        result = engine._execute_task_workflow("ctx-enrich-1", "nexus:bug", state=state)

        assert result is False
        engine.context_enrichment.run.assert_called_once_with(state=state)
    finally:
        stack.close()


def test_execute_task_workflow_delegates_repair_attempt_and_aborts():
    config = EngineConfig(project_root=Path("/tmp/nexus_test"), run_dir=Path("/tmp/nexus_test/runs/test-run"), silent=True)
    engine, _, stack = _build_engine(config, reporter=MagicMock())
    try:
        state = NexusState(task_id="repair-attempt-1")
        state.metadata["task_description"] = "repair attempt delegation"
        engine.forecast_gate = MagicMock()
        engine.forecast_gate.evaluate.return_value = {
            "proceed": True,
            "reason": "ok",
            "forecast": {"est_tokens": 10, "roi_score": 0.5},
            "risk": {"reject_prob": 0.1},
        }
        engine.autonomic_routing = MagicMock()
        engine.context_enrichment = MagicMock()
        engine.repair_setup = MagicMock()
        engine.repair_setup.prepare.return_value = {
            "proceed": True,
            "verify_cmds": ["pytest -q"],
            "skip_pregate": False,
        }
        engine.repair_loop = MagicMock()
        engine.repair_loop.run.return_value = False

        result = engine._execute_task_workflow("repair-attempt-1", "nexus:bug", state=state)

        assert result is False
        engine.repair_setup.prepare.assert_called_once_with(state=state)
        engine.repair_loop.run.assert_called_once()
    finally:
        stack.close()
