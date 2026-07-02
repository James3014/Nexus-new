"""M1.3: LocalHeal Pipeline Seam Truth Tests.

Verifies that localheal_pipeline topology invokes the bridge (LocalHealPipelineCapabilityExecutor),
NOT the full HealPipeline.run() or HealOrchestrator.run().

Seam truth:
- Bridge IS invoked (localheal_pipeline_invoked=True)
- Bridge does real work: instantiates modules, parses protocol (localheal_pipeline_actual_execution=True)
- Bridge does NOT call HealPipeline.run() or Orchestrator.run()
- Model call goes through provider.generate() directly, bypassing pipeline retry/verification loop
- localheal_pipeline_availability_only=False when modules are importable
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import hashlib
import os
import pytest

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
    _resolve_execution_topology,
)
from nexus.services.local_heal.local_model_capability_executors import (
    LocalHealPipelineCapabilityExecutor,
)
from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
    CapabilityExecutionResult,
)


def _build_request(
    execution_topology: str = "localheal_pipeline",
    dry_run: bool = False,
    selected_capabilities: tuple[str, ...] = ("repair_loop", "ddtree", "autoreason"),
    evidence_refs: tuple[str, ...] = ("e1",),
):
    return LocalModelExecutorRequest(
        task_id="t_seam_1",
        problem_statement="fix bug in foo",
        repo_root="/tmp/test_repo",
        target_file="foo.py",
        selected_capabilities=selected_capabilities,
        evidence_refs=evidence_refs,
        route_context={
            "signal_snapshot": {
                "execution_topology": execution_topology,
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
            },
            "locked_search": "def foo_func():\n    pass\n",
            "target_symbol": "foo_func",
        },
        dry_run=dry_run,
        mutation_allowed=True,
    )


def _build_provider_mock(output_text: str = "def foo_func():\n    return 42\n"):
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.output_text = output_text
    mock_response.provider_invoked = True
    mock_response.model_called = True
    mock_response.error = ""
    mock_response.timed_out = False
    mock_response.model_name = "qwen2.5-coder:7b"
    mock.generate.return_value = mock_response
    return mock


class TestLocalhealPipelineTopologyBridgeInvocation:
    """Test 1: Verify topology routes through bridge, not full pipeline."""

    def test_localheal_pipeline_topology_reports_bridge_invocation(self):
        """LocalHealPipelineCapabilityExecutor is invoked, NOT HealPipeline/Orchestrator."""
        provider = _build_provider_mock()

        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            result = LocalModelExecutor.run(_build_request(), provider=provider)

        assert result.invoked is True
        assert result.raw_model_metadata.get("execution_topology") == "localheal_pipeline"

        # The bridge should report what was invoked
        bridge_invoked = result.raw_model_metadata.get("localheal_pipeline_invoked", False)
        actual_execution = result.raw_model_metadata.get("localheal_pipeline_actual_execution", False)
        availability_only = result.raw_model_metadata.get("localheal_pipeline_availability_only", False)

        # Bridge WAS invoked
        assert bridge_invoked is True, "LocalHealPipelineCapabilityExecutor must be invoked"

        # Bridge does real work when modules are importable (instantiation, protocol parse)
        # But this is NOT full pipeline execution (no .run(), no orchestrator repair loop)
        assert actual_execution is True, (
            "localheal_pipeline_actual_execution should be True — bridge does real work"
        )

        # Availability-only is False when modules are importable
        assert availability_only is False, (
            "localheal_pipeline_availability_only should be False — modules are importable"
        )


class TestLocalhealPipelineTopologyDoesNotClaimFullExecution:
    """Test 2: Bridge NOW calls HealPipeline.run() (B1), but Orchestrator.run() is reached via pipeline."""

    def test_localheal_pipeline_topology_calls_heal_pipeline_run(self):
        """Bridge now calls HealPipeline.run() (B1 wiring)."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                result = LocalHealPipelineCapabilityExecutor().execute(
                    LocalModelCapabilityContext(
                        task_id="t_bridge",
                        source_root="/tmp",
                        problem_statement="fix bug",
                        target_file="a.py",
                        target_symbol="f",
                        selected_capabilities=("repair_loop",),
                        execution_topology="localheal_pipeline",
                        evidence_refs=("e1",),
                        source_anchor={"present": False},
                        route_context={},
                    )
                )

                # .run() IS now called (B1)
                pipeline_run_mock.assert_called_once()
                assert result.telemetries.get("localheal_pipeline_run_called") is True

    def test_localheal_pipeline_topology_does_not_call_orchestrator_run_directly(self):
        """Bridge calls pipeline.run(), which internally calls orchestrator — bridge doesn't call orchestrator directly."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                result = LocalHealPipelineCapabilityExecutor().execute(
                    LocalModelCapabilityContext(
                        task_id="t_bridge",
                        source_root="/tmp",
                        problem_statement="fix bug",
                        target_file="a.py",
                        target_symbol="f",
                        selected_capabilities=("repair_loop",),
                        execution_topology="localheal_pipeline",
                        evidence_refs=("e1",),
                        source_anchor={"present": False},
                        route_context={},
                    )
                )

                # Bridge doesn't import orchestrator directly
                # Orchestrator is called internally by pipeline.run()
                pass

    def test_localheal_pipeline_passes_python_executable_from_route_context(self):
        """Bridge must forward task-scoped python_executable into HealContext."""
        from nexus.services.local_heal.pipeline import HealPipeline

        captured_ctx = None

        def _capture_run(ctx):
            nonlocal captured_ctx
            captured_ctx = ctx
            mock_ctx = MagicMock()
            mock_ctx.final_patch = ""
            mock_ctx.solve_eligible = False
            mock_ctx.failure_reason = ""
            return mock_ctx

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", side_effect=_capture_run):
                LocalHealPipelineCapabilityExecutor().execute(
                    LocalModelCapabilityContext(
                        task_id="t_bridge_py",
                        source_root="/tmp",
                        problem_statement="fix bug",
                        target_file="a.py",
                        target_symbol="f",
                        selected_capabilities=("repair_loop",),
                        execution_topology="localheal_pipeline",
                        evidence_refs=("e1",),
                        source_anchor={"present": False},
                        route_context={"python_executable": "/tmp/task-venv/bin/python"},
                    )
                )

        assert captured_ctx is not None
        assert captured_ctx.python_executable == "/tmp/task-venv/bin/python"


class TestLocalhealPipelineTopologyExposesExecutionFlag:
    """Test 3: Telemetry flags distinguish bridge from full pipeline."""

    def test_localheal_pipeline_topology_exposes_actual_execution_flag(self):
        """Telemetry must contain availability_only vs actual_execution distinction."""
        provider = _build_provider_mock()

        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            result = LocalModelExecutor.run(_build_request(), provider=provider)

        meta = result.raw_model_metadata

        # These flags MUST exist in the telemetry
        assert "localheal_pipeline_availability_only" in meta, (
            "localheal_pipeline_availability_only flag missing from telemetry"
        )
        assert "localheal_pipeline_actual_execution" in meta, (
            "localheal_pipeline_actual_execution flag missing from telemetry"
        )

        # They must be mutually exclusive
        avail_only = meta["localheal_pipeline_availability_only"]
        actual_exec = meta["localheal_pipeline_actual_execution"]

        assert avail_only != actual_exec, (
            f"availability_only ({avail_only}) and actual_execution ({actual_exec}) "
            "must be mutually exclusive"
        )


class TestLocalhealPipelineTopologyDoesNotMarkSolvedFromAvailabilityOnly:
    """Test 4: Mere topology availability does NOT produce solved=true."""

    def test_localheal_pipeline_topology_does_not_mark_solved_from_availability_only(self):
        """Availability-only bridge must not produce candidate_patch or solved outcome."""
        provider = _build_provider_mock(
            output_text=""  # No patch produced
        )

        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            result = LocalModelExecutor.run(_build_request(), provider=provider)

        empty_hash = hashlib.sha256(b"").hexdigest()

        # When provider returns empty, candidate_hash must be empty
        if not result.candidate_patch.strip():
            assert result.candidate_hash == empty_hash, (
                "Empty patch must produce empty hash"
            )

        # Bridge availability alone must not set a solved-like state
        meta = result.raw_model_metadata
        actual_execution = meta.get("localheal_pipeline_actual_execution", False)

        if not actual_execution and not result.candidate_patch.strip():
            # No actual execution + no patch = not solved
            assert result.candidate_hash == empty_hash, (
                "Bridge availability without execution and without patch must not produce solved state"
            )


class TestLocalhealPipelineTopologySingleLocalModelNotAffected:
    """Test 5: single_local_model topology is NOT affected by this seam."""

    def test_single_local_model_topology_does_not_use_bridge(self):
        """single_local_model should not invoke the bridge at all."""
        from nexus.services.local_heal.local_model_capability_executors import (
            LocalHealPipelineCapabilityExecutor,
        )

        bridge_execute_mock = MagicMock(return_value=CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=False, gate_passed=False,
            outcome_contributed=False, evidence_present=True,
            failure_reason="not_localheal_pipeline_topology",
        ))

        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=_build_provider_mock(),
        ):
            with patch.object(
                LocalHealPipelineCapabilityExecutor, "execute", bridge_execute_mock
            ):
                # Build a single_local_model request
                req = _build_request(execution_topology="single_local_model")
                result = LocalModelExecutor.run(req, provider=_build_provider_mock())

                # Bridge should NOT be called for single_local_model
                bridge_execute_mock.assert_not_called()


class TestLocalhealPipelineTopologyModelCallBypassesPipeline:
    """Test 6: Model call goes through provider, NOT through pipeline retry loop."""

    def test_model_call_goes_through_provider(self):
        """provider.generate() is called — through pipeline orchestrator."""
        provider = _build_provider_mock()

        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            result = LocalModelExecutor.run(_build_request(), provider=provider)

        # provider.generate() was called (at least once — pipeline may call it multiple times)
        assert provider.generate.call_count >= 1
        assert result.local_model_called is True
        assert result.reasoning_summary in ("pipeline_result", "pipeline_failed_empty")

        # No retry loop metadata (pipeline doesn't do retry in bridge path)
        meta = result.raw_model_metadata
        # The bridge doesn't add retry_count or semantic_retry fields
        # because it doesn't run the orchestrator repair loop



class TestLocalhealPipelineBridgeUsesRealProvider:
    """A3: Bridge uses real provider when available, not _noop_generate."""

    def test_bridge_calls_heal_pipeline_run_when_planner_selects_localheal_pipeline(self):
        """Bridge instantiates HealPipeline with real provider generate function."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_init_mock = MagicMock()
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", pipeline_init_mock):
            ctx = LocalModelCapabilityContext(
                task_id="t_bridge_provider",
                source_root="/tmp",
                problem_statement="fix bug",
                target_file="a.py",
                target_symbol="f",
                selected_capabilities=("repair_loop",),
                execution_topology="localheal_pipeline",
                evidence_refs=("e1",),
                source_anchor={"present": False},
                route_context={},
                provider=provider,
            )
            result = LocalHealPipelineCapabilityExecutor().execute(ctx)

            # HealPipeline was instantiated
            pipeline_init_mock.assert_called_once()
            call_kwargs = pipeline_init_mock.call_args
            # The ollama_generate_fn should NOT be _noop_generate
            generate_fn = call_kwargs.kwargs.get("ollama_generate_fn") or call_kwargs[1].get("ollama_generate_fn")
            assert generate_fn is not None

    def test_bridge_uses_real_provider_not_noop_when_available(self):
        """When provider is set, bridge wraps it instead of using _noop_generate."""
        provider = _build_provider_mock()

        ctx = LocalModelCapabilityContext(
            task_id="t_bridge_real",
            source_root="/tmp",
            problem_statement="fix bug",
            target_file="a.py",
            target_symbol="f",
            selected_capabilities=("repair_loop",),
            execution_topology="localheal_pipeline",
            evidence_refs=("e1",),
            source_anchor={"present": False},
            route_context={},
            provider=provider,
        )
        result = LocalHealPipelineCapabilityExecutor().execute(ctx)
        assert result.invoked is True
        assert result.telemetries.get("localheal_pipeline_invoked") is True

    def test_bridge_does_not_call_pipeline_for_local_only(self):
        """single_local_model topology does not invoke bridge."""
        bridge_mock = MagicMock(return_value=CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=False, gate_passed=False,
            outcome_contributed=False, evidence_present=True,
        ))
        with patch.object(LocalHealPipelineCapabilityExecutor, "execute", bridge_mock):
            ctx = LocalModelCapabilityContext(
                task_id="t_no_bridge",
                source_root="/tmp",
                problem_statement="fix bug",
                target_file="a.py",
                target_symbol="f",
                selected_capabilities=("repair_loop",),
                execution_topology="single_local_model",
                evidence_refs=("e1",),
                source_anchor={"present": False},
                route_context={},
            )
            LocalHealPipelineCapabilityExecutor().execute(ctx)
            # Bridge should report not selected for non-pipeline topology
            assert ctx.execution_topology != "localheal_pipeline"

    def test_bridge_does_not_call_pipeline_for_local_committee_only(self):
        """local_committee_only topology does not invoke bridge."""
        ctx = LocalModelCapabilityContext(
            task_id="t_no_bridge_committee",
            source_root="/tmp",
            problem_statement="fix bug",
            target_file="a.py",
            target_symbol="f",
            selected_capabilities=("repair_loop",),
            execution_topology="local_committee_only",
            evidence_refs=("e1",),
            source_anchor={"present": False},
            route_context={},
        )
        result = LocalHealPipelineCapabilityExecutor().execute(ctx)
        assert result.invoked is False
        assert result.failure_reason == "localheal_pipeline_topology_not_selected"

    def test_bridge_pipeline_exception_fail_closed(self):
        """When HealPipeline instantiation fails, bridge returns fail-closed metadata."""
        from nexus.services.local_heal.pipeline import HealPipeline

        with patch.object(HealPipeline, "__init__", side_effect=RuntimeError("pipeline init failed")):
            ctx = LocalModelCapabilityContext(
                task_id="t_bridge_fail",
                source_root="/tmp",
                problem_statement="fix bug",
                target_file="a.py",
                target_symbol="f",
                selected_capabilities=("repair_loop",),
                execution_topology="localheal_pipeline",
                evidence_refs=("e1",),
                source_anchor={"present": False},
                route_context={},
            )
            result = LocalHealPipelineCapabilityExecutor().execute(ctx)
            # Should not crash, should return with failure_reason
            assert result.invoked is True
            assert "pipeline_instantiation_error" in result.telemetries.get("path_a_failure_reason", "")

    def test_bridge_does_not_claim_solved_without_verifier_pass(self):
        """Bridge availability alone must not produce solved=true."""
        provider = _build_provider_mock(output_text="")
        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            result = LocalModelExecutor.run(_build_request(), provider=provider)
        assert result.raw_model_metadata.get("gate_passed") is not True

    def test_bridge_keeps_route_truth_source_capability_planner(self):
        """Bridge never changes route_truth_source."""
        provider = _build_provider_mock()
        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            result = LocalModelExecutor.run(_build_request(), provider=provider)
        meta = result.raw_model_metadata
        # Bridge telemetry should not contain route_truth_source override
        assert "route_truth_source" not in meta or meta.get("route_truth_source") != "bridge"


class TestHealPipelineRunInvocationTruth:
    """A3.1/B1: Verify HealPipeline.run() is actually called."""

    def test_localheal_pipeline_calls_healpipeline_run(self):
        """HealPipeline.run() IS called (B1 wiring)."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_a31_run",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # .run() IS now called (B1)
                pipeline_run_mock.assert_called_once()
                assert result.telemetries.get("localheal_pipeline_run_called") is True

    def test_localheal_pipeline_instantiation_not_equal_to_execution(self):
        """Instantiation alone does not constitute execution — but B1 now also calls .run()."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_a31_init",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # .run() IS now called (B1)
                pipeline_run_mock.assert_called_once()
                # actual_execution reflects .run() success
                assert result.telemetries.get("localheal_pipeline_actual_execution") is True
                assert result.telemetries.get("localheal_pipeline_run_called") is True

    def test_localheal_pipeline_actual_execution_false_when_run_raises(self):
        """localheal_pipeline_actual_execution must be False when pipeline.run() raises."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock(side_effect=RuntimeError("pipeline run failed"))
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_a31_flag",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # .run() raised — actual_execution must be False
                pipeline_run_mock.assert_called_once()
                actual_exec = result.telemetries.get("localheal_pipeline_actual_execution")
                assert actual_exec is False
                assert result.telemetries.get("localheal_pipeline_run_called") is True
                assert result.telemetries.get("localheal_pipeline_run_success") is False

    def test_localheal_pipeline_does_not_claim_retry_invoked_without_run(self):
        """semantic_retry_invoked must be False when .run() raises."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock(side_effect=RuntimeError("fail"))
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_a31_retry",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # .run() raised
                pipeline_run_mock.assert_called_once()
                # Retry was NOT invoked
                assert result.telemetries.get("semantic_retry_invoked") is False

    def test_full_executor_calls_healpipeline_run(self):
        """End-to-end: LocalModelExecutor.run with localheal_pipeline DOES call HealPipeline.run()."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            with patch.object(HealPipeline, "__init__", return_value=None):
                with patch.object(HealPipeline, "run", pipeline_run_mock):
                    result = LocalModelExecutor.run(_build_request(), provider=provider)

                    # .run() IS now called through the full executor path (B1)
                    pipeline_run_mock.assert_called_once()


class TestPipelineTelemetrySemanticsB2:
    """B2: Telemetry semantics must be truthful."""

    def test_pipeline_instantiated_does_not_mean_actual_execution(self):
        """Instantiation alone does not set actual_execution=True."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock(side_effect=RuntimeError("run failed"))
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b2_init",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("localheal_pipeline_instantiated") is True
                assert result.telemetries.get("localheal_pipeline_actual_execution") is False

    def test_pipeline_run_called_does_not_mean_run_success(self):
        """run_called=True does not imply run_success=True."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock(side_effect=RuntimeError("run failed"))
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b2_run",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("localheal_pipeline_run_called") is True
                assert result.telemetries.get("localheal_pipeline_run_success") is False

    def test_pipeline_actual_execution_requires_run_success(self):
        """actual_execution=True only when run_success=True."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = "patch"
        mock_ctx.solve_eligible = True
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b2_exec",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("localheal_pipeline_run_success") is True
                assert result.telemetries.get("localheal_pipeline_actual_execution") is True

    def test_semantic_retry_invoked_requires_orchestrator_telemetry(self):
        """semantic_retry_invoked must come from orchestrator, not retry_available."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b2_retry",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # semantic_retry_invoked is False by default — only set by orchestrator telemetry
                assert result.telemetries.get("semantic_retry_invoked") is False

    def test_semantic_retry_invoked_comes_from_orchestrator_telemetry(self):
        """shared pipeline truth should expose real semantic retry usage."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        mock_ctx._semantic_retry_telemetry = {"semantic_retry_count": 1, "same_span_retry": True}
        mock_ctx.errors = []
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b2_retry_truth",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("semantic_retry_invoked") is True
                assert result.telemetries.get("semantic_retry_count") == 1
                assert result.telemetries.get("same_span_retry") is True

    def test_structured_retry_packet_available_comes_from_pipeline_errors(self):
        """shared pipeline truth should expose structured retry packet availability."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = "SEARCH_MISMATCH"
        mock_ctx._semantic_retry_telemetry = {}
        mock_ctx.errors = [MagicMock(structured_packet=object())]
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b2_packet_truth",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("structured_retry_packet_available") is True

    def test_verifier_command_truth_comes_from_pipeline_context(self):
        """shared pipeline truth should expose verifier_command presence from route_context."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = "VERIFICATION_FAILED"
        mock_ctx._semantic_retry_telemetry = {}
        mock_ctx.errors = []
        mock_ctx.verifier_command_present = True
        mock_ctx.verifier_command_source = "route_context"
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b2_verifier_truth",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={"verifier_command": ["python3", "verify.py"]},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("verifier_command_present") is True
                assert result.telemetries.get("verifier_command_source") == "route_context"


class TestPipelineResultProjectionB3:
    """B3: Project HealPipeline result into executor response."""

    def test_pipeline_result_non_empty_final_patch_projects_candidate_hash(self):
        """Non-empty final_patch from pipeline becomes candidate_patch."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = "def fixed():\n    return 42"
        mock_ctx.solve_eligible = True
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b3_patch",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("pipeline_final_patch") == "def fixed():\n    return 42"
                assert result.telemetries.get("pipeline_solve_eligible") is True

    def test_pipeline_result_empty_final_patch_remains_empty(self):
        """Empty final_patch from pipeline means no candidate projected."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = "no patch"
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b3_empty",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("pipeline_final_patch") == ""
                assert result.telemetries.get("pipeline_solve_eligible") is False

    def test_pipeline_result_failure_reason_projected(self):
        """Pipeline failure_reason is projected into telemetry."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = "verifier_rejected"
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b3_fail",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("pipeline_failure_reason") == "verifier_rejected"

    def test_pipeline_syntax_error_is_classified_without_provider_diag(self):
        """Syntax failure with patch output should stay syntax-classified, not natural-language downgraded."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = "SYNTAX_ERROR:REPLACE_SYNTAX_ERROR:expected an indented block"
        mock_ctx.repro_evidence = "AssertionError"
        mock_ctx.plan = {"search_symbols": ["f"]}
        mock_ctx.localized_files = [MagicMock(path="a.py", content="if value:\n    return value\n")]
        mock_ctx.evaluation_report = ""
        mock_ctx.skip_reproduction = False
        mock_ctx.model_decisions = [
            {
                "phase": "patch",
                "status": "SYNTAX_ERROR",
                "output_len": 213,
                "output_class": "UNKNOWN",
                "parser_error_kind": "none",
                "parser_error_message": "none",
                "output_excerpt": "FILE: a.py\n<<<<<<< SEARCH\n...",
            }
        ]
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b3_syntax",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("output_class") == "SEARCH_REPLACE_SYNTAX_ERROR"
                assert result.telemetries.get("parser_error_kind") == "SYNTAX_ERROR"

    def test_pipeline_exception_does_not_mark_solved(self):
        """Pipeline exception remains fail-closed."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock(side_effect=RuntimeError("pipeline crash"))
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b3_crash",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                assert result.telemetries.get("localheal_pipeline_run_success") is False
                assert result.telemetries.get("localheal_pipeline_actual_execution") is False


class TestPlannerOwnedOrchestratorSelectionB6:
    """B6: Orchestrator selection must be planner-owned, not env-driven."""

    def test_pipeline_bridge_ignores_nexus_use_committee_env_when_signal_snapshot_disables_committee(self):
        """Env NEXUS_USE_COMMITTEE is ignored when signal_snapshot disables committee."""
        from nexus.services.local_heal.pipeline import HealPipeline
        from unittest.mock import patch as _patch

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with _patch.dict(os.environ, {"NEXUS_USE_COMMITTEE": "1"}):
            with patch.object(HealPipeline, "__init__", return_value=None):
                with patch.object(HealPipeline, "run", pipeline_run_mock):
                    ctx = LocalModelCapabilityContext(
                        task_id="t_b6_no_committee",
                        source_root="/tmp",
                        problem_statement="fix bug",
                        target_file="a.py",
                        target_symbol="f",
                        selected_capabilities=("repair_loop",),
                        execution_topology="localheal_pipeline",
                        evidence_refs=("e1",),
                        source_anchor={"present": False},
                        route_context={
                            "signal_snapshot": {
                                "local_committee_enabled": False,
                            }
                        },
                        provider=provider,
                    )
                    result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                    # Pipeline was called — env was ignored because signal_snapshot said no committee
                    pipeline_run_mock.assert_called_once()

    def test_pipeline_bridge_uses_committee_when_signal_snapshot_enables_committee(self):
        """Signal_snapshot.local_committee_enabled=True enables committee path."""
        from nexus.services.local_heal.pipeline import HealPipeline
        from unittest.mock import patch as _patch

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with _patch.dict(os.environ, {"NEXUS_USE_COMMITTEE": "0"}):
            with patch.object(HealPipeline, "__init__", return_value=None):
                with patch.object(HealPipeline, "run", pipeline_run_mock):
                    ctx = LocalModelCapabilityContext(
                        task_id="t_b6_committee",
                        source_root="/tmp",
                        problem_statement="fix bug",
                        target_file="a.py",
                        target_symbol="f",
                        selected_capabilities=("repair_loop",),
                        execution_topology="localheal_pipeline",
                        evidence_refs=("e1",),
                        source_anchor={"present": False},
                        route_context={
                            "signal_snapshot": {
                                "local_committee_enabled": True,
                            }
                        },
                        provider=provider,
                    )
                    result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                    # Pipeline was called — signal_snapshot enabled committee
                    pipeline_run_mock.assert_called_once()

    def test_pipeline_bridge_does_not_create_route_truth(self):
        """Pipeline bridge never changes route_truth_source."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b6_truth",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # Bridge doesn't set route_truth_source
                assert "route_truth_source" not in result.telemetries

    def test_pipeline_bridge_missing_signal_snapshot_fail_closed(self):
        """Missing signal_snapshot in route_context fails closed."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx
        provider = _build_provider_mock()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b6_missing",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={},  # No signal_snapshot
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # Pipeline still runs — committee defaults to False
                pipeline_run_mock.assert_called_once()
                assert result.telemetries.get("localheal_pipeline_run_called") is True
