from __future__ import annotations

import hashlib
import pytest

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
    _resolve_execution_topology,
)
from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)


def _make_cascade_request(
    task_id: str,
    problem_statement: str = "test",
    execution_topology: str = "local_cascade",
    cascade_models: tuple[str, ...] | None = None,
    extra_signal: dict | None = None,
    dry_run: bool = False,
) -> LocalModelExecutorRequest:
    snap: dict[str, object] = {
        "execution_topology": execution_topology,
        "model_call_allowed": True,
        "selected_executor": "local_model",
        "protocol_mode": "anchored_edit",
    }
    if cascade_models is not None:
        snap["cascade_models"] = cascade_models
    if extra_signal:
        snap.update(extra_signal)
    return LocalModelExecutorRequest(
        task_id=task_id,
        problem_statement=problem_statement,
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=dry_run,
        route_context={"signal_snapshot": snap},
        mutation_allowed=False,
        verifier_allowed=False,
    )


class TestCascadeTopologyAcceptance:

    def test_cascade_topology_accepted_by_resolve(self):
        req = _make_cascade_request("cascade-accept-1")
        topology = _resolve_execution_topology(req)
        assert topology == "local_cascade"

    def test_cascade_topology_does_not_require_executor_model(self):
        req = _make_cascade_request("cascade-accept-2")
        snap = req.route_context.get("signal_snapshot", {})
        assert "executor_model" not in snap
        topology = _resolve_execution_topology(req)
        assert topology == "local_cascade"


class TestCascadeFailClosed:

    def test_cascade_all_models_fail_with_empty_output(self):
        req = _make_cascade_request("cascade-fail-1")
        provider = InjectedLocalModelProvider(lambda _: "")
        resp = LocalModelExecutor.run(req, provider=provider)
        assert resp.invoked is True
        assert resp.local_model_called is True
        assert resp.candidate_patch == ""
        assert resp.error == "all_cascade_models_failed"
        assert resp.reasoning_summary == "cascade_fail_closed"
        meta = resp.raw_model_metadata
        assert meta.get("execution_topology") == "local_cascade"
        assert meta.get("cascade_failed_at_final_stage") is True
        assert len(meta.get("cascade_stages_run", ())) > 0

    def test_cascade_fail_closed_sets_cascade_stages_run(self):
        req = _make_cascade_request("cascade-fail-2")
        provider = InjectedLocalModelProvider(lambda _: "")
        resp = LocalModelExecutor.run(req, provider=provider)
        meta = resp.raw_model_metadata
        assert resp.cascade_stages_run == meta.get("cascade_stages_run")
        assert len(resp.cascade_stages_run) > 0

    def test_inert_provider_is_not_cascade(self):
        req = _make_cascade_request("cascade-fail-3")
        provider = InertLocalModelProvider()
        resp = LocalModelExecutor.run(req, provider=provider)
        assert resp.invoked is True
        assert resp.local_model_called is False
        assert resp.error == "provider_unavailable"


class TestCascadeSuccess:

    def test_cascade_first_model_succeeds(self):
        call_count = 0

        def mock_gen(req: LocalModelProviderRequest) -> str:
            nonlocal call_count
            call_count += 1
            return "patch from cascade"

        provider = InjectedLocalModelProvider(mock_gen)
        req = _make_cascade_request("cascade-win-1")
        resp = LocalModelExecutor.run(req, provider=provider)
        assert resp.invoked is True
        assert resp.local_model_called is True
        assert resp.candidate_patch == "patch from cascade"
        assert resp.error == ""
        assert resp.reasoning_summary.startswith("cascade_winner_")
        assert "cascade_failed_at_final_stage" not in resp.raw_model_metadata or resp.raw_model_metadata.get("cascade_failed_at_final_stage") is not True
        assert call_count >= 1

    def test_cascade_with_custom_models(self):
        custom_models = ("qwen2.5-coder:1.5b", "deepseek-coder:1.3b")

        def mock_gen(req: LocalModelProviderRequest) -> str:
            return f"output_for_{req.model_name}"

        provider = InjectedLocalModelProvider(mock_gen)
        req = _make_cascade_request(
            "cascade-win-2",
            cascade_models=custom_models,
        )
        resp = LocalModelExecutor.run(req, provider=provider)
        assert resp.invoked is True
        assert resp.local_model_called is True
        assert resp.candidate_patch == "output_for_qwen2.5-coder:1.5b"
        assert resp.error == ""
        meta = resp.raw_model_metadata
        assert meta.get("cascade_models") == custom_models
        assert meta.get("cascade_winner_model") == "qwen2.5-coder:1.5b"
