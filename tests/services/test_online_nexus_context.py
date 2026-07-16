"""P0: true with_nexus Online armor wired into UnifiedRuntime (ROUTING FREEZE)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.services.online_nexus_context import (
    NEXUS_CODEINTEL_MARKER,
    NEXUS_ROUTE_MARKER,
    build_codeintel_preflight_invoker,
    build_online_nexus_context,
    make_with_nexus_online_invoker,
    prompt_has_with_nexus_sections,
)
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)


def _codeintel_fixture() -> dict[str, Any]:
    return {
        "scan_report_present": True,
        "impact_report_present": True,
        "risk_score": 7,
        "risk_reason": ["impacted_module"],
        "impacted_files_count": 2,
        "impacted_symbols_count": 4,
        "dci_evidence_count": 1,
        "dci_locator_report_path": "artifacts/codeintel/fixture.json",
    }


def test_build_online_nexus_context_includes_route_and_codeintel_sections() -> None:
    ctx = build_online_nexus_context(
        task_statement="scan impact and repair parse_kv",
        task_id="p0-ctx-001",
        task_type="codeintel",
        route={"recommended_flow": "direct", "route_decision": {"selected_capabilities": ["codeintel"]}},
        codeintel=_codeintel_fixture(),
        plan={
            "selected_capabilities": ["codeintel", "artifact_gate"],
            "plan_hash": "abc123",
            "planner_decision_id": "abc123",
        },
    )
    assert NEXUS_ROUTE_MARKER in ctx.prompt
    assert NEXUS_CODEINTEL_MARKER in ctx.prompt
    assert "route" in ctx.prompt_sections_present
    assert "codeintel" in ctx.prompt_sections_present
    assert ctx.codeintel_present is True
    assert ctx.selected_capabilities == ("codeintel", "artifact_gate")
    assert ctx.plan_hash == "abc123"
    flags = prompt_has_with_nexus_sections(ctx.prompt)
    assert flags["route"] is True
    assert flags["codeintel"] is True


def test_bare_prompt_lacks_with_nexus_sections() -> None:
    bare = "Please fix parse_kv and run tests."
    flags = prompt_has_with_nexus_sections(bare)
    assert flags["route"] is False
    assert flags["codeintel"] is False


def test_with_nexus_invoker_enriches_prompt_and_lineage() -> None:
    seen: dict[str, Any] = {}

    def base_invoker(context: dict[str, Any]) -> dict[str, Any]:
        seen["online_prompt"] = str(context.get("online_prompt") or "")
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=str(context.get("task_id") or ""),
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "ok", "note": "fixture"},
            raw_response='{"status":"ok"}',
            evidence_refs=[f"online:{context.get('task_id')}:fixture"],
            transport="structured_callable",
            selection_source="explicit_request",
        )

    invoker = make_with_nexus_online_invoker(base_invoker, provider="fixture")
    payload = invoker(
        {
            "task_id": "p0-inv-001",
            "task_statement": "scan impact codeintel refactor",
            "task_type": "codeintel",
            "online_prompt": "bare task only",
            "route": {"recommended_flow": "direct"},
            "codeintel": _codeintel_fixture(),
            "planner": {
                "selected_capabilities": ["codeintel"],
                "plan_hash": "plan-xyz",
                "signal_snapshot": {"planner_decision_id": "plan-xyz"},
            },
            "local": {"invoked": False},
            "capability_results": {},
        }
    )
    assert NEXUS_ROUTE_MARKER in seen["online_prompt"]
    assert NEXUS_CODEINTEL_MARKER in seen["online_prompt"]
    assert "bare task only" not in seen["online_prompt"] or NEXUS_ROUTE_MARKER in seen["online_prompt"]
    assert payload["armor"] == "with_nexus"
    assert "route" in payload["prompt_sections_present"]
    assert "codeintel" in payload["prompt_sections_present"]
    assert payload["with_nexus"]["codeintel_present"] is True
    assert payload["with_nexus"]["plan_hash"] == "plan-xyz"
    assert any("with_nexus_armor" in ref for ref in payload["evidence_refs"])


def test_unified_runtime_with_nexus_vs_bare_distinguishable(tmp_path: Path) -> None:
    """Nexus arm prompt sections present; bare arm lacks them. FREEZE: no new route."""
    captured: dict[str, str] = {}

    def bare_online(context: dict[str, Any]) -> dict[str, Any]:
        captured["bare"] = str(context.get("online_prompt") or "")
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=str(context["task_id"]),
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "ok", "arm": "bare"},
            raw_response="ok",
            evidence_refs=[f"online:{context['task_id']}:bare"],
        )

    def capture_base(context: dict[str, Any]) -> dict[str, Any]:
        captured["nexus"] = str(context.get("online_prompt") or "")
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=str(context["task_id"]),
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "ok", "arm": "nexus"},
            raw_response="ok",
            evidence_refs=[f"online:{context['task_id']}:base"],
        )

    def verifier(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"verifier:{context['task_id']}"],
        }

    def learning(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"learning:{context['task_id']}"],
        }

    codeintel = _codeintel_fixture()
    # Task wording that yields codeintel on CapabilityPlanner (see planner probe).
    task_statement = "scan impact risk codeintel refactor module"
    route = {
        "recommended_flow": "direct",
        "risk_score": 8,
        "injected_transport": True,
        "online_policy": "auto",
    }

    bare_req = UnifiedRuntimeRequest(
        task_id="p0-bare-001",
        workspace_revision="rev-p0",
        task_statement=task_statement,
        task_type="codeintel",
        route=route,
        online_enabled=True,
        local_enabled=False,
        online_prompt="bare task only — no nexus armor",
        codeintel=codeintel,
    )
    bare_receipt = UnifiedRuntime().run(
        bare_req,
        online_invoker=bare_online,
        verifier=verifier,
        learning=learning,
        receipt_path=tmp_path / "bare_receipt.json",
    )

    nexus_req = UnifiedRuntimeRequest(
        task_id="p0-nexus-001",
        workspace_revision="rev-p0",
        task_statement=task_statement,
        task_type="codeintel",
        route=route,
        online_enabled=True,
        local_enabled=False,
        online_prompt="will be replaced by with_nexus assembly",
        codeintel=codeintel,
    )
    nexus_invoker = make_with_nexus_online_invoker(capture_base, provider="fixture")
    codeintel_invoker = build_codeintel_preflight_invoker(codeintel=codeintel)
    nexus_receipt = UnifiedRuntime().run(
        nexus_req,
        online_invoker=nexus_invoker,
        capability_invokers={"codeintel": codeintel_invoker},
        verifier=verifier,
        learning=learning,
        receipt_path=tmp_path / "nexus_receipt.json",
    )

    # Bare lacks armor sections
    assert NEXUS_ROUTE_MARKER not in captured["bare"]
    assert NEXUS_CODEINTEL_MARKER not in captured["bare"]
    bare_trace = bare_receipt["context_trace"]["online_received_context"]
    assert bare_trace.get("with_nexus_armor") is False

    # Nexus has armor sections + planner plan hash lineage
    assert NEXUS_ROUTE_MARKER in captured["nexus"]
    assert NEXUS_CODEINTEL_MARKER in captured["nexus"]
    nexus_online = nexus_receipt["online"]["response"]
    assert nexus_online["armor"] == "with_nexus"
    assert "route" in nexus_online["prompt_sections_present"]
    assert "codeintel" in nexus_online["prompt_sections_present"]
    assert nexus_receipt["planner"]["invoked"] is True
    assert nexus_receipt["planner"]["plan_hash"]
    assert nexus_receipt["context_trace"]["online_received_context"]["with_nexus_armor"] is True
    assert nexus_receipt["context_trace"]["online_received_context"]["codeintel_present"] is True
    assert nexus_receipt["claim_boundary"]["public_claim_allowed"] is False

    # codeintel selected → preflight invoker ran
    selected = list(nexus_receipt["context_trace"]["selected_capabilities"])
    assert "codeintel" in selected
    assert "codeintel" in nexus_receipt["capability_results"]
    assert nexus_receipt["capability_results"]["codeintel"]["invoked"] is True

    # FREEZE: no new recommended_flow / topology invented on receipt
    assert nexus_req.route.get("recommended_flow") == "direct"
    assert "execution_topology" not in nexus_receipt.get("planner", {})


def test_non_selected_capability_invoker_skipped(tmp_path: Path) -> None:
    calls: list[str] = []

    def memory_invoker(context: dict[str, Any]) -> dict[str, Any]:
        calls.append("memory")
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"capability:memory:{context['task_id']}"],
        }

    def online(context: dict[str, Any]) -> dict[str, Any]:
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            raw_response="ok",
            evidence_refs=[f"online:{context['task_id']}"],
        )

    def verifier(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"verifier:{context['task_id']}"],
        }

    def learning(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"learning:{context['task_id']}"],
        }

    # Simple repair task: memory typically not selected unless signals demand it.
    req = UnifiedRuntimeRequest(
        task_id="p0-skip-001",
        workspace_revision="rev-p0",
        task_statement="trivial hello world rewrite",
        task_type="content",
        route={"recommended_flow": "direct", "injected_transport": True, "online_policy": "auto"},
        online_enabled=True,
        online_prompt="say hi",
    )
    receipt = UnifiedRuntime().run(
        req,
        online_invoker=online,
        capability_invokers={"memory": memory_invoker},
        verifier=verifier,
        learning=learning,
    )
    selected = set(receipt["context_trace"]["selected_capabilities"])
    if "memory" not in selected:
        assert "memory" not in receipt["capability_results"]
        assert calls == []
    else:
        # If planner did select memory, invoker must have run — still plan-gated.
        assert calls == ["memory"]
