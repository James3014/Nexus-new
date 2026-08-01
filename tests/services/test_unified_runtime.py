from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path[:1]:
    sys.path.insert(0, str(ROOT))

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.evidence.receipt_base import validate_receipt_base
from nexus.services.local_assist_service import (
    REQUEST_SCHEMA,
    LocalAssistRequest,
    LocalAssistService,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.unified_runtime import (
    ONLINE_CLI_SPEC_REGISTRY,
    OnlineCliSpec,
    REGISTERED_CLI_MODEL_BINDING_FLAGS,
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    build_execution_replan_request,
    build_local_ast_capability_invoker,
    build_local_memory_capability_invoker,
    build_local_search_ranking_capability_invoker,
    build_online_route,
    build_prompt_compression_capability_invoker,
    build_registered_online_invoker,
    build_structured_online_invoker,
    build_subprocess_online_invoker,
    extract_online_stage_payload,
    resolve_online_transport_binding,
    resolve_registered_online_cli_spec,
)


@dataclass
class _Planner:
    calls: int = 0

    def plan(self, **_: object) -> CapabilityPlan:
        self.calls += 1
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=["memory", "local_model_executor"],
            required_capabilities=["memory", "local_model_executor"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=["claim_fail_closed"],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
        )


def _request(*, local_enabled: bool = False, online_enabled: bool = True) -> UnifiedRuntimeRequest:
    return UnifiedRuntimeRequest(
        task_id="unified-test-001",
        workspace_revision="rev-1",
        task_statement="trace one runtime task",
        task_type="repair",
        route={"recommended_flow": "direct"},
        online_enabled=online_enabled,
        local_enabled=local_enabled,
        local_request=(
            {"task_id": "unified-test-001", "action": "candidate"} if local_enabled else None
        ),
    )


def _online(_: dict) -> dict:
    return {
        "invoked": True,
        "output_delivered": True,
        "gate_passed": True,
        "provider_call_count": 1,
        "evidence_refs": ["online:test:invocation"],
    }


def _verifier(context: dict) -> dict:
    bundle = context.get("capability_evidence_bundle") if isinstance(context.get("capability_evidence_bundle"), dict) else {}
    src = str(context.get("source_hash") or bundle.get("source_hash") or "")
    task_id = str(context.get("task_id") or "")
    return {
        "status": "SUCCEEDED",
        "task_id": task_id,
        "invoked": True,
        "gate_passed": True,
        "verifier_status": "pass",
        # Must be sha256: + 64 hex (or bare 64 hex) — length fallbacks rejected.
        "verifier_artifact": "sha256:" + ("ab" * 32),
        "source_hash": src,
        "evidence": "deterministic verifier",
        "evidence_refs": ["verifier:test:pass"],
    }


def _learning(_: dict) -> dict:
    return {
        "status": "SUCCEEDED",
        "invoked": True,
        "gate_passed": True,
        "evidence": "learning closure",
        "evidence_refs": ["learning:test:recorded"],
    }


_DETERMINISTIC_CAPABILITY_INVOKERS: dict[str, Callable[[dict], dict]] = {
    name: (lambda ctx, _n=name: {
        "task_id": ctx["task_id"],
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": [f"test:{_n}:{ctx['task_id']}:fixture"],
    })
    for name in (
        "harness_preflight_sensor",
        "repair_loop",
        "delivery_gate",
        "mempalace_gate",
        "artifact_gate",
        "claim_gate",
        "research_route",
        "memory",
        "local_model_executor",
    )
}


def test_runtime_calls_one_planner_and_emits_one_receipt() -> None:
    planner = _Planner()
    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        _request(),
        capability_invokers={
            "memory": lambda ctx: {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"memory:{ctx['task_id']}:fixture"],
            },
        },
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert planner.calls == 1
    assert receipt["schema"] == "nexus.unified_runtime.receipt.v1"
    assert receipt["task_id"] == "unified-test-001"
    assert receipt["receipt_complete"] is True
    assert [stage["name"] for stage in receipt["stages"]] == [
        "planner",
        "shared_capability_evidence",
        "local",
        "online",
        "verifier",
        "learning",
    ]
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt["planner"]["required_capabilities"] == ["memory", "local_model_executor"]
    assert receipt["planner"]["conditional_capabilities"] == []
    assert receipt["planner"]["pending_capabilities"] == []
    assert all(item["task_id"] == receipt["task_id"] for item in receipt["capabilities"])
    # FCM F1: selected names are INVOKED (stub/real) or SKIPPED — never silent omit.
    assert all(
        item["status"] in {"INVOKED", "SKIPPED", "SELECTED_NOT_EXECUTED"}
        for item in receipt["capabilities"]
    )
    assert receipt["capability_coverage"]["coverage_ok"] is True


def test_runtime_is_fail_closed_without_online_invoker() -> None:
    runtime = UnifiedRuntime(planner=_Planner())
    receipt = runtime.run(_request(), verifier=_verifier, learning=_learning)

    assert receipt["online"]["status"] == "NOT_RUN"
    assert receipt["receipt_complete"] is False
    assert receipt["claim_boundary"]["receipt_complete"] is False


def test_runtime_rejects_mismatched_local_task_identity() -> None:
    planner = _Planner()
    runtime = UnifiedRuntime(planner=planner, local_service=object())
    request = UnifiedRuntimeRequest(
        task_id="unified-test-001",
        workspace_revision="rev-1",
        task_statement="trace one runtime task",
        task_type="repair",
        route={"recommended_flow": "direct"},
        online_enabled=False,
        local_enabled=True,
        local_request={"task_id": "different-task"},
    )
    receipt = runtime.run(request, verifier=_verifier, learning=_learning)

    assert receipt["local"]["status"] == "BLOCKED"


def test_runtime_rejects_mismatched_online_and_learning_identity() -> None:
    runtime = UnifiedRuntime(planner=_Planner())
    receipt = runtime.run(
        _request(),
        online_invoker=lambda _context: {
            "task_id": "other-task",
            "invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "provider_call_count": 1,
            "evidence_refs": ["online:other-task:call"],
        },
        verifier=_verifier,
        learning=lambda _context: {
            "task_id": "other-task",
            "status": "pass",
            "evidence": "wrong task learning",
            "evidence_refs": ["learning:other-task"],
        },
    )

    assert receipt["online"]["status"] == "FAILED"
    assert receipt["online"]["reason"] == "online_task_id_mismatch"
    assert receipt["learning"]["status"] == "FAILED"
    assert receipt["learning"]["task_identity_shared"] is False
    assert receipt["receipt_complete"] is False


class _LocalService:
    def __init__(self) -> None:
        self.seen_snapshot: dict = {}

    def handle(self, request: dict) -> dict:
        self.seen_snapshot = dict(request.get("planner_snapshot") or {})
        action = str(request.get("action") or "candidate")
        # R4.2: executor INVOKED proof requires physical_callable + executor_invoked.
        is_executor = action in {"candidate", "verified-subtask"}
        return {
            "task_id": request["task_id"],
            "action": action,
            "local_model_invoked": True,
            "output_delivered": True,
            "executor_invoked": is_executor,
            "physical_callable": "LocalModelExecutor.run" if is_executor else "LocalModelProvider.generate",
            "receipt_path": "/tmp/local-receipt.json",
            "evidence_refs": ["local:test:invocation"],
            "verifier_summary": {"verifier_status": "not_run"},
            "local_outputs": {
                "concise_summary": f"action={action};status=succeeded;evidence_count=1",
            },
        }


def test_hybrid_receipt_keeps_local_assist_and_online_on_same_task() -> None:
    local_service = _LocalService()
    runtime = UnifiedRuntime(planner=_Planner(), local_service=local_service)
    receipt = runtime.run(
        _request(local_enabled=True),
        capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS,
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["receipt_complete"] is True
    assert receipt["local"]["invoked"] is True
    assert local_service.seen_snapshot.get("route_truth_source") == "CapabilityPlanner"
    assert local_service.seen_snapshot.get("planner_decision_id") == receipt["planner_decision_id"]
    assert receipt["online"]["invoked"] is True
    assert receipt["claim_boundary"]["local_online_continuation"] is True
    assert receipt["delegation"] == {
        "planner": "Nexus",
        "local_assist": "Local",
        "online_provider": "Online",
        "verifier": "Hybrid",
        "learning": "Hybrid",
    }


def test_hybrid_receipt_records_explicit_online_capability_delegation() -> None:
    local_service = _LocalService()
    request = UnifiedRuntimeRequest(
        **{
            **_request(local_enabled=True).__dict__,
            "route": {
                "recommended_flow": "hybrid",
                "local_enabled": True,
                "online_capabilities": ("memory",),
            },
        }
    )
    receipt = UnifiedRuntime(planner=_Planner(), local_service=local_service).run(
        request,
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    delegated = {item["name"]: item for item in receipt["capabilities"]}
    assert delegated["memory"]["delegated_to"] == "Online"
    assert delegated["memory"]["status"] == "INVOKED"
    assert delegated["local_model_executor"]["delegated_to"] == "Local"
    assert delegated["memory"]["task_id"] == delegated["local_model_executor"]["task_id"] == receipt["task_id"]


def test_local_capability_invoker_forwards_output_to_online_and_receipt() -> None:
    local_service = _LocalService()
    seen: dict[str, object] = {}

    def _memory(context: dict) -> dict:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence": "bounded_memory_lookup",
            "evidence_refs": [f"memory:{context['task_id']}:lookup"],
            "delegated_to": "Local",
            "output": {"hits": ["bounded-hit"]},
        }

    def _online_with_context(context: dict) -> dict:
        seen["capability_results"] = context["capability_results"]
        return _online(context)

    request = UnifiedRuntimeRequest(
        **{
            **_request(local_enabled=True).__dict__,
            "route": {
                "recommended_flow": "hybrid",
                "local_enabled": True,
                "online_capabilities": ("memory",),
            },
        }
    )
    receipt = UnifiedRuntime(planner=_Planner(), local_service=local_service).run(
        request,
        capability_invokers={"memory": _memory},
        online_invoker=_online_with_context,
        verifier=_verifier,
        learning=_learning,
    )

    memory_stage = receipt["capability_results"]["memory"]
    assert memory_stage["status"] == "SUCCEEDED"
    assert memory_stage["task_identity_shared"] is True
    assert seen["capability_results"]["memory"]["response"]["output"] == {"hits": ["bounded-hit"]}
    memory_receipt = next(item for item in receipt["capabilities"] if item["name"] == "memory")
    assert memory_receipt["delegated_to"] == "Local"
    assert memory_receipt["stage"] == "capability:memory"
    assert receipt["receipt_complete"] is True


def test_local_memory_edge_binds_adapter_result_to_one_task_receipt(tmp_path: Path) -> None:
    class _Adapter:
        last_metadata = {"status": "ok", "retrieval_sources": ["fixture"]}

        def retrieve(self, *, query_text: str, limit: int):
            assert query_text == "trace one runtime task"
            assert limit == 2
            return [
                SimpleNamespace(
                    finding_id="lesson-1",
                    summary="bounded lesson",
                    relevance_score=1.0,
                    provenance="receipt:lesson-1",
                    source="fixture",
                    pattern_type="success",
                    task_id="prior-task",
                )
            ]

    invoker = build_local_memory_capability_invoker(tmp_path, adapter=_Adapter(), limit=2)
    result = invoker({"task_id": "unified-test-001", "task_statement": "trace one runtime task"})

    assert result["task_id"] == "unified-test-001"
    assert result["invoked"] is True
    assert result["gate_passed"] is True
    assert result["outcome_contributed"] is True
    assert result["response"]["lessons"][0]["provenance"] == "receipt:lesson-1"
    assert "memory:unified-test-001:hit" in result["evidence_refs"]


def test_local_search_ranking_edge_returns_ordered_provenance(tmp_path: Path) -> None:
    class _Adapter:
        last_metadata = {"status": "ok", "rerank_mode": True}

        def retrieve_reranked(self, *, query_text, anchor_symbol, anchor_file, limit, task_id):
            assert query_text == "semantic retrieval task"
            assert anchor_symbol == "UnifiedRuntime.run"
            assert anchor_file == "nexus/services/unified_runtime.py"
            assert limit == 2
            assert task_id == "unified-search-001"
            return [
                SimpleNamespace(
                    finding_id="rank-1",
                    summary="top ranked result",
                    relevance_score=5.0,
                    provenance="receipt:rank-1",
                    source="fixture",
                    pattern_type="success",
                    task_id="prior-task",
                ),
            ]

    invoker = build_local_search_ranking_capability_invoker(tmp_path, adapter=_Adapter(), limit=2)
    result = invoker(
        {
            "task_id": "unified-search-001",
            "task_statement": "semantic retrieval task",
            "route": {
                "anchor_symbol": "UnifiedRuntime.run",
                "anchor_file": "nexus/services/unified_runtime.py",
            },
        }
    )

    assert result["task_id"] == "unified-search-001"
    assert result["gate_passed"] is True
    assert result["response"]["selected_ids"] == ["rank-1"]
    assert result["response"]["results"][0]["provenance"] == "receipt:rank-1"
    assert "search:unified-search-001:ranked" in result["evidence_refs"]


def test_local_ast_edge_is_bounded_and_root_scoped(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("class Sample:\n    def run(self):\n        return 1\n", encoding="utf-8")
    invoker = build_local_ast_capability_invoker(tmp_path)

    result = invoker(
        {
            "task_id": "unified-ast-001",
            "route": {"target_file": "sample.py"},
        }
    )

    assert result["task_id"] == "unified-ast-001"
    assert result["invoked"] is True
    assert result["gate_passed"] is True
    assert result["response"]["node_count"] >= 1
    assert "ast:unified-ast-001:extracted" in result["evidence_refs"]

    outside = invoker(
        {
            "task_id": "unified-ast-002",
            "route": {"target_file": "../outside.py"},
        }
    )
    assert outside["gate_passed"] is False
    assert outside["error"] == "ast_target_required"


def test_prompt_compression_edge_measures_reduction_and_preserves_json() -> None:
    invoker = build_prompt_compression_capability_invoker(max_chars=512)
    result = invoker(
        {
            "task_id": "unified-compression-001",
            "online_prompt": "prompt " * 400,
            "online_payload": "payload " * 400,
            "capability_results": {
                "memory": {
                    "status": "SUCCEEDED",
                    "evidence_refs": ["memory:unified-compression-001:hit"],
                    "response": {"large": "x" * 1000},
                }
            },
        }
    )

    response = result["response"]
    assert result["task_id"] == "unified-compression-001"
    assert result["gate_passed"] is True
    assert response["truncated"] is True
    assert response["compressed_context_chars"] <= 512
    assert response["compression_ratio"] > 0
    assert json.loads(response["compressed_context"])["truncated"] is True
    assert "compression:unified-compression-001:measured" in result["evidence_refs"]


def test_capability_edges_share_incremental_task_context() -> None:
    class _ChainPlanner:
        def plan(self, **_: object) -> CapabilityPlan:
            return CapabilityPlan(
                schema_version="nexus_capability_plan_v1",
                planner_mode="dry_run",
                selected_capabilities=["memory", "prompt_compression"],
                required_capabilities=["memory", "prompt_compression"],
                optional_capabilities=[],
                conditional_capabilities=[],
                pending_capabilities=[],
                forbidden_capabilities=[],
                constraints=["claim_fail_closed"],
                decision_trace=[],
                replan_trace=[],
                score=1.0,
                signal_snapshot={"route_truth_source": "CapabilityPlanner"},
            )

    seen: dict[str, object] = {}

    def _memory(context: dict) -> dict:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence": "memory-chain",
            "evidence_refs": [f"memory:{context['task_id']}:chain"],
            "response": {"hits": ["chain-hit"]},
        }

    def _compression(context: dict) -> dict:
        seen["memory_status"] = context["capability_results"]["memory"]["status"]
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence": "compression-chain",
            "evidence_refs": [f"compression:{context['task_id']}:chain"],
            "response": {
                "original_context_chars": 100,
                "compressed_context_chars": 20,
                "compression_ratio": 0.8,
                "compressed_context": "COMPACT_CONTEXT",
            },
        }

    def _online_with_context(context: dict) -> dict:
        seen["online_prompt"] = context["online_prompt"]
        seen["compressed"] = context["capability_context_compressed"]
        return _online(context)

    receipt = UnifiedRuntime(planner=_ChainPlanner()).run(
        _request(),
        capability_invokers={"memory": _memory, "prompt_compression": _compression},
        online_invoker=_online_with_context,
        verifier=_verifier,
        learning=_learning,
    )

    assert seen["memory_status"] == "SUCCEEDED"
    assert seen["online_prompt"] == "COMPACT_CONTEXT"
    assert seen["compressed"] is True
    assert receipt["capability_results"]["prompt_compression"]["status"] == "SUCCEEDED"
    assert receipt["context_trace"]["task_id"] == receipt["task_id"]
    assert receipt["context_trace"]["capability_context_compressed"] is True
    assert receipt["context_trace"]["selected_capabilities"] == ["memory", "prompt_compression"]
    assert receipt["receipt_complete"] is True


def test_capability_invoker_rejects_cross_task_result() -> None:
    def _bad_memory(_context: dict) -> dict:
        return {
            "task_id": "other-task",
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["memory:other-task:lookup"],
        }

    receipt = UnifiedRuntime(planner=_Planner(), local_service=_LocalService()).run(
        _request(local_enabled=True),
        capability_invokers={"memory": _bad_memory},
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["capability_results"]["memory"]["status"] == "FAILED"
    assert receipt["capability_results"]["memory"]["reason"] == "capability_task_id_mismatch"
    assert receipt["receipt_complete"] is False
    finalized = UnifiedRuntime().finalize_receipt(
        receipt,
        verifier={"task_id": receipt["task_id"], "status": "pass", "evidence_refs": ["verifier:final"]},
        learning={"task_id": receipt["task_id"], "status": "pass", "evidence_refs": ["learning:final"]},
    )
    assert finalized["receipt_complete"] is False


def test_r4_provider_generate_not_executor_invoked_for_candidate() -> None:
    """R4.0/R4.2: candidate + Provider.generate must remain SELECTED_NOT_EXECUTED."""

    class _Misattributed:
        def handle(self, request):
            return {
                "task_id": request["task_id"] if isinstance(request, dict) else request.task_id,
                "action": "candidate",
                "local_model_invoked": True,
                "output_delivered": True,
                "executor_invoked": True,
                "physical_callable": "LocalModelProvider.generate",
                "evidence_refs": ["local:mis"],
                "receipt_path": "/tmp/mis.json",
                "verifier_summary": {"verifier_status": "not_run"},
            }

    request = UnifiedRuntimeRequest(
        **{
            **_request(local_enabled=True).__dict__,
            "local_request": {"task_id": "unified-test-001", "action": "candidate"},
        }
    )
    receipt = UnifiedRuntime(planner=_Planner(), local_service=_Misattributed()).run(
        request,
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )
    local_cap = next(c for c in receipt["capabilities"] if c["name"] == "local_model_executor")
    assert local_cap["status"] == "SELECTED_NOT_EXECUTED"
    assert local_cap["invoked"] is False
    assert local_cap["physical_callable"] == "LocalModelProvider.generate"


def test_real_planner_selects_local_capability_from_unified_route(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", raising=False)
    runtime = UnifiedRuntime(planner=CapabilityPlanner(), local_service=_LocalService())
    receipt = runtime.run(
        _request(local_enabled=True),
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert "local_model_executor" in receipt["planner"]["selected_capabilities"]
    assert receipt["local"]["status"] == "SUCCEEDED"
    assert receipt["claim_boundary"]["local_online_continuation"] is True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    decision_id = receipt["planner_decision_id"]
    assert decision_id
    assert receipt["planner"]["planner_decision_id"] == decision_id
    assert receipt["context_trace"]["planner_decision_id"] == decision_id
    local_capability = next(item for item in receipt["capabilities"] if item["name"] == "local_model_executor")
    assert local_capability["delegated_to"] == "Local"
    assert local_capability["status"] == "INVOKED"
    assert local_capability["task_id"] == receipt["task_id"]
    assert local_capability["planner_decision_id"] == decision_id


def test_gateway_unified_hybrid_uses_real_local_assist_and_shared_planner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    online_calls: list[tuple[tuple, dict]] = []

    def _online_call(*args, **kwargs):
        online_calls.append((args, kwargs))
        return {"status": "APPROVED", "patch": "candidate"}, "online-raw"

    monkeypatch.setattr(gateway, "ask_structured", _online_call)
    local_service = LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _request: "local diagnosis: inspect candidate")
    )
    task_id = "hybrid-runtime-test-001"
    local_request = LocalAssistRequest(
        schema=REQUEST_SCHEMA,
        task_id=task_id,
        parent_task_id=task_id,
        workspace_root=str(tmp_path),
        workspace_revision="revision-001",
        task_statement="inspect and improve candidate",
        action="advisor",
        allowed_files=("candidate.py",),
        target_file="candidate.py",
        target_symbol="",
        evidence_refs=("hybrid:test:request",),
    )
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="revision-001",
        task_statement="inspect and improve candidate",
        task_type="repair",
        route={"recommended_flow": "hybrid", "provider": "gemini"},
        online_prompt="Return candidate",
        online_payload="Use bounded local diagnosis",
        local_enabled=True,
        local_request=local_request,
        evidence_refs=("hybrid:test:request",),
    )

    receipt = gateway.ask_unified(
        request,
        local_service=local_service,
        capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS,
        verifier=_verifier,
        learning=_learning,
    )

    assert "local_model_executor" in receipt["planner"]["selected_capabilities"]
    assert receipt["local"]["status"] == "SUCCEEDED"
    assert receipt["local"]["response"]["provider"] == "injected"
    assert receipt["local"]["response"]["physical_callable"] == "LocalModelProvider.generate"
    assert receipt["local"]["response"]["executor_invoked"] is False
    local_capability = next(item for item in receipt["capabilities"] if item["name"] == "local_model_executor")
    # Advisor path must not be attributed as local_model_executor INVOKED.
    # FCM: explicit SKIPPED with same reason (coverage row, not silent omit).
    assert local_capability["status"] in {"SELECTED_NOT_EXECUTED", "SKIPPED"}
    assert local_capability["reason"] == "selected_executor_not_invoked_advisor_path"
    assert local_capability["invoked"] is False
    assert local_capability["planner_decision_id"] == receipt["planner_decision_id"]
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert "local diagnosis: inspect candidate" in online_calls[0][0][0]
    assert "gateway:hybrid-runtime-test-001:local_context_forwarded" in receipt["evidence_refs"]
    assert receipt["claim_boundary"]["local_online_continuation"] is True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt["receipt_complete"] is True


def test_gateway_unified_entry_uses_same_receipt_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_args, **_kwargs: ({"summary": "online"}, "online-response"),
    )
    receipt = gateway.ask_unified(
        _request(),
        capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS,
        verifier=_verifier,
        learning=_learning,
        receipt_path=tmp_path / "unified.json",
    )

    assert receipt["schema"] == "nexus.unified_runtime.receipt.v1"
    assert receipt["online"]["invoked"] is True
    assert receipt["receipt_complete"] is True
    assert (tmp_path / "unified.json").exists()


def test_gateway_unified_entry_forwards_provider_context(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    calls: list[dict] = []

    def _fake_ask(*_args, **kwargs):
        calls.append(kwargs)
        return {"status": "APPROVED", "patch": "candidate"}, "raw-candidate"

    monkeypatch.setattr(gateway, "ask_structured", _fake_ask)
    request = UnifiedRuntimeRequest(
        **{
            **_request().__dict__,
            "online_model_name": "provider-model-1",
            "online_output_schema": {"status": "APPROVED | FAIL"},
            "online_phase": "R",
        }
    )
    gateway.ask_unified(request, verifier=_verifier, learning=_learning)

    assert calls[0]["model_name"] == "provider-model-1"
    assert calls[0]["output_schema"] == {"status": "APPROVED | FAIL"}


def test_provider_neutral_subprocess_invoker_is_task_scoped() -> None:
    invoker = build_subprocess_online_invoker(
        OnlineCliSpec(
            provider="deterministic-cli",
            command=(sys.executable, "-c", "import sys; print(sys.stdin.read())"),
        )
    )
    result = invoker(
        {
            "task_id": "cli-task-001",
            "task_statement": "answer this task",
            "online_payload": "bounded payload",
        }
    )

    assert result["invoked"] is True
    assert result["task_id"] == "cli-task-001"
    assert result["output_delivered"] is True
    assert result["gate_passed"] is True
    assert result["evidence_refs"] == ["online:deterministic-cli:cli-task-001:subprocess"]


def test_gateway_accepts_provider_neutral_online_invoker(tmp_path: Path) -> None:
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    invoker = build_subprocess_online_invoker(
        OnlineCliSpec(
            provider="grok",
            command=(sys.executable, "-c", "print('grok-provider-output')"),
        )
    )
    request = UnifiedRuntimeRequest(
        **{
            **_request().__dict__,
            "route": {
                "recommended_flow": "direct",
                "provider": "grok",
                "online_policy": "auto",
                "injected_transport": True,
                "workspace_root": str(tmp_path),
            },
        }
    )

    receipt = gateway.ask_unified(
        request,
        online_invoker=invoker,
        capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS,
        verifier=_verifier,
        learning=_learning,
    )
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert receipt["receipt_complete"] is True
    assert "online:grok:unified-test-001:subprocess" in receipt["evidence_refs"]


def test_gateway_selects_explicit_registered_provider_at_edge(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.gateway import BattlesuitGateway

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    gateway = BattlesuitGateway(project_root=tmp_path)
    request = UnifiedRuntimeRequest(
        **{
            **_request().__dict__,
            "route": {
                "recommended_flow": "direct",
                "provider": "grok",
                "online_command": (sys.executable, "-c", "print('edge-provider-output')"),
            },
        }
    )
    receipt = gateway.ask_unified(request, capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS, verifier=_verifier, learning=_learning)

    assert receipt["planner"]["invoked"] is True
    assert receipt["online"]["response"]["provider"] == "grok"
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert receipt["receipt_complete"] is True


def test_gateway_uses_registered_edge_when_gateway_is_configured_for_codex(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.gateway import BattlesuitGateway

    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "codex")
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    gateway = BattlesuitGateway(project_root=tmp_path)
    request = UnifiedRuntimeRequest(
        **{
            **_request().__dict__,
            "route": {
                "recommended_flow": "direct",
                "provider": "codex",
                "online_command": (sys.executable, "-c", "print('same-provider-edge-output')"),
            },
        }
    )

    receipt = gateway.ask_unified(request, capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS, verifier=_verifier, learning=_learning)

    assert receipt["online"]["response"]["provider"] == "codex"
    assert receipt["online"]["response"]["response"].strip() == "same-provider-edge-output"
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert receipt["receipt_complete"] is True


def test_all_registered_providers_enter_one_unified_receipt_contract(tmp_path: Path) -> None:
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    observed: dict[str, dict] = {}
    for provider in ONLINE_CLI_SPEC_REGISTRY:
        if provider == "agy":
            # build_subprocess_online_invoker adds --dangerously-skip-permissions
            # for agy, which breaks with a bare sys.executable.  Use a direct
            # stub instead.
            invoker = lambda ctx: {
                "invoked": True,
                "output_delivered": True,
                "gate_passed": True,
                "provider_call_count": 1,
                "evidence_refs": ["online:agy:test:subprocess"],
            }
        else:
            invoker = build_subprocess_online_invoker(
                OnlineCliSpec(
                    provider=provider,
                    command=(sys.executable, "-c", f"print('{provider}-bounded-output')"),
                )
            )
        request = UnifiedRuntimeRequest(
            **{
                **_request().__dict__,
                "task_id": f"unified-provider-{provider}",
                "route": {
                    "recommended_flow": "direct",
                    "provider": provider,
                    "online_policy": "auto",
                    "injected_transport": True,
                    "workspace_root": str(tmp_path),
                },
            }
        )
        receipt = gateway.ask_unified(
            request,
            online_invoker=invoker,
            capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS,
            verifier=_verifier,
            learning=_learning,
        )
        observed[provider] = receipt

    assert set(observed) == set(ONLINE_CLI_SPEC_REGISTRY)
    assert all(receipt["schema"] == "nexus.unified_runtime.receipt.v1" for receipt in observed.values())
    assert all(receipt["planner"]["name"] == "planner" for receipt in observed.values())
    assert all(receipt["receipt_complete"] is True for receipt in observed.values())
    assert all(
        receipt["context_trace"]["task_id"] == receipt["task_id"]
        for receipt in observed.values()
    )


def test_negative_control_deny_missing_provider_binary(monkeypatch) -> None:
    """deny + missing provider binary: zero forbidden calls."""
    import shutil
    from nexus.services.unified_runtime import (
        build_subprocess_online_invoker,
        resolve_registered_online_cli_spec,
    )

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)

    counts: dict[str, int] = {"which": 0, "resolve": 0, "build_invoker": 0}

    def _which_sentinel(*_a, **_kw):
        counts["which"] += 1
        raise AssertionError("shutil.which called during deny path")

    def _resolve_sentinel(*_a, **_kw):
        counts["resolve"] += 1
        raise AssertionError("resolve_registered_online_cli_spec called during deny path")

    def _build_sentinel(*_a, **_kw):
        counts["build_invoker"] += 1
        raise AssertionError("build_subprocess_online_invoker called during deny path")

    monkeypatch.setattr(shutil, "which", _which_sentinel)
    monkeypatch.setattr(
        "nexus.services.unified_runtime.resolve_registered_online_cli_spec",
        _resolve_sentinel,
    )
    monkeypatch.setattr(
        "nexus.services.unified_runtime.build_subprocess_online_invoker",
        _build_sentinel,
    )

    invoker = build_registered_online_invoker("gemini")
    result = invoker({"task_id": "nc-1", "task_statement": "do not run"})

    assert counts == {"which": 0, "resolve": 0, "build_invoker": 0}
    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert result["error"] == "online_execution_not_authorized"
    assert result["provider"] == "gemini"


def test_negative_control_deny_invalid_provider(monkeypatch) -> None:
    """deny + invalid/unregistered provider: zero forbidden calls."""
    import shutil
    from nexus.services.unified_runtime import (
        build_subprocess_online_invoker,
        resolve_registered_online_cli_spec,
    )

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)

    counts: dict[str, int] = {"which": 0, "resolve": 0, "build_invoker": 0}

    def _which_sentinel(*_a, **_kw):
        counts["which"] += 1
        raise AssertionError("shutil.which called during deny path")

    def _resolve_sentinel(*_a, **_kw):
        counts["resolve"] += 1
        raise AssertionError("resolve_registered_online_cli_spec called during deny path")

    def _build_sentinel(*_a, **_kw):
        counts["build_invoker"] += 1
        raise AssertionError("build_subprocess_online_invoker called during deny path")

    monkeypatch.setattr(shutil, "which", _which_sentinel)
    monkeypatch.setattr(
        "nexus.services.unified_runtime.resolve_registered_online_cli_spec",
        _resolve_sentinel,
    )
    monkeypatch.setattr(
        "nexus.services.unified_runtime.build_subprocess_online_invoker",
        _build_sentinel,
    )

    invoker = build_registered_online_invoker("nonexistent_provider")
    result = invoker({"task_id": "nc-2", "task_statement": "do not run"})

    assert counts == {"which": 0, "resolve": 0, "build_invoker": 0}
    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert result["error"] == "online_execution_not_authorized"
    assert result["provider"] == "nonexistent_provider"


def test_negative_control_authorized_missing_provider_binary(monkeypatch) -> None:
    """authorized + missing provider binary: subprocess adapter not executed."""
    import shutil
    from nexus.services.unified_runtime import build_subprocess_online_invoker

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    build_calls: list[object] = []

    def _build_sentinel(*a, **kw):
        build_calls.append((a, kw))
        # Fall through to real function so the exception is properly caught.
        return build_subprocess_online_invoker(*a, **kw)

    monkeypatch.setattr(
        "nexus.services.unified_runtime.build_subprocess_online_invoker",
        _build_sentinel,
    )

    invoker = build_registered_online_invoker("gemini")
    result = invoker({
        "task_id": "nc-3",
        "task_statement": "try to run",
        "online_execution_authorized": True,
    })

    # shutil.which returning None → resolve fails before build_subprocess_online_invoker.
    assert len(build_calls) == 0, "build_subprocess_online_invoker should not be called"
    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert result["error"] == "provider_binary_not_found"


def test_negative_control_required_memory_missing_context() -> None:
    """Required memory capability with missing context: receipt_complete=False."""
    planner = _Planner()
    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        _request(),
        online_invoker=_online,
        verifier=_verifier,
    )

    assert receipt["receipt_complete"] is False
    mem_result = receipt.get("capability_results", {}).get("memory", {})
    assert mem_result.get("invoked") is True
    assert mem_result.get("gate_passed") is False
    inner = mem_result.get("response", {})
    if isinstance(inner, dict):
        outcome = inner.get("response", {}).get("outcome", {}) if isinstance(inner.get("response"), dict) else {}
        error = str(outcome.get("error") or "")
        assert "PROJECT_MEMORY_CONTEXT_REQUIRED" in error, f"unexpected error: {error}"


def test_negative_control_required_memory_valid_project_context(tmp_path: Path) -> None:
    """Required memory via build_local_memory_capability_invoker with production adapter boundary."""
    from types import SimpleNamespace

    planner = _Planner()
    runtime = UnifiedRuntime(planner=planner)

    class _Adapter:
        last_metadata = {"status": "ok", "retrieval_sources": ["test_fixture"]}

        def retrieve(self, *, query_text: str, limit: int):
            return [
                SimpleNamespace(
                    finding_id="nc-memory-1",
                    summary="bounded memory result for negative control",
                    relevance_score=0.95,
                    provenance="receipt:nc-memory-1",
                    source="test_fixture",
                    pattern_type="success",
                    task_id="nc-task",
                )
            ]

    memory_invoker = build_local_memory_capability_invoker(
        tmp_path,
        adapter=_Adapter(),
        limit=3,
    )

    invokers = dict(_DETERMINISTIC_CAPABILITY_INVOKERS)
    invokers["memory"] = memory_invoker

    receipt = runtime.run(
        _request(),
        capability_invokers=invokers,
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    mem_result = receipt.get("capability_results", {}).get("memory", {})
    assert mem_result.get("invoked") is True, f"memory not invoked: {mem_result}"
    assert mem_result.get("gate_passed") is True, f"memory not passed: {mem_result}"

    ev_refs = mem_result.get("evidence_refs", [])
    assert any("memory" in r for r in ev_refs), f"missing memory evidence_refs: {ev_refs}"
    assert any("retrieval" in r for r in ev_refs), f"missing retrieval evidence_refs: {ev_refs}"

    assert receipt["receipt_complete"] is True, (
        f"receipt not complete: blockers={receipt.get('capability_closure_blockers')}"
    )


def test_negative_control_optional_non_selected_memory(monkeypatch, tmp_path: Path) -> None:
    """Non-selected memory with real CapabilityPlanner: receipt_complete=True."""
    from nexus.services.gateway import BattlesuitGateway

    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_args, **_kwargs: ({"summary": "online"}, "online-response"),
    )

    # Real CapabilityPlanner selects harness_preflight_sensor, repair_loop, etc.
    # Provide deterministic fixtures for all selected caps.
    receipt = gateway.ask_unified(
        _request(),
        capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS,
        verifier=_verifier,
        learning=_learning,
    )

    caps = receipt.get("capability_results", {})
    assert "memory" not in caps, "memory should not be selected by real planner"
    assert receipt["receipt_complete"] is True, (
        f"receipt not complete: blockers={receipt.get('capability_closure_blockers')}"
    )


def test_explicit_committee_route_enters_unified_receipt_fail_closed(tmp_path: Path, monkeypatch) -> None:
    class _CommitteePlanner:
        def plan(self, **_: object) -> CapabilityPlan:
            return CapabilityPlan(
                schema_version="nexus_capability_plan_v1",
                planner_mode="dry_run",
                selected_capabilities=["committee"],
                required_capabilities=["committee"],
                optional_capabilities=[],
                conditional_capabilities=[],
                pending_capabilities=[],
                forbidden_capabilities=[],
                constraints=["claim_fail_closed"],
                decision_trace=[],
                replan_trace=[],
                score=1.0,
                signal_snapshot={"route_truth_source": "CapabilityPlanner"},
            )

    monkeypatch.setenv("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", "1")

    def _committee(context: dict) -> dict:
        from nexus.services.local_heal.committee_routed_tool import (
            CommitteeRoutedToolRequest,
            evaluate_and_execute,
        )

        request = CommitteeRoutedToolRequest(
            task_id=context["task_id"],
            repo_root=str(tmp_path),
            target_file="committee_fixture.py",
            difficulty="hard",
            execution_topology="cloud_with_local_assist",
            p3_route_status="shadow_stage5_escalation_recommended",
            hard_case_escalation_reason="retry_failed",
            source_hash="fixture-source",
            evidence_refs=(f"committee:{context['task_id']}:request",),
            proposer_specs=[
                {"model": "fixture-primary", "role": "primary"},
                {"model": "fixture-secondary", "role": "secondary"},
            ],
            judge_model="fixture-judge",
        )
        committee_result = evaluate_and_execute(
            request,
            candidate_producer=lambda _request: [{
                "candidate_patch": "def committee_fixture():\n    return 42\n",
                "format": "UNIFIED_DIFF",
                "model": "fixture-primary",
                "candidate_id": "committee-fixture-candidate",
            }],
        )
        return {
            "task_id": context["task_id"],
            "invoked": committee_result.invoked,
            "gate_passed": committee_result.solved_by_committee,
            "outcome_contributed": committee_result.solved_by_committee,
            "evidence": "CommitteeRoutedTool.evaluate_and_execute",
            "evidence_refs": [f"committee:{context['task_id']}:bounded"],
            "response": committee_result.receipt_fragment,
        }

    receipt = UnifiedRuntime(planner=_CommitteePlanner()).run(
        _request(),
        capability_invokers={"committee": _committee},
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["capability_results"]["committee"]["status"] == "SUCCEEDED"
    assert receipt["capability_results"]["committee"]["delegated_to"] == "Local"
    assert receipt["capability_results"]["committee"]["response"]["response"]["p4_winner_found"] is True
    assert receipt["capability_results"]["committee"]["response"]["response"]["p4_committee_claim_gate_passed"] is True
    assert receipt["receipt_complete"] is True


def test_capability_planner_exposes_committee_only_when_route_selects_it() -> None:
    default_plan = CapabilityPlanner().plan(
        task_desc="bounded repair task",
        task_type="repair",
        route={"recommended_flow": "direct"},
    )
    routed_plan = CapabilityPlanner().plan(
        task_desc="bounded repair task",
        task_type="repair",
        route={
            "recommended_flow": "direct",
            "route_decision": {"selected_capabilities": ["committee"]},
        },
    )
    compression_off = CapabilityPlanner().plan(
        task_desc="bounded repair task",
        task_type="repair",
        route={"recommended_flow": "direct"},
    )
    compression_on = CapabilityPlanner().plan(
        task_desc="bounded repair task",
        task_type="repair",
        route={"recommended_flow": "direct", "prompt_compression": True},
    )

    assert "committee" not in default_plan.selected_capabilities
    assert "committee" in routed_plan.selected_capabilities
    assert "prompt_compression" not in compression_off.selected_capabilities
    assert "prompt_compression" in compression_on.selected_capabilities


def test_gateway_does_not_fallback_to_wrong_provider_for_unknown_route(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.gateway import BattlesuitGateway

    # Authorize Online so the failure is provider resolution, not product deny.
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    gateway = BattlesuitGateway(project_root=tmp_path)
    request = UnifiedRuntimeRequest(
        **{
            **_request().__dict__,
            "route": {
                "recommended_flow": "direct",
                "provider": "unknown-provider",
                "online_policy": "auto",
                "workspace_root": str(tmp_path),
            },
        }
    )
    receipt = gateway.ask_unified(request, verifier=_verifier, learning=_learning)

    assert receipt["online"]["status"] == "FAILED"
    # Fail closed: either adapter resolution or provider-not-approved decision.
    err = str(receipt["online"]["response"].get("error") or "")
    assert err in {"provider_adapter_resolution_failed", "online_execution_not_authorized"}
    assert receipt["receipt_complete"] is False


def test_build_online_route_does_not_promote_local_ollama_to_online_provider() -> None:
    route = build_online_route(gateway_provider="ollama", recommended_flow="direct")
    assert "provider" not in route
    assert route["execution_role"] == "online"
    assert route["local_provider_detected"] == "ollama"
    assert route["selection_source"] == "compatibility_default"
    assert route["gateway_default_provider"] == "ollama"


def test_build_online_route_keeps_registered_gateway_default() -> None:
    route = build_online_route(gateway_provider="gemini", recommended_flow="direct")
    assert route["provider"] == "gemini"
    assert route["selection_source"] == "environment_default"


def test_resolve_online_transport_binding_precedence() -> None:
    injected = resolve_online_transport_binding(
        structured_transport_injected=True,
        route_provider="ollama",
        gateway_provider="ollama",
    )
    assert injected.transport == "structured_callable"
    assert injected.selection_source == "injected_transport"
    assert injected.provider == "injected"
    assert injected.provider != "ollama"
    assert injected.use_gateway_structured is True

    local_default = resolve_online_transport_binding(
        route_provider="ollama",
        gateway_provider="ollama",
    )
    assert local_default.transport == "gateway_compatibility"
    assert local_default.use_gateway_structured is True
    assert local_default.resolution_error == ""

    unknown = resolve_online_transport_binding(route_provider="unknown-provider")
    assert unknown.transport == "unresolved"
    assert unknown.resolution_error == "provider_not_registered"

    registered = resolve_online_transport_binding(
        route_provider="grok",
        gateway_provider="ollama",
    )
    assert registered.transport == "registered_cli"
    assert registered.use_registered_cli is True


def test_gateway_injected_structured_transport_outranks_local_ollama(
    tmp_path: Path, monkeypatch
) -> None:
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(gateway, "oauth_provider", "ollama")
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_args, **_kwargs: ({"status": "APPROVED", "patch": "ok\n"}, "raw-ok"),
    )
    request = UnifiedRuntimeRequest(
        **{
            **_request().__dict__,
            # Even if a caller still copies oauth_provider into route.provider,
            # injected structured transport must win.
            "route": {"recommended_flow": "direct", "provider": "ollama"},
        }
    )
    receipt = gateway.ask_unified(request, verifier=_verifier, learning=_learning)
    domain, raw, payload = extract_online_stage_payload(receipt["online"])

    assert receipt["online"]["status"] == "SUCCEEDED"
    assert domain == {"status": "APPROVED", "patch": "ok\n"}
    assert raw == "raw-ok"
    assert payload["invoked"] is True
    assert payload["output_delivered"] is True
    # Binding identity, not oauth_provider auto-detect.
    assert payload["provider"] == "injected"
    assert payload["transport"] == "structured_callable"
    assert payload["selection_source"] == "injected_transport"
    assert payload["provider"] != "ollama"
    for required in (
        "provider",
        "task_id",
        "invoked",
        "output_delivered",
        "gate_passed",
        "provider_call_count",
        "response",
        "raw_response",
        "usage",
        "error",
        "evidence_refs",
    ):
        assert required in payload
    assert payload["error"] == ""
    assert isinstance(payload["usage"], dict)


def test_extract_online_stage_payload_is_canonical() -> None:
    domain, raw, payload = extract_online_stage_payload(
        {
            "status": "SUCCEEDED",
            "response": {
                "provider": "fixture",
                "task_id": "t1",
                "invoked": True,
                "output_delivered": True,
                "gate_passed": True,
                "provider_call_count": 1,
                "response": {"patch": "x"},
                "raw_response": "raw-x",
                "error": "",
                "evidence_refs": ["online:fixture:t1"],
            },
        }
    )
    assert domain == {"patch": "x"}
    assert raw == "raw-x"
    assert payload["provider"] == "fixture"
    assert payload["provider_call_count"] == 1


def test_provider_neutral_cli_registry_is_explicit_and_non_invoking() -> None:
    assert set(ONLINE_CLI_SPEC_REGISTRY) == {
        "gemini", "agy", "grok", "codex", "openai", "opencode", "cline", "mimo", "ollama",
    }
    assert all(
        item["transport"] == "subprocess" and item["binary_env"] and item["binary_name"]
        for item in ONLINE_CLI_SPEC_REGISTRY.values()
    )


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    (
        ("cline", "glm-5.2", ["cline", "--json", "--yolo", "--model", "glm-5.2", "bounded"]),
        ("mimo", "xiaomi/mimo-v2.5", ["mimo", "run", "--model", "xiaomi/mimo-v2.5", "bounded"]),
        ("ollama", "qwen3:8b", ["ollama", "run", "qwen3:8b", "bounded"]),
    ),
)
def test_registered_local_and_cline_models_bind_exactly(provider, model, expected) -> None:
    calls = []

    class _Completed:
        returncode = 0
        stdout = "model-output"
        stderr = ""

    def _runner(command, **kwargs):
        calls.append(list(command))
        return _Completed()

    invoker = build_registered_online_invoker(provider, command=(provider,), model_name=model, runner=_runner)
    result = invoker({"task_id": f"{provider}-model", "task_statement": "bounded"})

    assert result["provider"] == provider
    assert calls == [expected]


def test_opencode_registered_invoker_constructs_correct_argv() -> None:
    calls: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = "opencode-output"
        stderr = ""

    def _runner(command, **kwargs):
        calls.append(list(command))
        return _Completed()

    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
        runner=_runner,
    )
    result = invoker(
        {
            "task_id": "opencode-test",
            "task_statement": "test prompt",
            "online_payload": "",
        }
    )
    assert result["provider"] == "opencode"
    assert result["task_id"] == "opencode-test"
    assert result["invoked"] is True
    assert result["gate_passed"] is True
    assert len(calls) == 1
    argv = calls[0]
    assert argv[0] == "/usr/local/bin/opencode"
    assert "run" in argv
    assert "--model" in argv
    assert "opencode/deepseek-v4-flash-free" in argv


def test_opencode_invoker_fails_closed_on_timeout() -> None:
    calls: list[list[str]] = []

    def _runner(command, **kwargs):
        calls.append(list(command))
        import subprocess
        raise subprocess.TimeoutExpired(cmd=command, timeout=0.001, output="")

    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
        runner=_runner,
        timeout_sec=0.001,
    )
    result = invoker(
        {
            "task_id": "opencode-timeout",
            "task_statement": "test prompt",
            "online_payload": "",
        }
    )
    assert result["invoked"] is True
    assert result["provider_call_count"] == 1
    assert result["error"] == "provider_timeout"
    assert result["gate_passed"] is False
    assert len(calls) == 1


def test_opencode_invoker_fails_closed_on_nonzero_exit() -> None:
    calls: list[list[str]] = []

    class _Completed:
        returncode = 1
        stdout = ""
        stderr = "error"

    def _runner(command, **kwargs):
        calls.append(list(command))
        return _Completed()

    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
        runner=_runner,
    )
    result = invoker(
        {
            "task_id": "opencode-nonzero",
            "task_statement": "test prompt",
            "online_payload": "",
        }
    )
    assert result["invoked"] is True
    assert result["provider_call_count"] == 1
    assert result["error"] == "provider_subprocess_failed"
    assert result["gate_passed"] is False


def test_opencode_invoker_fails_closed_on_empty_stdout() -> None:
    calls: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def _runner(command, **kwargs):
        calls.append(list(command))
        return _Completed()

    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
        runner=_runner,
    )
    result = invoker(
        {
            "task_id": "opencode-empty",
            "task_statement": "test prompt",
            "online_payload": "",
        }
    )
    assert result["invoked"] is True
    assert result["provider_call_count"] == 1
    assert result["error"] == "provider_subprocess_failed"
    assert result["gate_passed"] is False


def test_opencode_invoker_fails_closed_on_oserror() -> None:
    calls: list[list[str]] = []

    def _runner(command, **kwargs):
        calls.append(list(command))
        raise OSError("binary not found")

    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
        runner=_runner,
    )
    result = invoker(
        {
            "task_id": "opencode-oserror",
            "task_statement": "test prompt",
            "online_payload": "",
        }
    )
    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert result["error"] == "provider_not_invoked"
    assert result["gate_passed"] is False


def test_opencode_deny_causes_zero_subprocess_calls(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
    )
    result = invoker(
        {
            "task_id": "opencode-deny",
            "task_statement": "test prompt",
            "online_payload": "",
        }
    )
    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert result["error"] == "online_execution_not_authorized"


def test_opencode_request_stdout_stderr_physical_output() -> None:
    captured: dict = {}

    class _Completed:
        returncode = 0
        stdout = '{"response": "test"}'
        stderr = ""

    def _runner(command, **kwargs):
        captured["argv"] = list(command)
        return _Completed()

    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
        runner=_runner,
    )
    result = invoker(
        {
            "task_id": "opencode-physical-output",
            "task_statement": "test prompt",
            "online_payload": '{"task": "test"}',
        }
    )
    assert result["invoked"] is True
    assert result["gate_passed"] is True
    last_arg = captured["argv"][-1] if captured.get("argv") else ""
    assert "test prompt" in last_arg
    assert result["error"] == ""
    assert result["provider"] == "opencode"
    assert result["task_id"] == "opencode-physical-output"


def test_opencode_no_fallback_or_model_substitution() -> None:
    calls: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = "output"
        stderr = ""

    def _runner(command, **kwargs):
        calls.append(list(command))
        return _Completed()

    invoker = build_registered_online_invoker(
        "opencode",
        command=("/usr/local/bin/opencode",),
        runner=_runner,
    )
    result = invoker(
        {
            "task_id": "opencode-no-fallback",
            "task_statement": "test prompt",
            "online_payload": "",
        }
    )
    assert result["invoked"] is True
    assert result["gate_passed"] is True
    argv = calls[0]
    model_idx = argv.index("--model") + 1 if "--model" in argv else -1
    assert model_idx > 0
    assert argv[model_idx] == "opencode/deepseek-v4-flash-free"


def test_registered_cli_spec_resolver_is_edge_only() -> None:
    spec = resolve_registered_online_cli_spec(
        "grok",
        command=("/opt/grok", "--stdin"),
        timeout_sec=45,
    )
    assert spec.provider == "grok"
    assert spec.command == ("/opt/grok", "--stdin")
    assert spec.timeout_sec == 45


def test_registered_cli_spec_resolver_prefers_provider_command_env() -> None:
    spec = resolve_registered_online_cli_spec(
        "codex",
        environ={
            "NEXUS_CODEX_COMMAND": "/opt/codex-wrapper --stdin --output plain",
            "NEXUS_CODEX_BIN": "/opt/codex-binary",
        },
    )

    assert spec.command == ("/opt/codex-wrapper", "--stdin", "--output", "plain")


def test_registered_online_invoker_fails_closed_without_external_authorization(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    invoker = build_registered_online_invoker(
        "grok",
        command=(sys.executable, "-c", "raise SystemExit('must not execute')"),
    )

    result = invoker({"task_id": "auth-task", "task_statement": "do not run"})

    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert result["error"] == "online_execution_not_authorized"
    assert result["task_id"] == "auth-task"


def test_gateway_default_transport_fails_closed_without_external_authorization(monkeypatch, tmp_path: Path) -> None:
    from nexus.services.gateway import BattlesuitGateway

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    receipt = BattlesuitGateway(project_root=tmp_path).ask_unified(
        _request(),
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["online"]["status"] == "FAILED"
    assert receipt["online"]["response"]["error"] == "online_execution_not_authorized"
    assert receipt["online"]["response"]["task_id"] == receipt["task_id"]
    assert receipt["receipt_complete"] is False


def test_gateway_forwards_capability_invokers_into_canonical_runtime(tmp_path: Path) -> None:
    from nexus.services.gateway import BattlesuitGateway

    request = UnifiedRuntimeRequest(
        task_id="gateway-capability-001",
        workspace_revision="rev-1",
        task_statement="retrieve prior context for this task",
        task_type="repair",
        route={
            "recommended_flow": "direct",
            "route_features": {"memory_hits": 1, "findings_hits": 1},
        },
    )

    receipt = BattlesuitGateway(project_root=tmp_path).ask_unified(
        request,
        capability_invokers={
            "memory": lambda context: {
                "task_id": context["task_id"],
                "invoked": True,
                "gate_passed": True,
                "evidence": "gateway capability fixture",
                "evidence_refs": [f"memory:{context['task_id']}:fixture"],
            }
        },
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["capability_results"]["memory"]["status"] == "SUCCEEDED"
    assert receipt["capability_results"]["memory"]["task_identity_shared"] is True


def test_all_registered_online_providers_share_one_invoker_contract() -> None:
    calls: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = "provider-output"
        stderr = ""

    def _runner(command, **kwargs):
        calls.append(list(command))
        assert kwargs["input"].startswith("answer this task")
        return _Completed()

    for provider in ("gemini", "grok", "codex", "openai"):
        invoker = build_registered_online_invoker(
            provider,
            command=(f"/opt/{provider}", "--stdin"),
            runner=_runner,
        )
        result = invoker(
            {
                "task_id": f"{provider}-task",
                "task_statement": "answer this task",
                "online_payload": "bounded payload",
            }
        )
        assert result["provider"] == provider
        assert result["task_id"] == f"{provider}-task"
        assert result["invoked"] is True
        assert result["gate_passed"] is True

    assert calls == [[f"/opt/{provider}", "--stdin"] for provider in ("gemini", "grok", "codex", "openai")]


def test_registered_invoker_forwards_capability_context_to_online() -> None:
    seen: dict[str, str] = {}

    class _Completed:
        returncode = 0
        stdout = "provider-output"
        stderr = ""

    def _runner(_command, **kwargs):
        seen["input"] = kwargs["input"]
        return _Completed()

    invoker = build_registered_online_invoker(
        "grok",
        command=("/opt/grok", "--stdin"),
        runner=_runner,
    )
    result = invoker(
        {
            "task_id": "capability-forward-task",
            "task_statement": "continue the task",
            "capability_results": {
                "memory": {
                    "status": "SUCCEEDED",
                    "response": {"output": {"hits": ["bounded-hit"]}},
                }
            },
        }
    )

    assert result["gate_passed"] is True
    assert "[CAPABILITY_CONTEXT]" in seen["input"]
    assert "bounded-hit" in seen["input"]
    assert "online:grok:capability-forward-task:capability_context_forwarded" in result["evidence_refs"]

    compressed_result = invoker(
        {
            "task_id": "capability-forward-compressed-task",
            "online_prompt": "continue the compact task",
            "capability_context_compressed": True,
            "capability_results": {
                "memory": {
                    "status": "SUCCEEDED",
                    "task_id": "capability-forward-compressed-task",
                    "evidence_refs": ["memory:capability-forward-compressed-task:hit"],
                    "response": {"output": {"hits": ["must-not-forward-raw"]}},
                }
            },
        }
    )

    assert compressed_result["gate_passed"] is True
    assert "[CAPABILITY_EVIDENCE_SUMMARY]" in seen["input"]
    assert "must-not-forward-raw" not in seen["input"]
    assert "online:grok:capability-forward-compressed-task:compressed_context_applied" in compressed_result["evidence_refs"]


def test_structured_compatibility_transport_is_wrapped_by_runtime_contract() -> None:
    calls: list[dict] = []

    def _ask_structured(**kwargs):
        calls.append(kwargs)
        return {"status": "APPROVED", "patch": "candidate"}, "raw"

    invoker = build_structured_online_invoker(_ask_structured, provider="fixture")
    result = invoker(
        {
            "task_id": "fixture-task",
            "task_statement": "generate candidate",
            "online_payload": "payload",
            "online_output_schema": {"patch": "text"},
        }
    )

    assert result["invoked"] is True
    assert result["task_id"] == "fixture-task"
    assert result["output_delivered"] is True
    assert result["evidence_refs"] == ["online:fixture:fixture-task:structured_transport"]
    assert calls[0]["prompt"] == "generate candidate"


def test_finalize_receipt_closes_same_task_after_observed_outcome(tmp_path: Path) -> None:
    runtime = UnifiedRuntime(planner=_Planner())
    receipt = runtime.run(_request(), capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS, online_invoker=_online, verifier=_verifier)
    assert receipt["receipt_complete"] is False

    finalized = runtime.finalize_receipt(
        receipt,
        verifier={"status": "pass", "evidence": "pytest_pass", "evidence_refs": ["verifier:final"]},
        learning={"status": "pass", "evidence": "learning_written", "evidence_refs": ["learning:final"]},
        outcome={"score": 1.0},
        receipt_path=tmp_path / "finalized.json",
    )

    assert finalized["task_id"] == receipt["task_id"]
    assert finalized["receipt_complete"] is True
    assert finalized["terminal_status"] == "SUCCEEDED"
    assert finalized["claim_boundary"]["value_measured"] is True


def test_finalize_receipt_rejects_cross_task_final_stage_payload() -> None:
    runtime = UnifiedRuntime(planner=_Planner())
    receipt = runtime.run(_request(), capability_invokers=_DETERMINISTIC_CAPABILITY_INVOKERS, online_invoker=_online, verifier=_verifier)
    finalized = runtime.finalize_receipt(
        receipt,
        verifier={
            "task_id": "other-task",
            "status": "pass",
            "evidence": "wrong task verifier",
            "evidence_refs": ["verifier:other-task"],
        },
        learning={
            "task_id": "unified-test-001",
            "status": "pass",
            "evidence": "same task learning",
            "evidence_refs": ["learning:unified-test-001"],
        },
    )

    assert finalized["verifier"]["status"] == "FAILED"
    assert finalized["verifier"]["reason"] == "verifier_task_id_mismatch"
    assert finalized["claim_boundary"]["public_claim_allowed"] is False
    assert finalized["receipt_complete"] is False


def test_gateway_ask_unified_cleans_task_decision_before_later_direct_call(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    original_ask_structured = gateway.ask_structured

    def injected_ask(*_args, **_kwargs):
        return {"status": "APPROVED", "patch": "candidate"}, "raw-candidate"

    monkeypatch.setattr(gateway, "ask_structured", injected_ask)
    request = UnifiedRuntimeRequest(
        task_id="gateway-cleanup-task",
        workspace_revision="rev-cleanup",
        task_statement="run one injected online task",
        task_type="repair",
        route={"recommended_flow": "direct", "workspace_root": str(tmp_path)},
    )

    receipt = gateway.ask_unified(request, verifier=_verifier, learning=_learning)
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert not hasattr(gateway, "_online_execution_decision")

    monkeypatch.setattr(gateway, "ask_structured", original_ask_structured)
    data, raw = gateway.ask_structured("direct legacy call", "{}")
    assert data["error"] == "online_execution_not_authorized"
    assert data["invoked"] is False
    assert data["provider_call_count"] == 0
    assert raw == "online_execution_not_authorized"


# ── P0-T1: execution_depth consumption tests ────────────────────────────────


@dataclass
class _DepthPlanner:
    """Planner fixture that explicitly outputs execution_depth='LIGHT'."""
    calls: int = 0

    def plan(self, **_: object) -> CapabilityPlan:
        self.calls += 1
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=["memory", "local_model_executor"],
            required_capabilities=["memory", "local_model_executor"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=["claim_fail_closed"],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            execution_depth="LIGHT",
            signal_snapshot={
                "route_truth_source": "CapabilityPlanner",
                "execution_depth": "LIGHT",
                "execution_depth_source": "CapabilityPlanner:routing_tier",
            },
        )


@dataclass
class _DepthLocalService:
    """Fake local service that records the planner_snapshot it receives."""
    seen_snapshot: dict = None

    def __post_init__(self):
        if self.seen_snapshot is None:
            self.seen_snapshot = {}

    def handle(self, request):
        if isinstance(request, dict):
            snap = request.get("planner_snapshot")
            if isinstance(snap, dict):
                self.seen_snapshot = dict(snap)
        elif hasattr(request, "planner_snapshot") and isinstance(request.planner_snapshot, dict):
            self.seen_snapshot = dict(request.planner_snapshot)
        return {
            "task_id": getattr(request, "task_id", "") if not isinstance(request, dict) else request.get("task_id", ""),
            "invoked": True,
            "output_delivered": True,
            "action": "candidate",
            "evidence_refs": ["local:test:fixture"],
            "verifier_summary": {"verifier_status": "pass", "verifier_reached": True, "exit_code": 0},
            "candidate_summary": {
                "isolation_status": "isolated",
                "selected_candidate_hash": "abc123",
                "selected_candidate_hash_matches_applied": True,
            },
            "receipt_path": "",
            "outcome_contributed": True,
        }


def test_runtime_receipt_contains_execution_depth():
    """Receipt must contain execution_depth from planner."""
    planner = _DepthPlanner()
    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        _request(),
        capability_invokers={
            "memory": lambda ctx: {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"memory:{ctx['task_id']}:fixture"],
            },
        },
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["execution_depth"] == "LIGHT"
    assert receipt["planner"]["execution_depth"] == "LIGHT"
    assert receipt["context_trace"]["execution_depth"] == "LIGHT"


def test_runtime_planner_stage_contains_execution_depth():
    """Planner stage must contain execution_depth."""
    planner = _DepthPlanner()
    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        _request(),
        capability_invokers={
            "memory": lambda ctx: {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"memory:{ctx['task_id']}:fixture"],
            },
        },
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    planner_stage = receipt["planner"]
    assert planner_stage["execution_depth"] == "LIGHT"


def test_runtime_context_trace_contains_execution_depth():
    """Context trace must contain execution_depth."""
    planner = _DepthPlanner()
    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        _request(),
        capability_invokers={
            "memory": lambda ctx: {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"memory:{ctx['task_id']}:fixture"],
            },
        },
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    context_trace = receipt["context_trace"]
    assert context_trace["execution_depth"] == "LIGHT"


def test_runtime_local_snapshot_contains_execution_depth():
    """Local planner snapshot must contain execution_depth."""
    planner = _DepthPlanner()
    local_service = _DepthLocalService()
    runtime = UnifiedRuntime(planner=planner, local_service=local_service)
    runtime.run(
        _request(local_enabled=True),
        capability_invokers={
            "memory": lambda ctx: {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"memory:{ctx['task_id']}:fixture"],
            },
        },
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert local_service.seen_snapshot.get("execution_depth") == "LIGHT"


def test_runtime_physical_json_receipt_contains_execution_depth(tmp_path):
    """Physical JSON receipt on disk must contain execution_depth."""
    planner = _DepthPlanner()
    runtime = UnifiedRuntime(planner=planner)
    receipt_path = tmp_path / "unified-receipt.json"
    receipt = runtime.run(
        _request(),
        capability_invokers={
            "memory": lambda ctx: {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"memory:{ctx['task_id']}:fixture"],
            },
        },
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
        receipt_path=receipt_path,
    )

    assert receipt_path.exists()
    disk_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert disk_receipt["execution_depth"] == "LIGHT"
    assert disk_receipt["planner"]["execution_depth"] == "LIGHT"
    assert disk_receipt["context_trace"]["execution_depth"] == "LIGHT"


def test_runtime_physical_receipt_uses_effective_execution_depth(tmp_path):
    """UnifiedRuntime physical receipt must record effective execution_depth from CapabilityPlanner."""
    runtime = UnifiedRuntime(planner=CapabilityPlanner())
    receipt_path = tmp_path / "unified-receipt.json"

    req = UnifiedRuntimeRequest(
        task_id="p0-t2-receipt-test",
        workspace_revision="rev-1",
        task_statement="Fix minor bug with candidate count 2.",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 2,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
        receipt_path=receipt_path,
    )

    assert receipt["execution_depth"] == "STANDARD"
    assert receipt["planner"]["execution_depth"] == "STANDARD"
    assert receipt["context_trace"]["execution_depth"] == "STANDARD"

    assert receipt_path.exists()
    disk_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert disk_receipt["execution_depth"] == "STANDARD"
    assert disk_receipt["planner"]["execution_depth"] == "STANDARD"
    assert disk_receipt["context_trace"]["execution_depth"] == "STANDARD"


def test_next_execution_depth_after_failure_contract():
    from nexus.engine.capability_contracts import next_execution_depth_after_failure

    assert next_execution_depth_after_failure("LIGHT") == "STANDARD"
    assert next_execution_depth_after_failure("STANDARD") == "FULL"
    assert next_execution_depth_after_failure("FULL") == "FULL"

    with pytest.raises(ValueError, match="invalid_execution_depth:INVALID"):
        next_execution_depth_after_failure("INVALID")


def test_runtime_light_trusted_verifier_failure_escalates_to_standard():
    runtime = UnifiedRuntime()

    def _verifier(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": False,
            "status": "failed",
            "evidence": "semantic assertion failed",
            "evidence_refs": ["verifier:test:semantic_failure"],
        }

    req = UnifiedRuntimeRequest(
        task_id="task-light-fail-1",
        workspace_revision="rev-1",
        task_statement="Safe low risk task",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=_verifier,
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert receipt["execution_depth"] == "LIGHT"
    assert receipt["receipt_complete"] is False
    assert receipt["terminal_status"] == "INCOMPLETE"

    req_contract = receipt["execution_replan_request"]
    assert req_contract["schema"] == "nexus.execution_replan_request.v1"
    assert req_contract["current_execution_depth"] == "LIGHT"
    assert req_contract["requested_execution_depth"] == "STANDARD"
    assert req_contract["trigger"] == "verifier_failed"
    assert req_contract["replan_required"] is True
    assert req_contract["depth_escalated"] is True
    assert req_contract["manual_review_required"] is False
    assert req_contract["verifier_outcome_trusted"] is True
    assert req_contract["verifier_status"] == "FAILED"
    assert req_contract["verifier_evidence_refs"] == ["verifier:test:semantic_failure"]
    assert req_contract["public_claim_allowed"] is False

    assert receipt["context_trace"]["execution_replan_request_id"] == req_contract["replan_request_id"]
    assert receipt["claim_boundary"]["replan_required"] is True
    assert receipt["claim_boundary"]["requested_execution_depth"] == "STANDARD"


def test_runtime_standard_trusted_verifier_failure_escalates_to_full():
    runtime = UnifiedRuntime()

    def _verifier(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": False,
            "status": "failed",
            "evidence": "hardened validation failed",
            "evidence_refs": ["verifier:test:hardened_fail"],
        }

    req = UnifiedRuntimeRequest(
        task_id="task-standard-fail-1",
        workspace_revision="rev-1",
        task_statement="Hardened L2 task",
        task_type="public_bugfix",
        route={
            "routing_tier": "L2_hardened",
            "execution_depth": "STANDARD",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 50,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 1,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=_verifier,
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert receipt["execution_depth"] == "STANDARD"
    req_contract = receipt["execution_replan_request"]
    assert req_contract["current_execution_depth"] == "STANDARD"
    assert req_contract["requested_execution_depth"] == "FULL"
    assert req_contract["trigger"] == "verifier_failed"
    assert req_contract["replan_required"] is True
    assert req_contract["depth_escalated"] is True
    assert req_contract["manual_review_required"] is False
    assert req_contract["verifier_outcome_trusted"] is True


def test_runtime_full_trusted_verifier_failure_requires_manual_review():
    runtime = UnifiedRuntime()

    def _verifier(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": False,
            "status": "failed",
            "evidence": "deep swarm failure",
            "evidence_refs": ["verifier:test:full_fail"],
        }

    req = UnifiedRuntimeRequest(
        task_id="task-full-fail-1",
        workspace_revision="rev-1",
        task_statement="Deep swarm task",
        task_type="public_bugfix",
        route={
            "routing_tier": "L3_swarm_deep",
            "execution_depth": "FULL",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 86,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 1,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=_verifier,
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert receipt["execution_depth"] == "FULL"
    req_contract = receipt["execution_replan_request"]
    assert req_contract["current_execution_depth"] == "FULL"
    assert req_contract["requested_execution_depth"] == "FULL"
    assert req_contract["trigger"] == "verifier_failed_at_full_depth"
    assert req_contract["replan_required"] is True
    assert req_contract["depth_escalated"] is False
    assert req_contract["manual_review_required"] is True
    assert req_contract["verifier_outcome_trusted"] is True


def test_runtime_passed_verifier_requests_no_replan():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-pass-1",
        workspace_revision="rev-1",
        task_statement="Safe low risk task",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    req_contract = receipt["execution_replan_request"]
    assert req_contract["replan_required"] is False
    assert req_contract["depth_escalated"] is False
    assert req_contract["manual_review_required"] is False
    assert req_contract["requested_execution_depth"] == "LIGHT"
    assert req_contract["trigger"] == "verifier_passed"
    assert req_contract["verifier_outcome_trusted"] is True


def test_runtime_missing_verifier_requests_no_replan():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-no-verifier-1",
        workspace_revision="rev-1",
        task_statement="Task without verifier",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=None,
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    req_contract = receipt["execution_replan_request"]
    assert req_contract["replan_required"] is False
    assert req_contract["requested_execution_depth"] == "LIGHT"
    assert req_contract["trigger"] == "verifier_not_observed"
    assert req_contract["verifier_outcome_trusted"] is False


def test_runtime_evidence_free_failed_verifier_requests_no_replan():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-evidence-free-1",
        workspace_revision="rev-1",
        task_statement="Task with evidence free failure",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "", "evidence_refs": []},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    req_contract = receipt["execution_replan_request"]
    assert req_contract["replan_required"] is False
    assert req_contract["requested_execution_depth"] == "LIGHT"
    assert req_contract["trigger"] == "verifier_evidence_untrusted"
    assert req_contract["verifier_outcome_trusted"] is False


def test_runtime_cross_task_verifier_requests_no_replan():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-correct-id-1",
        workspace_revision="rev-1",
        task_statement="Task with identity mismatch",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": "different-task-id-2", "invoked": True, "gate_passed": False, "status": "failed", "evidence": "wrong task", "evidence_refs": ["v:wrong"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    req_contract = receipt["execution_replan_request"]
    assert req_contract["replan_required"] is False
    assert req_contract["requested_execution_depth"] == "LIGHT"
    assert req_contract["trigger"] == "verifier_identity_mismatch"
    assert req_contract["verifier_outcome_trusted"] is False


def test_runtime_learning_observes_same_execution_replan_request():
    runtime = UnifiedRuntime()

    captured_learning_context = {}

    def _learning(ctx):
        captured_learning_context.update(dict(ctx))
        return {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True}

    req = UnifiedRuntimeRequest(
        task_id="task-learning-obs-1",
        workspace_revision="rev-1",
        task_statement="Learning observation task",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:ref1"]},
        learning=_learning,
    )

    assert "execution_replan_request" in captured_learning_context
    assert captured_learning_context["execution_replan_request"] == receipt["execution_replan_request"]
    assert captured_learning_context["execution_replan_request"]["replan_request_id"] == receipt["execution_replan_request"]["replan_request_id"]


def test_runtime_physical_receipt_disk_contains_replan_fields(tmp_path):
    runtime = UnifiedRuntime()
    receipt_path = tmp_path / "unified-receipt-replan.json"

    req = UnifiedRuntimeRequest(
        task_id="task-disk-replan-1",
        workspace_revision="rev-1",
        task_statement="Task for physical receipt replan test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "disk err", "evidence_refs": ["v:disk"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        receipt_path=receipt_path,
    )

    assert receipt_path.exists()
    disk_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert disk_receipt["execution_replan_request"] == receipt["execution_replan_request"]
    assert disk_receipt["context_trace"]["execution_replan_request_id"] == receipt["execution_replan_request"]["replan_request_id"]
    assert disk_receipt["claim_boundary"]["replan_required"] is True
    assert disk_receipt["claim_boundary"]["requested_execution_depth"] == "STANDARD"


def test_runtime_finalize_receipt_parity_and_replan(tmp_path):
    runtime = UnifiedRuntime()
    receipt_path = tmp_path / "unified-receipt-finalized.json"

    req = UnifiedRuntimeRequest(
        task_id="task-finalize-replan-1",
        workspace_revision="rev-1",
        task_statement="Task for finalize receipt test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    init_receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=None,
        learning=None,
    )

    finalized = runtime.finalize_receipt(
        init_receipt,
        verifier={
            "task_id": "task-finalize-replan-1",
            "invoked": True,
            "gate_passed": False,
            "status": "failed",
            "evidence": "postflight verifier failure",
            "evidence_refs": ["v:postflight_fail"],
        },
        learning={
            "task_id": "task-finalize-replan-1",
            "invoked": True,
            "gate_passed": True,
            "status": "succeeded",
        },
        receipt_path=receipt_path,
    )

    assert finalized["execution_depth"] == "LIGHT"
    req_contract = finalized["execution_replan_request"]
    assert req_contract["current_execution_depth"] == "LIGHT"
    assert req_contract["requested_execution_depth"] == "STANDARD"
    assert req_contract["trigger"] == "verifier_failed"
    assert req_contract["replan_required"] is True
    assert req_contract["depth_escalated"] is True
    assert req_contract["manual_review_required"] is False
    assert req_contract["verifier_outcome_trusted"] is True

    assert finalized["context_trace"]["execution_replan_request_id"] == req_contract["replan_request_id"]
    assert finalized["claim_boundary"]["replan_required"] is True
    assert finalized["claim_boundary"]["requested_execution_depth"] == "STANDARD"

    assert receipt_path.exists()
    disk_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert disk_receipt["execution_replan_request"]["replan_request_id"] == req_contract["replan_request_id"]


def test_runtime_deterministic_replan_request_id():
    runtime = UnifiedRuntime()

    def make_run(refs):
        req = UnifiedRuntimeRequest(
            task_id="task-deterministic-1",
            workspace_revision="rev-1",
            task_statement="Deterministic test",
            task_type="public_bugfix",
            route={
                "execution_depth": "LIGHT",
                "recommended_flow": "baseline",
                "route_features": {"risk_score": 10},
                "capability_stack": {"selected_capabilities": ["baseline"]},
            },
            online_enabled=True,
            local_enabled=False,
        )
        return runtime.run(
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "fail", "evidence_refs": refs},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )

    r1 = make_run(["refA", "refB"])
    r2 = make_run(["refA", "refB"])
    r3 = make_run(["refA", "refC"])

    id1 = r1["execution_replan_request"]["replan_request_id"]
    id2 = r2["execution_replan_request"]["replan_request_id"]
    id3 = r3["execution_replan_request"]["replan_request_id"]

    assert id1 == id2
    assert id1 != id3


def test_normal_runtime_receipt_has_attempt_one_identity():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-attempt-1",
        workspace_revision="rev-1",
        task_statement="Normal run attempt 1 test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    attempt = receipt["execution_attempt"]
    assert attempt["schema"] == "nexus.execution_attempt.v1"
    assert attempt["attempt_number"] == 1
    assert attempt["max_attempts"] == 2
    assert attempt["is_replan"] is False
    assert attempt["parent_receipt_hash"] == ""
    assert attempt["parent_run_anchor_hash"] == ""
    assert attempt["source_replan_request_id"] == ""
    assert receipt["claim_boundary"]["attempt_number"] == 1
    assert receipt["claim_boundary"]["replan_attempt"] is False


def test_controlled_replan_light_to_standard_succeeds(tmp_path):
    runtime = UnifiedRuntime()
    p1_path = tmp_path / "receipt_attempt_1.json"
    p2_path = tmp_path / "receipt_attempt_2.json"

    req = UnifiedRuntimeRequest(
        task_id="task-replan-flow-1",
        workspace_revision="rev-1",
        task_statement="Task for light to standard replan",
        task_type="public_bugfix",
        route={
            "online_policy": "auto",
            "injected_transport": True,
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "output_delivered": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["online:ok"]},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:ok"]},
        receipt_path=p1_path,
    )

    assert r1["execution_depth"] == "LIGHT"
    assert r1["terminal_status"] == "INCOMPLETE"

    invs = {cap: (lambda ctx, c=cap: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence": "ok", "evidence_refs": [f"cap:{c}:ok"]}) for cap in ["harness_preflight_sensor", "bdd_acceptance_skill", "acceptance_check", "claim_gate", "delivery_gate", "mempalace_gate", "research_route", "artifact_gate"]}

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "output_delivered": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["online:ok"]},
        capability_invokers=invs,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok2"]},
        learning=lambda ctx: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:ok"]},
        receipt_path=p2_path,
    )

    assert r2["execution_depth"] == "STANDARD"
    assert r2["terminal_status"] == "SUCCEEDED"
    assert r2["receipt_complete"] is True
    assert r2["execution_attempt"]["attempt_number"] == 2
    assert r2["execution_attempt"]["is_replan"] is True
    assert r2["execution_attempt"]["parent_receipt_hash"] == r1["receipt_hash"]
    assert r2["execution_attempt"]["parent_run_anchor_hash"] == r1["run_anchor_hash"]
    assert r2["execution_attempt"]["source_replan_request_id"] == r1["execution_replan_request"]["replan_request_id"]
    assert r2["claim_boundary"]["attempt_number"] == 2
    assert r2["claim_boundary"]["replan_attempt"] is True


def test_controlled_replan_standard_to_full_succeeds(tmp_path):
    runtime = UnifiedRuntime()
    p1_path = tmp_path / "r1_std.json"

    req = UnifiedRuntimeRequest(
        task_id="task-replan-std-1",
        workspace_revision="rev-1",
        task_statement="Hardened L2 task replan to full",
        task_type="public_bugfix",
        route={
            "routing_tier": "L2_hardened",
            "execution_depth": "STANDARD",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 50},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err std", "evidence_refs": ["v:std_fail"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        receipt_path=p1_path,
    )

    assert r1["execution_depth"] == "STANDARD"

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["execution_depth"] == "FULL"
    assert r2["execution_attempt"]["attempt_number"] == 2
    assert r2["execution_attempt"]["is_replan"] is True


def test_controlled_replan_floor_does_not_downgrade_natural_full():
    runtime = UnifiedRuntime()

    req_l1 = UnifiedRuntimeRequest(
        task_id="task-replan-nat-full-1",
        workspace_revision="rev-1",
        task_statement="Low risk task for attempt 1",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req_l1,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r1["execution_replan_request"]["requested_execution_depth"] == "STANDARD"

    req_l2 = UnifiedRuntimeRequest(
        task_id="task-replan-nat-full-1",
        workspace_revision="rev-1",
        task_statement="Now deep swarm signals on attempt 2",
        task_type="public_bugfix",
        route={
            "routing_tier": "L3_swarm_deep",
            "execution_depth": "FULL",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 86},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r2 = runtime.run_replan(
        r1,
        req_l2,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["execution_depth"] == "FULL"


def test_controlled_replan_uses_new_planner_decision_id():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-replan-dec-1",
        workspace_revision="rev-1",
        task_statement="Replan new decision ID test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r1["planner_decision_id"] != r2["planner_decision_id"]
    assert r2["execution_attempt"]["planner_decision_id"] == r2["planner_decision_id"]
    assert r2["execution_attempt"]["source_planner_decision_id"] == r1["planner_decision_id"]


def test_controlled_replan_preserves_first_receipt_unchanged(tmp_path):
    runtime = UnifiedRuntime()
    p1 = tmp_path / "receipt_attempt_1_orig.json"

    req = UnifiedRuntimeRequest(
        task_id="task-preserve-r1",
        workspace_revision="rev-1",
        task_statement="Preserve first receipt test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        receipt_path=p1,
    )

    r1_bytes_before = p1.read_bytes()

    runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        receipt_path=tmp_path / "receipt_attempt_2.json",
    )

    r1_bytes_after = p1.read_bytes()
    assert r1_bytes_before == r1_bytes_after


def test_controlled_replan_links_parent_receipt_and_run_anchor():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-link-anchor-1",
        workspace_revision="rev-1",
        task_statement="Link anchor test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["context_trace"]["parent_receipt_hash"] == r1["receipt_hash"]
    assert r2["context_trace"]["source_replan_request_id"] == r1["execution_replan_request"]["replan_request_id"]
    assert r2["planner"]["execution_attempt"]["parent_receipt_hash"] == r1["receipt_hash"]
    assert r2["planner"]["execution_attempt"]["parent_run_anchor_hash"] == r1["run_anchor_hash"]


def test_controlled_replan_learning_observes_lineage():
    runtime = UnifiedRuntime()

    captured_learning_context = {}

    def _learning_r2(ctx):
        captured_learning_context.update(dict(ctx))
        return {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True}

    req = UnifiedRuntimeRequest(
        task_id="task-learning-lineage-1",
        workspace_revision="rev-1",
        task_statement="Learning lineage test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=_learning_r2,
    )

    assert captured_learning_context["execution_attempt"]["attempt_number"] == 2
    assert captured_learning_context["parent_receipt_hash"] == r1["receipt_hash"]
    assert captured_learning_context["source_replan_request_id"] == r1["execution_replan_request"]["replan_request_id"]


def test_controlled_replan_invokes_each_stage_exactly_twice_total():
    runtime = UnifiedRuntime()

    invocations = {"online": 0, "verifier": 0, "learning": 0}

    def _online(ctx):
        invocations["online"] += 1
        return {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True}

    def _verifier_r1(ctx):
        invocations["verifier"] += 1
        return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "f", "evidence_refs": ["v:f"]}

    def _verifier_r2(ctx):
        invocations["verifier"] += 1
        return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]}

    def _learning(ctx):
        invocations["learning"] += 1
        return {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True}

    req = UnifiedRuntimeRequest(
        task_id="task-count-2",
        workspace_revision="rev-1",
        task_statement="Invocation count test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=_online,
        verifier=_verifier_r1,
        learning=_learning,
    )

    runtime.run_replan(
        r1,
        req,
        online_invoker=_online,
        verifier=_verifier_r2,
        learning=_learning,
    )

    assert invocations["online"] == 2
    assert invocations["verifier"] == 2
    assert invocations["learning"] == 2


def test_controlled_replan_rejects_caller_route_spoof():
    runtime = UnifiedRuntime()

    req1 = UnifiedRuntimeRequest(
        task_id="task-spoof-1",
        workspace_revision="rev-1",
        task_statement="Spoof test attempt 1",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req1,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    req_spoof = UnifiedRuntimeRequest(
        task_id="task-spoof-1",
        workspace_revision="rev-1",
        task_statement="Spoof test attempt 2",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "execution_replan_request": {"requested_execution_depth": "FULL"},
            "replan_authorization": {"requested_execution_depth": "FULL"},
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r2 = runtime.run_replan(
        r1,
        req_spoof,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["execution_depth"] == "STANDARD"


def test_controlled_replan_rejects_tampered_replan_request():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-tamper-req-1",
        workspace_revision="rev-1",
        task_statement="Tamper replan req test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    tampered_r1 = dict(r1)
    tampered_r1["execution_replan_request"] = dict(r1["execution_replan_request"])
    tampered_r1["execution_replan_request"]["replan_request_id"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

    with pytest.raises(ValueError, match="replan_request_integrity_mismatch|execution_replan_request_hash_mismatch"):
        runtime.run_replan(
            tampered_r1,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_rejects_tampered_prior_receipt_hash():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-tamper-hash-1",
        workspace_revision="rev-1",
        task_statement="Tamper prior receipt hash test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    tampered_r1 = dict(r1)
    tampered_r1["receipt_base"] = dict(r1["receipt_base"])
    tampered_r1["receipt_base"]["receipt_hash"] = "f" * 64

    with pytest.raises(ValueError, match="prior_receipt_base_invalid"):
        runtime.run_replan(
            tampered_r1,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_rejects_cross_task_receipt():
    runtime = UnifiedRuntime()

    req1 = UnifiedRuntimeRequest(
        task_id="task-orig-1",
        workspace_revision="rev-1",
        task_statement="Cross task test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req1,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    req2 = UnifiedRuntimeRequest(
        task_id="different-task-id-2",
        workspace_revision="rev-1",
        task_statement="Different task ID",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    with pytest.raises(ValueError, match="replan_task_id_mismatch"):
        runtime.run_replan(
            r1,
            req2,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_rejects_cross_revision_receipt():
    runtime = UnifiedRuntime()

    req1 = UnifiedRuntimeRequest(
        task_id="task-rev-1",
        workspace_revision="rev-1",
        task_statement="Cross rev test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req1,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    req2 = UnifiedRuntimeRequest(
        task_id="task-rev-1",
        workspace_revision="rev-different-2",
        task_statement="Cross rev test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    with pytest.raises(ValueError, match="replan_workspace_revision_mismatch"):
        runtime.run_replan(
            r1,
            req2,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_rejects_completed_prior_receipt():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-comp-1",
        workspace_revision="rev-1",
        task_statement="Completed receipt test",
        task_type="public_bugfix",
        route={
            "online_policy": "auto",
            "injected_transport": True,
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    invs = {cap: (lambda ctx, c=cap: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence": "ok", "evidence_refs": [f"cap:{c}:ok"]}) for cap in ["harness_preflight_sensor", "bdd_acceptance_skill", "acceptance_check", "claim_gate", "delivery_gate", "mempalace_gate", "research_route", "artifact_gate"]}

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "output_delivered": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["online:ok"]},
        capability_invokers=invs,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"task_id": ctx["task_id"], "status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:ok"]},
    )

    assert r1["receipt_complete"] is True

    with pytest.raises(ValueError, match="prior_receipt_not_incomplete"):
        runtime.run_replan(
            r1,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_rejects_untrusted_verifier_request():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-untrusted-ver-1",
        workspace_revision="rev-1",
        task_statement="Untrusted verifier test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "", "evidence_refs": []},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r1["execution_replan_request"]["verifier_outcome_trusted"] is False

    with pytest.raises(ValueError, match="replan_request_not_trusted"):
        runtime.run_replan(
            r1,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_rejects_full_manual_review():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-full-man-1",
        workspace_revision="rev-1",
        task_statement="Full manual review test",
        task_type="public_bugfix",
        route={
            "routing_tier": "L3_swarm_deep",
            "execution_depth": "FULL",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 86},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "deep fail", "evidence_refs": ["v:dfail"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r1["execution_replan_request"]["manual_review_required"] is True

    with pytest.raises(ValueError, match="replan_manual_review_required"):
        runtime.run_replan(
            r1,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_rejects_third_attempt():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-budget-3",
        workspace_revision="rev-1",
        task_statement="Budget exhausted test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "f1", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "f2", "evidence_refs": ["v:f2"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["execution_attempt"]["attempt_number"] == 2

    with pytest.raises(ValueError, match="replan_attempt_budget_exhausted"):
        runtime.run_replan(
            r2,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_controlled_replan_second_failure_stops_without_auto_chain():
    runtime = UnifiedRuntime()

    req = UnifiedRuntimeRequest(
        task_id="task-fail-twice-1",
        workspace_revision="rev-1",
        task_statement="Double failure test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "f1", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "f2", "evidence_refs": ["v:f2"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["receipt_complete"] is False
    assert r2["terminal_status"] == "INCOMPLETE"
    assert r2["execution_attempt"]["attempt_number"] == 2
    assert "execution_replan_request" in r2


def test_controlled_replan_physical_receipts_validate_strict(tmp_path):
    runtime = UnifiedRuntime()
    p1 = tmp_path / "attempt_1_disk.json"
    p2 = tmp_path / "attempt_2_disk.json"

    req = UnifiedRuntimeRequest(
        task_id="task-phys-strict-1",
        workspace_revision="rev-1",
        task_statement="Physical receipts strict validation test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )

    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "f1", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        receipt_path=p1,
    )

    assert p1.exists()
    disk_r1 = json.loads(p1.read_text(encoding="utf-8"))
    v1_res = validate_receipt_base(disk_r1, mode="strict")
    assert v1_res["ok"] is True

    r2 = runtime.run_replan(
        disk_r1,
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        receipt_path=p2,
    )

    assert p2.exists()
    disk_r2 = json.loads(p2.read_text(encoding="utf-8"))
    v2_res = validate_receipt_base(disk_r2, mode="strict")
    assert v2_res["ok"] is True

    assert disk_r2["execution_attempt"]["attempt_number"] == 2
    assert disk_r2["execution_attempt"]["parent_receipt_hash"] == disk_r1["receipt_hash"]
    assert disk_r2["execution_attempt"]["parent_run_anchor_hash"] == disk_r1["run_anchor_hash"]


class LegacyPlannerMock:
    """Mock Planner with pre-P0-T4 signature (no replan_authorization keyword parameter)."""

    def plan(
        self,
        *,
        task_desc: str,
        task_type: str,
        route: Mapping[str, Any],
        pillars: Mapping[str, Any],
        codeintel: Mapping[str, Any],
        phase_trace: Mapping[str, Any],
        budget: Mapping[str, Any],
        skills: Sequence[str],
    ) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus.capability_plan.v1",
            selected_capabilities=["baseline"],
            required_capabilities=[],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            planner_mode="dry_run",
            signal_snapshot={},
            execution_depth="LIGHT",
        )


def test_normal_runtime_supports_legacy_planner_signature():
    runtime = UnifiedRuntime(planner=LegacyPlannerMock())
    req = UnifiedRuntimeRequest(
        task_id="task-legacy-planner-1",
        workspace_revision="rev-1",
        task_statement="Legacy planner signature test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    receipt = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    assert len(receipt["planner_decision_id"]) == 64
    assert receipt["execution_depth"] == "LIGHT"


def test_run_replan_rejects_top_level_receipt_hash_substitution():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-top-sub-1",
        workspace_revision="rev-1",
        task_statement="Top level receipt hash substitution test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged_r1 = dict(r1)
    forged_r1["receipt_hash"] = "a" * 64

    with pytest.raises(ValueError, match="prior_receipt_base_invalid"):
        runtime.run_replan(
            forged_r1,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_run_replan_rejects_top_level_run_anchor_substitution():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-top-sub-2",
        workspace_revision="rev-1",
        task_statement="Top level run anchor substitution test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "failed", "evidence": "err", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged_r1 = dict(r1)
    forged_r1["run_anchor_hash"] = "b" * 64

    with pytest.raises(ValueError, match="prior_receipt_base_invalid"):
        runtime.run_replan(
            forged_r1,
            req,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


def test_strict_receipt_rejects_top_level_receipt_hash_substitution():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-strict-sub-1",
        workspace_revision="rev-1",
        task_statement="Strict receipt top level receipt hash substitution test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["receipt_hash"] = "c" * 64
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False
    assert "envelope_receipt_hash_mismatch" in res["blockers"]


def test_strict_receipt_rejects_top_level_run_anchor_substitution():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-strict-sub-2",
        workspace_revision="rev-1",
        task_statement="Strict receipt top level run anchor substitution test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["run_anchor_hash"] = "d" * 64
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False
    assert "envelope_run_anchor_hash_mismatch" in res["blockers"]


def test_strict_receipt_rejects_top_level_planner_decision_substitution():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-strict-sub-3",
        workspace_revision="rev-1",
        task_statement="Strict receipt top level planner decision substitution test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["planner_decision_id"] = "e" * 64
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False
    assert "envelope_planner_decision_id_mismatch" in res["blockers"]


def test_strict_receipt_rejects_root_execution_attempt_tamper():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-attempt-tamper-1",
        workspace_revision="rev-1",
        task_statement="Root execution attempt tamper test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["execution_attempt"] = dict(r1["execution_attempt"])
    forged["execution_attempt"]["attempt_number"] = 2
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False


def test_strict_receipt_rejects_planner_execution_attempt_tamper():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-attempt-tamper-2",
        workspace_revision="rev-1",
        task_statement="Planner execution attempt tamper test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["planner"] = dict(r1["planner"])
    forged["planner"]["execution_attempt"] = dict(r1["execution_attempt"])
    forged["planner"]["execution_attempt"]["attempt_number"] = 2
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False


def test_strict_receipt_rejects_context_execution_attempt_tamper():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-attempt-tamper-3",
        workspace_revision="rev-1",
        task_statement="Context execution attempt tamper test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["context_trace"] = dict(r1["context_trace"])
    forged["context_trace"]["execution_attempt"] = dict(r1["execution_attempt"])
    forged["context_trace"]["execution_attempt"]["attempt_number"] = 2
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False


def test_strict_receipt_rejects_attempt_number_tamper():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-attempt-tamper-4",
        workspace_revision="rev-1",
        task_statement="Attempt number tamper test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["execution_attempt"] = dict(r1["execution_attempt"])
    forged["execution_attempt"]["attempt_number"] = 99
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False


def test_strict_receipt_rejects_parent_lineage_tamper():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-attempt-tamper-5",
        workspace_revision="rev-1",
        task_statement="Parent lineage tamper test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["execution_attempt"] = dict(r1["execution_attempt"])
    forged["execution_attempt"]["parent_receipt_hash"] = "9" * 64
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False


def test_execution_attempt_hash_changes_receipt_hash():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-attempt-hash-1",
        workspace_revision="rev-1",
        task_statement="Execution attempt hash changes receipt hash test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "succeeded", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["execution_attempt"] = dict(r1["execution_attempt"])
    forged["execution_attempt"]["attempt_number"] = 2
    forged["planner"] = dict(r1["planner"])
    forged["planner"]["execution_attempt"] = dict(forged["execution_attempt"])
    forged["context_trace"] = dict(r1["context_trace"])
    forged["context_trace"]["execution_attempt"] = dict(forged["execution_attempt"])
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False


def test_strict_receipt_rejects_forged_verifier_with_rebuilt_replan_request():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-forged-v-1",
        workspace_revision="rev-1",
        task_statement="Forged verifier test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["verifier"] = {"task_id": req.task_id, "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "forged", "evidence_refs": ["v:forged"]}
    forged["execution_replan_request"] = build_execution_replan_request(
        task_id=req.task_id,
        planner_decision_id=r1["planner_decision_id"],
        current_execution_depth="LIGHT",
        verifier_stage=forged["verifier"],
    )
    res = validate_receipt_base(forged, mode="strict")
    assert res["ok"] is False


def test_run_replan_rejects_forged_verifier_with_rebuilt_replan_request():
    runtime = UnifiedRuntime()
    req = UnifiedRuntimeRequest(
        task_id="task-forged-replan-1",
        workspace_revision="rev-1",
        task_statement="Forged verifier replan test",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = runtime.run(
        req,
        online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    forged = dict(r1)
    forged["verifier"] = {"task_id": req.task_id, "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "forged", "evidence_refs": ["v:forged"]}
    forged["execution_replan_request"] = build_execution_replan_request(
        task_id=req.task_id,
        planner_decision_id=r1["planner_decision_id"],
        current_execution_depth="LIGHT",
        verifier_stage=forged["verifier"],
    )
    with pytest.raises((ValueError, Exception)):
        runtime.run_replan(
            req,
            previous_receipt=forged,
            online_invoker=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )


# Milestone A Tests — Hardened Subprocess Invoker & Sealed Process Evidence

def test_bare_gemini_print_flag_uses_argv_and_none_stdin(tmp_path):
    recorded = {}
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["argv"] = argv
        recorded["input"] = input
        recorded["cwd"] = cwd
        class Res:
            stdout = "gemini ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t1", "task_statement": "reply gemini"})
    assert recorded["argv"] == ["gemini", "-p", "reply gemini"]
    assert recorded["input"] in (None, "")
    assert res["gate_passed"] is True


def test_bare_codex_exec_uses_argv_and_none_stdin(tmp_path):
    recorded = {}
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["argv"] = argv
        recorded["input"] = input
        class Res:
            stdout = "codex ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="codex", command=("codex",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t2", "task_statement": "reply codex"})
    assert recorded["argv"] == ["codex", "exec", "reply codex"]
    assert recorded["input"] in (None, "")
    assert res["gate_passed"] is True


def test_admitted_codex_model_is_bound_in_physical_argv():
    recorded = {}

    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["argv"] = argv

        class Res:
            stdout = "codex bound"
            stderr = ""
            returncode = 0

        return Res()

    model = "gpt-5.6-luna"
    spec = OnlineCliSpec(provider="codex", command=("codex",), model_name=model)
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t2-bound", "task_statement": "reply codex"})

    assert recorded["argv"] == ["codex", "exec", "-m", model, "reply codex"]
    assert res["gate_passed"] is True


def test_bare_opencode_uses_registered_free_model(tmp_path):
    recorded = {}
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["argv"] = argv
        recorded["input"] = input
        class Res:
            stdout = "opencode ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="opencode", command=("opencode",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t3", "task_statement": "reply opencode"})
    assert recorded["argv"] == ["opencode", "run", "--model", "opencode/deepseek-v4-flash-free", "reply opencode"]
    assert recorded["input"] in (None, "")
    assert res["gate_passed"] is True


def test_admitted_opencode_model_is_bound_in_physical_argv():
    recorded = {}

    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["argv"] = argv

        class Res:
            stdout = "opencode bound"
            stderr = ""
            returncode = 0

        return Res()

    model = "opencode/mimo-v2.5-free"
    spec = OnlineCliSpec(provider="opencode", command=("opencode",), model_name=model)
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t3-bound", "task_statement": "reply opencode"})

    assert recorded["argv"] == ["opencode", "run", "--model", model, "reply opencode"]
    assert res["gate_passed"] is True


@pytest.mark.parametrize(
    ("provider", "command"),
    [
        ("codex", ("codex", "exec", "--json")),
        ("opencode", ("opencode", "run", "--format", "json")),
    ],
)
def test_legacy_custom_registered_cli_command_preserves_argv_without_authority(provider, command):
    calls = []

    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        calls.append((argv, input))

        class Res:
            stdout = "legacy custom ok"
            stderr = ""
            returncode = 0

        return Res()

    model = f"{provider}-legacy-model"
    spec = OnlineCliSpec(provider=provider, command=command, model_name=model)
    invoker = build_subprocess_online_invoker(spec, runner=runner)

    result = invoker({"task_id": f"{provider}-legacy-custom", "task_statement": "legacy prompt"})

    assert len(calls) == 1
    assert calls[0] == (list(command), "legacy prompt")
    assert result["gate_passed"] is True


@pytest.mark.parametrize(
    ("provider", "command"),
    [
        ("codex", ("codex", "exec")),
        ("codex", ("codex", "exec", "-m", "wrong-model")),
        ("opencode", ("opencode", "run")),
        ("opencode", ("opencode", "run", "--model", "wrong-model")),
    ],
)
def test_governed_custom_registered_cli_command_requires_exact_model_binding(provider, command):
    calls = []

    def runner(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("governed model-binding failure reached provider runner")

    model = f"{provider}-admitted-model"
    authority = {
        "schema": "nexus.gateway_invocation_authority.v1",
        "status": "ALLOW",
        "gate_passed": True,
        "resolved_provider": provider,
        "resolved_model": model,
    }
    spec = OnlineCliSpec(provider=provider, command=command, model_name=model)
    invoker = build_subprocess_online_invoker(spec, runner=runner)

    result = invoker(
        {
            "task_id": f"{provider}-governed-invalid-custom",
            "task_statement": "must not run",
            "gateway_invocation_authority": authority,
        }
    )

    assert result["error"] == "registered_cli_model_binding_command_shape_unsupported"
    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert calls == []


@pytest.mark.parametrize("provider", ["codex", "opencode"])
def test_governed_exact_custom_registered_cli_command_runs_with_admitted_model(provider):
    model = f"{provider}-admitted-model"
    subcommand, model_flag = REGISTERED_CLI_MODEL_BINDING_FLAGS[provider]
    command = (provider, subcommand, model_flag, model)
    recorded = {}

    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["argv"] = argv
        recorded["input"] = input

        class Res:
            stdout = "governed custom ok"
            stderr = ""
            returncode = 0

        return Res()

    authority = {
        "schema": "nexus.gateway_invocation_authority.v1",
        "status": "ALLOW",
        "gate_passed": True,
        "resolved_provider": provider,
        "resolved_model": model,
    }
    spec = OnlineCliSpec(provider=provider, command=command, model_name=model)
    invoker = build_subprocess_online_invoker(spec, runner=runner)

    result = invoker(
        {
            "task_id": f"{provider}-governed-exact-custom",
            "task_statement": "governed prompt",
            "gateway_invocation_authority": authority,
        }
    )

    assert recorded["argv"] == list(command)
    assert recorded["input"] == "governed prompt"
    assert result["invoked"] is True
    assert result["provider_call_count"] == 1
    assert result["gate_passed"] is True


@pytest.mark.parametrize(
    ("provider", "spec_model", "context_model", "error"),
    [
        ("codex", "wrong-model", "", "gateway_invocation_authority_model_mismatch"),
        ("opencode", "", "", "gateway_invocation_authority_model_missing"),
    ],
)
def test_authority_model_mismatch_or_omission_never_reaches_runner(
    provider, spec_model, context_model, error
):
    calls = []

    def runner(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("model-binding failure reached provider runner")

    authority = {
        "schema": "nexus.gateway_invocation_authority.v1",
        "status": "ALLOW",
        "gate_passed": True,
        "resolved_provider": provider,
        "resolved_model": "admitted-model",
    }
    spec = OnlineCliSpec(provider=provider, command=(provider,), model_name=spec_model)
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    context = {
        "task_id": f"{provider}-model-guard",
        "task_statement": "must not run",
        "gateway_invocation_authority": authority,
    }
    if context_model:
        context["online_model_name"] = context_model

    result = invoker(context)

    assert result["error"] == error
    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert calls == []


def test_explicit_multi_argument_command_uses_stdin(tmp_path):
    recorded = {}
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["argv"] = argv
        recorded["input"] = input
        class Res:
            stdout = "custom ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("python3", "-c", "import sys; print('ok')"))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t4", "task_statement": "custom prompt"})
    assert recorded["argv"] == ["python3", "-c", "import sys; print('ok')"]
    assert recorded["input"] == "custom prompt"
    assert res["gate_passed"] is True


def test_registered_cli_print_flag_has_no_unbound_local(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        class Res:
            stdout = "ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t5", "task_statement": "test unbound local"})
    assert res["invoked"] is True


def test_subprocess_invoker_passes_explicit_working_directory(tmp_path):
    recorded = {}
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["cwd"] = cwd
        class Res:
            stdout = "ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",), working_directory=str(tmp_path))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    invoker({"task_id": "t6", "task_statement": "cwd test"})
    assert recorded["cwd"] == str(tmp_path)


def test_subprocess_invoker_default_cwd_is_none(tmp_path):
    recorded = {}
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        recorded["cwd"] = cwd
        class Res:
            stdout = "ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    invoker({"task_id": "t7", "task_statement": "default cwd test"})
    assert recorded["cwd"] is None


def test_online_cli_spec_rejects_missing_working_directory():
    spec = OnlineCliSpec(provider="gemini", command=("gemini",), working_directory="/nonexistent/path/xyz_123")
    with pytest.raises(ValueError, match="working_directory_not_found"):
        spec.validate()


def test_online_cli_spec_rejects_file_as_working_directory(tmp_path):
    file_path = tmp_path / "some_file.txt"
    file_path.write_text("hello", encoding="utf-8")
    spec = OnlineCliSpec(provider="gemini", command=("gemini",), working_directory=str(file_path))
    with pytest.raises(ValueError, match="working_directory_not_directory"):
        spec.validate()


def test_parent_process_cwd_does_not_change(tmp_path):
    old_cwd = os.getcwd()
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        class Res:
            stdout = "ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",), working_directory=str(tmp_path))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    invoker({"task_id": "t8", "task_statement": "no chdir"})
    assert os.getcwd() == old_cwd


def test_process_evidence_contains_only_hashed_command_identity(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        class Res:
            stdout = "secret_output"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="opencode", command=("opencode",), working_directory=str(tmp_path))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t9", "task_statement": "my_secret_prompt"})
    evidence = res["process_evidence"]
    assert evidence["schema"] == "nexus.provider_process_evidence.v1"
    assert evidence["provider"] == "opencode"
    assert "command_fingerprint" in evidence
    assert "executable_path_hash" in evidence
    assert "working_directory_hash" in evidence
    assert "provider_input_sha256" in evidence
    assert "stdout_sha256" in evidence
    assert "stderr_sha256" in evidence


def test_process_evidence_does_not_expose_prompt(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        class Res:
            stdout = "ok"
            stderr = ""
            returncode = 0
        return Res()

    secret_prompt = "TOP_SECRET_PROMPT_12345"
    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t10", "task_statement": secret_prompt})
    evidence_str = json.dumps(res["process_evidence"])
    assert secret_prompt not in evidence_str


def test_process_evidence_does_not_expose_working_directory(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        class Res:
            stdout = "ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",), working_directory=str(tmp_path))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t11", "task_statement": "prompt"})
    evidence_str = json.dumps(res["process_evidence"])
    assert str(tmp_path) not in evidence_str


def test_process_evidence_attempt_ids_produce_unique_invocation_ids(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        class Res:
            stdout = "ok"
            stderr = ""
            returncode = 0
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    r1 = invoker({"task_id": "t12", "task_statement": "prompt", "attempt_id": "attempt_1_hash"})
    r2 = invoker({"task_id": "t12", "task_statement": "prompt", "attempt_id": "attempt_2_hash"})
    inv1 = r1["process_evidence"]["process_invocation_id"]
    inv2 = r2["process_evidence"]["process_invocation_id"]
    assert inv1 != inv2


def test_process_evidence_timeout_is_fail_closed(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t13", "task_statement": "prompt"})
    assert res["gate_passed"] is False
    evidence = res["process_evidence"]
    assert evidence["process_started"] is True
    assert evidence["returncode"] is None
    assert res["error"] == "provider_timeout"


def test_process_evidence_nonzero_exit_is_fail_closed(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        class Res:
            stdout = ""
            stderr = "error occurred"
            returncode = 1
        return Res()

    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t14", "task_statement": "prompt"})
    assert res["gate_passed"] is False
    evidence = res["process_evidence"]
    assert evidence["process_started"] is True
    assert evidence["returncode"] == 1
    assert res["error"] == "provider_subprocess_failed"


def test_process_evidence_oserror_records_not_invoked(tmp_path):
    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        raise OSError("Binary not found")

    spec = OnlineCliSpec(provider="gemini", command=("gemini",))
    invoker = build_subprocess_online_invoker(spec, runner=runner)
    res = invoker({"task_id": "t15", "task_statement": "prompt"})
    assert res["invoked"] is False
    assert res["gate_passed"] is False
    evidence = res["process_evidence"]
    assert evidence["process_started"] is False
    assert evidence["returncode"] is None
    assert res["error"] == "provider_not_invoked"
