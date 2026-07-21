from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.local_assist_service import (
    REQUEST_SCHEMA,
    LocalAssistRequest,
    LocalAssistService,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.unified_runtime import (
    ONLINE_CLI_SPEC_REGISTRY,
    OnlineCliSpec,
    UnifiedRuntime,
    UnifiedRuntimeRequest,
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
    assert set(ONLINE_CLI_SPEC_REGISTRY) == {"gemini", "agy", "grok", "codex", "openai"}
    assert all(
        item["transport"] == "subprocess" and item["binary_env"] and item["binary_name"]
        for item in ONLINE_CLI_SPEC_REGISTRY.values()
    )


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
