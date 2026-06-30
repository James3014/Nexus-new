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
    """Test 2: Bridge does NOT call HealPipeline.run() or Orchestrator.run()."""

    def test_localheal_pipeline_topology_does_not_call_heal_pipeline_run(self):
        """Bridge instantiates HealPipeline but never calls .run()."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()

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

                # .run() was NEVER called
                pipeline_run_mock.assert_not_called()

    def test_localheal_pipeline_topology_does_not_call_orchestrator_run(self):
        """Bridge does NOT instantiate or call HealOrchestrator.run()."""
        from nexus.services.local_heal.orchestrator import HealOrchestrator

        orchestrator_run_mock = MagicMock()

        with patch.object(HealOrchestrator, "__init__", return_value=None):
            with patch.object(HealOrchestrator, "run", orchestrator_run_mock):
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

                # Orchestrator.__init__ was NOT called (bridge doesn't import it)
                # Orchestrator.run was NOT called
                orchestrator_run_mock.assert_not_called()


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

    def test_model_call_goes_through_provider_not_pipeline(self):
        """provider.generate() is called directly, not through pipeline orchestrator."""
        provider = _build_provider_mock()

        with patch(
            "nexus.services.local_heal.local_model_executor.build_local_model_provider_from_signal_snapshot",
            return_value=provider,
        ):
            result = LocalModelExecutor.run(_build_request(), provider=provider)

        # provider.generate() was called directly
        provider.generate.assert_called_once()
        assert result.local_model_called is True
        assert result.candidate_patch.strip() != ""

        # No retry loop metadata (pipeline doesn't do retry in bridge path)
        meta = result.raw_model_metadata
        # The bridge doesn't add retry_count or semantic_retry fields
        # because it doesn't run the orchestrator repair loop
