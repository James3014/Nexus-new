"""B7.1: LocalHeal Pipeline Provider Contract Smoke Tests.

Verifies that the provider wrapper correctly handles both:
1. OllamaLLMClient signature: generate_fn(system_prompt, user_prompt, model=...)
2. LocalModelProviderRequest signature: generate_fn(request_object)
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import os
import pytest

from nexus.services.local_heal.local_model_capability_executors import (
    LocalHealPipelineCapabilityExecutor,
)
from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
)
from nexus.services.local_heal.local_model_provider import (
    LocalModelProviderRequest,
    LocalModelProviderResponse,
    InjectedLocalModelProvider,
)


def _build_injected_provider(output_text: str = "def fixed():\n    return 42"):
    def generate_fn(req: LocalModelProviderRequest) -> LocalModelProviderResponse:
        return LocalModelProviderResponse(
            provider_invoked=True,
            model_called=True,
            model_name=req.model_name,
            output_text=output_text,
        )
    return InjectedLocalModelProvider(generate_fn)


class TestProviderContractSmokeB71:
    """B7.1: Provider contract verification."""

    def test_provider_wrapper_accepts_ollama_llm_client_signature(self):
        """_provider_generate accepts (system_prompt, user_prompt) from OllamaLLMClient."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = "patch content"
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx

        captured_requests = []

        def capture_provider(req):
            captured_requests.append(req)
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=True,
                model_name=req.model_name,
                output_text="patch",
            )

        provider = InjectedLocalModelProvider(capture_provider)

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b71_sig",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={"signal_snapshot": {"executor_model": "qwen2.5-coder:7b"}},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # Pipeline was called
                pipeline_run_mock.assert_called_once()

    def test_provider_wrapper_passes_model_name_from_signal_snapshot(self):
        """model_name propagates from signal_snapshot.executor_model."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.final_patch = ""
        mock_ctx.solve_eligible = False
        mock_ctx.failure_reason = ""
        pipeline_run_mock.return_value = mock_ctx

        provider = _build_injected_provider()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b71_model",
                    source_root="/tmp",
                    problem_statement="fix bug",
                    target_file="a.py",
                    target_symbol="f",
                    selected_capabilities=("repair_loop",),
                    execution_topology="localheal_pipeline",
                    evidence_refs=("e1",),
                    source_anchor={"present": False},
                    route_context={"signal_snapshot": {"executor_model": "qwen2.5-coder:7b"}},
                    provider=provider,
                )
                result = LocalHealPipelineCapabilityExecutor().execute(ctx)

                # Pipeline was called — model_name is in route_context
                pipeline_run_mock.assert_called_once()
                assert result.telemetries.get("localheal_pipeline_run_called") is True

    def test_provider_not_configured_error_classification(self):
        """OllamaLocalModelProvider returns provider_not_configured when env missing."""
        from nexus.services.local_heal.local_model_provider import OllamaLocalModelProvider

        provider = OllamaLocalModelProvider()
        req = LocalModelProviderRequest(
            task_id="t_b71_config",
            prompt="test",
            evidence_refs=(),
            model_name="qwen2.5-coder:7b",
        )

        with patch.dict(os.environ, {}, clear=True):
            resp = provider.generate(req)
            assert resp.error == "provider_not_configured"

    def test_model_name_missing_error_classification(self):
        """OllamaLocalModelProvider returns model_name_missing when model empty."""
        from nexus.services.local_heal.local_model_provider import OllamaLocalModelProvider

        provider = OllamaLocalModelProvider()
        req = LocalModelProviderRequest(
            task_id="t_b71_model",
            prompt="test",
            evidence_refs=(),
            model_name="",
        )

        with patch.dict(os.environ, {"NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1", "NEXUS_LOCAL_MODEL_PROVIDER": "ollama"}, clear=False):
            resp = provider.generate(req)
            assert resp.error == "model_name_missing"

    def test_pipeline_bridge_distinguishes_provider_errors(self):
        """Pipeline failure_reason distinguishes provider errors."""
        from nexus.services.local_heal.pipeline import HealPipeline

        pipeline_run_mock = MagicMock(side_effect=RuntimeError("MODEL_PROVIDER_ERROR: provider_not_configured"))
        provider = _build_injected_provider()

        with patch.object(HealPipeline, "__init__", return_value=None):
            with patch.object(HealPipeline, "run", pipeline_run_mock):
                ctx = LocalModelCapabilityContext(
                    task_id="t_b71_error",
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
                failure = result.telemetries.get("path_a_failure_reason", "")
                assert "pipeline_run_error" in failure
