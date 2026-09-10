from __future__ import annotations

import builtins
import hashlib
import sys
from subprocess import TimeoutExpired
from types import SimpleNamespace

import pytest

from nexus.services.unified_runtime import build_registered_online_invoker


def _context() -> dict:
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle

    bundle = build_capability_evidence_bundle(
        task_id="task-online",
        workspace_revision="r" * 40,
        task_statement="bounded online task",
        plan_payload={"selected_capabilities": ["memory"]},
        plan_hash="p" * 64,
        planner_decision_id="d" * 64,
        capability_results={
            "memory": {
                "status": "SUCCEEDED",
                "invoked": True,
                "evidence_refs": ["ev:1"],
                "response": {
                    "consumer_payload": {
                        "fields": {"summary": "bounded memory result", "evidence_id": "ev:1"}
                    }
                },
            }
        },
        selected_capabilities=["memory"],
    )
    return {
        "schema": "nexus.unified_runtime.request.v1",
        "task_id": "task-online",
        "task_statement": "bounded online task",
        "execution_attempt": {"attempt_id": "attempt-1"},
        "online_prompt": "bounded online task",
        "planner_decision_id": "d" * 64,
        "planner": {
            "plan_hash": "p" * 64,
            "signal_snapshot": {"selected_capabilities": ["memory"]},
        },
        "capability_evidence_bundle": bundle,
        "gateway_invocation_authority": {
            "gate_passed": True,
            "resolved_worker_id": "worker-a",
            "resolved_provider": "codex",
            "resolved_model": "gpt-5.6-luna",
        },
    }


def test_canonical_bundle_invalid_blocks_before_runner():
    calls = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    context = _context()
    context["capability_evidence_bundle"]["task_id"] = "foreign"
    invoker = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )
    result = invoker(context)
    assert result["invoked"] is False
    assert "context_package_invalid" in result["error"]
    assert calls == []


@pytest.mark.parametrize("removed", ["execution_attempt", "planner_decision_id", "planner"])
def test_canonical_context_missing_bundle_blocks_before_runner(removed):
    calls = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    context = _context()
    context.pop(removed)
    del context["capability_evidence_bundle"]
    invoker = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )
    result = invoker(context)
    assert result["invoked"] is False
    assert result["error"] == "canonical_runtime_context_bundle_missing"
    assert calls == []


def test_missing_runtime_dependency_blocks_before_runner(monkeypatch):
    calls = []

    def runner(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    original_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "nexus_runtime.task_context":
            raise ModuleNotFoundError("nexus_runtime")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    result = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )(_context())
    assert result["invoked"] is False
    assert result["error"] == "canonical_runtime_dependency_missing"
    assert calls == []


def test_final_transport_input_contains_bounded_package_and_hashes_exact_input():
    captured = {}

    def runner(argv, **kwargs):
        captured.update(argv=argv, kwargs=kwargs)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    invoker = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
        include_local_context=False,
    )
    result = invoker(_context())
    final_input = captured["kwargs"]["input"]
    assert "[NEXUS MODEL CONTEXT]" in final_input
    assert "bounded memory result" in final_input
    assert (
        result["process_evidence"]["provider_input_sha256"]
        == hashlib.sha256(final_input.encode()).hexdigest()
    )
    assert result["model_context_consumption"]["physical_consumption_state"] == "NOT_PROVEN"


def test_final_input_includes_local_capability_and_payload_before_package():
    captured = {}

    def runner(argv, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    context = _context()
    context.update({
        "online_payload": "payload-boundary",
        "local": {"invoked": True, "response": {"concise_summary": "local-safe"}},
        "capability_results": {"memory": {"status": "SUCCEEDED", "evidence_refs": ["ev:1"]}},
    })
    result = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )(context)
    final_input = captured["input"]
    assert "[LOCAL_ASSIST_CONTEXT]" in final_input
    assert "[CAPABILITY_CONTEXT]" not in final_input
    assert "payload-boundary" in final_input
    assert "[NEXUS MODEL CONTEXT]" in final_input
    assert (
        result["process_evidence"]["provider_input_sha256"]
        == hashlib.sha256(final_input.encode()).hexdigest()
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c.update(task_id="foreign"),
        lambda c: c["planner"].update(plan_hash="foreign"),
        lambda c: c["capability_evidence_bundle"].update(bundle_hash="0" * 64),
    ],
)
def test_canonical_tamper_blocks_before_runner(mutation):
    calls = []

    def runner(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    context = _context()
    mutation(context)
    result = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )(context)
    assert result["invoked"] is False
    assert calls == []


@pytest.mark.parametrize("failure", [TimeoutExpired("provider", 1), OSError("offline")])
def test_transport_failure_preserves_context_receipt_without_retry(failure):
    calls = []

    def runner(*args, **kwargs):
        calls.append(True)
        raise failure

    result = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )(_context())
    assert result["provider_call_count"] == (1 if isinstance(failure, TimeoutExpired) else 0)
    assert len(calls) == 1
    assert result["model_context_consumption"]["physical_consumption_state"] == "NOT_PROVEN"
    assert (
        result["model_context_consumption"]["provider_input_sha256"]
        == result["process_evidence"]["provider_input_sha256"]
    )


def test_injected_runner_never_proves_physical_consumption():
    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    result = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )(_context())
    assert result["model_context_consumption"]["physical_consumption_state"] == "NOT_PROVEN"


def test_unified_runtime_admitted_codex_registered_invoker_reaches_context_receipt():
    from dataclasses import replace

    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import (
        _DETERMINISTIC_CAPABILITY_INVOKERS,
        _admit_gateway_request,
        _learning,
        _Planner,
        _request,
        _verifier,
    )

    class AdmittedPlanner(_Planner):
        def plan(self, **kwargs):
            plan = super().plan(**kwargs)
            snapshot = dict(plan.signal_snapshot)
            snapshot["workforce_demands"] = {
                "schema": "nexus.workforce_demands.v1",
                "route_authority": "CapabilityPlanner",
                "demands": [
                    {
                        "schema": "nexus.workforce_demand.v1",
                        "demand_id": "online-runtime-1",
                        "execution_channel": "online",
                        "requested_role": "main_engineering",
                        "minimum_autonomy": "L1",
                        "context_class": "nexus_bounded",
                        "mutation_intent": True,
                        "external_verification_required": True,
                        "route_authority": "CapabilityPlanner",
                    }
                ],
            }
            return replace(plan, signal_snapshot=snapshot)

    captured = {}

    def runner(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return SimpleNamespace(returncode=0, stdout="provider-output", stderr="")

    invoker = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
        include_local_context=False,
    )
    request = _admit_gateway_request(_request(), online_worker="codex_luna")
    receipt = UnifiedRuntime(planner=AdmittedPlanner()).run(
        request,
        online_invoker=invoker,
        capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS,
        verifier=_verifier,
        learning=_learning,
    )
    assert captured["input"]
    assert receipt["online"]["status"] == "SUCCEEDED"
    result = receipt["online"].get("response") or receipt["online"]
    assert result["model_context_consumption"]["physical_consumption_state"] == "NOT_PROVEN"
    assert result["model_context_consumption"]["proof_basis"] not in {
        "ONLINE_WORKER_BINDING_MISSING",
        "INVALID",
    }
    assert (
        result["process_evidence"]["provider_input_sha256"]
        == hashlib.sha256(captured["input"].encode()).hexdigest()
    )


def test_canonical_transport_forwards_bounded_evidence_without_raw_capability_responses():
    captured = {}

    def runner(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    context = _context()
    context["capability_results"] = {
        "memory": {
            "status": "SUCCEEDED",
            "evidence_refs": ["ev:1"],
            "response": {"private_reasoning": "PRIVATE_REASONING_SENTINEL_NOT_REAL_DATA"},
        },
        "unselected": {
            "status": "SUCCEEDED",
            "evidence_refs": ["ev:foreign"],
            "response": {"private_reasoning": "UNSELECTED_PRIVATE_SENTINEL"},
        },
    }
    result = build_registered_online_invoker(
        "codex",
        command=(sys.executable, "exec", "-m", "gpt-5.6-luna", "-c", "pass"),
        model_name="gpt-5.6-luna",
        runner=runner,
    )(context)
    final_input = captured["input"]
    assert "PRIVATE_REASONING_SENTINEL_NOT_REAL_DATA" not in final_input
    assert "UNSELECTED_PRIVATE_SENTINEL" not in final_input
    assert "unselected" not in final_input
    assert "ev:foreign" not in final_input
    assert "bounded memory result" in final_input
    assert (
        result["model_context_consumption"]["provider_input_sha256"]
        == hashlib.sha256(final_input.encode()).hexdigest()
    )
