"""False-green elimination gates: seal fail-closed, postflight honesty, closure.

Does not introduce routes, planners, or parallel runtimes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.capability_evidence_bundle import (
    build_capability_evidence_bundle,
    record_consumption,
    verify_capability_evidence_bundle,
)
from nexus.services.capability_registry import (
    PROBE_ONLY_REASON_CODES,
    WIRED_REAL,
    build_wiring_matrix,
    classify_gap,
    physical_runtime_eligible_count,
)
from nexus.services.online_nexus_context import (
    build_online_nexus_context,
    evaluate_postflight_gate,
)
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)


class _Planner:
    def __init__(self, selected: list[str] | None = None, required: list[str] | None = None) -> None:
        self.selected = selected or [
            "codeintel",
            "memory",
            "belief",
            "artifact_gate",
            "claim_gate",
            "delivery_gate",
        ]
        self.required = required or ["codeintel"]

    def plan(self, **_: object) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=list(self.selected),
            required_capabilities=list(self.required),
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
        )


def _online(context: dict[str, Any]) -> dict[str, Any]:
    return normalize_online_invoker_payload(
        provider="fixture",
        task_id=str(context.get("task_id") or ""),
        invoked=True,
        output_delivered=True,
        gate_passed=True,
        provider_call_count=1,
        response={"ok": True},
        raw_response="ok",
        evidence_refs=[f"online:{context.get('task_id')}"],
    )


def _verifier_explicit(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": c["task_id"],
        "invoked": True,
        "gate_passed": True,
        "verifier_status": "pass",
        "verifier_artifact": "sha256:explicitverifierartifact00000001",
        "evidence_refs": [f"v:{c['task_id']}"],
    }


def _learning(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": c["task_id"],
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": [f"l:{c['task_id']}"],
    }


def test_p0_tampered_seal_blocks_local_and_online(monkeypatch) -> None:
    local_calls = {"n": 0}
    online_calls = {"n": 0}

    class _Local:
        def handle(self, request: Any) -> dict[str, Any]:
            local_calls["n"] += 1
            return {"status": "SUCCEEDED", "invoked": True, "gate_passed": True}

    def online(ctx: dict[str, Any]) -> dict[str, Any]:
        online_calls["n"] += 1
        return _online(ctx)

    import nexus.services.capability_evidence_bundle as ceb

    real_verify = ceb.verify_capability_evidence_bundle

    def _fail_verify(bundle):  # type: ignore[no-untyped-def]
        v = real_verify(bundle)
        if v.get("ok"):
            return {
                **v,
                "ok": False,
                "gate_passed": False,
                "blockers": ["forced_tamper_for_test"],
            }
        return v

    monkeypatch.setattr(ceb, "verify_capability_evidence_bundle", _fail_verify)

    runtime = UnifiedRuntime(planner=_Planner(), local_service=_Local())
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="seal-block-1",
            workspace_revision="wr",
            task_statement="must block local online on seal fail",
            task_type="repair",
            route={"recommended_flow": "hybrid", "provider": "gemini"},
            online_prompt="x",
            online_payload="y",
            local_enabled=True,
            local_request={"action": "advisor", "task_id": "seal-block-1"},
            evidence_refs=("t",),
        ),
        online_invoker=online,
        verifier=_verifier_explicit,
        learning=_learning,
    )
    assert receipt["terminal_status"] == "BLOCKED"
    assert receipt["receipt_complete"] is False
    assert receipt.get("capability_closure_complete") is False
    assert local_calls["n"] == 0
    assert online_calls["n"] == 0
    assert receipt.get("local_call_count") == 0
    assert receipt.get("online_call_count") == 0
    # seal_verify must not be written back into sealed body
    bundle = receipt.get("capability_evidence_bundle") or {}
    assert "seal_verify" not in bundle
    assert receipt.get("seal_verify", {}).get("ok") is False
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_p0_arbitrary_evidence_ref_fails_three_postflight_gates() -> None:
    context = {
        "task_id": "pf-1",
        "task_statement": "postflight honesty",
        "source_hash": "abc123sourcehashvaluehere",
        "online": {"invoked": True, "status": "SUCCEEDED"},
        "verifier": {
            "invoked": True,
            "gate_passed": True,
            # only evidence_refs — must NOT auto-promote to artifact/status
            "evidence_refs": ["verifier:arbitrary:ref"],
        },
        "capability_evidence_bundle": {"bundle_hash": "deadbeef" * 8, "source_hash": "abc123sourcehashvaluehere"},
    }
    for name in ("artifact_gate", "claim_gate", "delivery_gate"):
        verdict = evaluate_postflight_gate(name, context)
        assert verdict["gate_passed"] is False, name
        assert verdict["public_claim_allowed"] is False
        blockers = set(verdict.get("blockers") or [])
        assert blockers, name


def test_p0_empty_evidence_ids_not_consumed() -> None:
    bundle = build_capability_evidence_bundle(
        task_id="empty-1",
        workspace_revision="wr",
        task_statement="empty consume",
        plan_payload={"x": 1},
        plan_hash="ph",
        planner_decision_id="pd",
        capability_results={
            "codeintel": {
                "status": "SUCCEEDED",
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [],
            }
        },
        selected_capabilities=["codeintel"],
        source_hash="src",
    )
    rec = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=[],
        selected_capabilities=["codeintel"],
    )
    assert rec["capability_consumed"] is False
    # synthetic bundle:hash must not count
    rec2 = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=[f"bundle:{str(bundle.get('bundle_hash') or '')[:16]}"],
        selected_capabilities=["codeintel"],
    )
    assert rec2["capability_consumed"] is False
    assert rec2["consumed_evidence_ids"] == []


def test_p0_bundle_hash_not_delivery_artifact() -> None:
    context = {
        "task_id": "del-1",
        "source_hash": "src_hash_value_long_enough_01",
        "online": {"invoked": True},
        "verifier": {
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            # no real verifier_artifact
        },
        "capability_evidence_bundle": {"bundle_hash": "a" * 64, "source_hash": "src_hash_value_long_enough_01"},
    }
    verdict = evaluate_postflight_gate("delivery_gate", context)
    assert verdict["gate_passed"] is False


def test_p1_f_wired_ok_is_honest_production_set() -> None:
    matrix = build_wiring_matrix()
    f_rows = [r for r in matrix["rows"] if r["gap_class"] == "F_wired_ok"]
    # physical_runtime_eligible is honest (not forced 91)
    assert matrix["physical_runtime_eligible"] == len(f_rows)
    assert physical_runtime_eligible_count() == len(f_rows)
    assert len(f_rows) < 91
    for row in f_rows:
        assert classify_gap(row["name"]) == "F_wired_ok"
        assert row["name"] in WIRED_REAL or row["name"] == "local_model_executor"
        # probe-only names must never be F
        assert row["name"] not in PROBE_ONLY_REASON_CODES
    for name, reason in PROBE_ONLY_REASON_CODES.items():
        if name in {r["name"] for r in matrix["rows"]}:
            assert classify_gap(name) == "E_escalate_ok"
            row = next(r for r in matrix["rows"] if r["name"] == name)
            assert row.get("reason_code") == reason


def test_p1_monkeypatch_real_engine_fail_blocks_success(monkeypatch) -> None:
    """Monkeypatch production engine path → capability must not stay SUCCEEDED."""
    from nexus.services import capability_registry as cr

    inv = cr.build_real_executor_invoker("codeintel")
    assert inv is not None

    def _boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("engine_forced_fail")

    monkeypatch.setattr(
        "nexus.core.capability_executor_registry.get_executor",
        lambda _name: _boom,
    )
    # Rebuild invoker after patch
    inv2 = cr.build_real_executor_invoker("codeintel")
    assert inv2 is not None
    out = inv2(
        {
            "task_id": "mp-1",
            "task_statement": "force engine failure",
            "planner": {"plan_hash": "p"},
        }
    )
    assert out.get("gate_passed") is False
    assert out.get("status") in {"BLOCKED", "FAILED"}


def test_p2_shared_hashes_and_consumption_fields(monkeypatch) -> None:
    """Local/Online share sealed hashes; selected ≠ used; consumption is real IDs."""
    planner = _Planner(
        selected=["codeintel", "memory", "belief", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )
    # Provide real evidence via invokers that succeed with ids
    def codeintel(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "evidence_refs": [f"capability:codeintel:{ctx['task_id']}:real"],
            "evidence_ids": [f"capability:codeintel:{ctx['task_id']}:real"],
            "physical_callable": "test:codeintel",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    def memory(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "evidence_refs": [f"capability:memory:{ctx['task_id']}:real"],
            "evidence_ids": [f"capability:memory:{ctx['task_id']}:real"],
            "physical_callable": "test:memory",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    def belief(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "evidence_refs": [f"capability:belief:{ctx['task_id']}:real"],
            "evidence_ids": [f"capability:belief:{ctx['task_id']}:real"],
            "physical_callable": "test:belief",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="cons-1",
            workspace_revision="wr",
            task_statement="shared consumption proof for codeintel memory belief",
            task_type="repair",
            route={"recommended_flow": "direct", "provider": "gemini"},
            online_prompt="return ok",
            online_payload="payload",
            local_enabled=False,
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        capability_invokers={
            "codeintel": codeintel,
            "memory": memory,
            "belief": belief,
        },
        verifier=_verifier_explicit,
        learning=_learning,
    )
    bundle = receipt.get("capability_evidence_bundle") or {}
    assert receipt.get("planner_decision_id")
    assert bundle.get("bundle_hash")
    assert bundle.get("baseline_hash")
    assert bundle.get("planner_decision_id") == receipt.get("planner_decision_id")
    # selected / executed / consumed / contributed are distinct fields
    assert "selected_capabilities" in receipt
    assert "executed_capabilities" in receipt
    assert "consumed_evidence_ids" in receipt
    assert "contributed_capabilities" in receipt
    assert receipt["claim_boundary"]["public_claim_allowed"] is False

    # Online context consumption for codeintel/memory/belief
    ctx = build_online_nexus_context(
        task_id="cons-1",
        task_statement="shared consumption proof",
        plan={
            "plan_hash": str(bundle.get("plan_hash") or ""),
            "planner_decision_id": str(bundle.get("planner_decision_id") or ""),
            "selected_capabilities": list(bundle.get("selected_capabilities") or []),
            "capability_evidence_bundle": bundle,
        },
        capability_evidence_bundle=bundle,
        codeintel={"scan_report_present": True, "risk_score": 1},
    )
    d = ctx.to_dict() if hasattr(ctx, "to_dict") else {}
    lineage = d.get("lineage") or d
    # Removing evidence must fail consumption proof
    empty = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=[],
    )
    assert empty["capability_consumed"] is False
    # Real IDs that match successful entries should be consumable
    real_ids = []
    for ent in bundle.get("entries") or []:
        if ent.get("name") in {"codeintel", "memory", "belief"} and (
            ent.get("success") or ent.get("invoked_real")
        ):
            real_ids.extend(ent.get("evidence_ids") or ent.get("evidence_refs") or [])
    assert real_ids, "expected successful entry evidence for codeintel/memory/belief"
    ok = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=real_ids[:3],
    )
    assert ok["capability_consumed"] is True
    bad = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=["capability:codeintel:cons-1:FORGED"],
    )
    assert bad["capability_consumed"] is False
    # lineage must not invent bundle: envelope as sole consumption
    lineage_ids = list(lineage.get("consumed_evidence_ids") or [])
    assert not any(str(i).startswith("bundle:") for i in lineage_ids)


def test_p4_receipt_complete_vs_capability_closure_complete() -> None:
    """Required-only success may set receipt_complete; optional fail keeps closure false."""
    planner = _Planner(
        selected=["codeintel", "repair_loop", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )

    def codeintel(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "evidence_refs": [f"capability:codeintel:{ctx['task_id']}:real"],
            "physical_callable": "test:codeintel",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    def repair_loop(ctx):
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": False,
            "status": "FAILED",
            "evidence_refs": [f"capability:repair_loop:{ctx['task_id']}:fail"],
            "physical_callable": "test:repair_loop",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="closure-1",
            workspace_revision="wr",
            task_statement="closure separation",
            task_type="repair",
            route={"recommended_flow": "direct", "provider": "gemini"},
            online_prompt="x",
            online_payload="y",
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        capability_invokers={"codeintel": codeintel, "repair_loop": repair_loop},
        verifier=_verifier_explicit,
        learning=_learning,
    )
    # Task success may complete when required ok
    assert receipt["receipt_complete"] is True
    # Full wiring closure must be false while optional executable failed
    assert receipt.get("capability_closure_complete") is False
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_p4_matrix_uses_tmp_workspace_only(tmp_path: Path, monkeypatch) -> None:
    """Full capability matrix must not mutate production writeback paths."""
    writeback = Path(".nexus/reports/learn/phase_writeback.jsonl")
    before = writeback.read_bytes() if writeback.exists() else b""
    monkeypatch.chdir(tmp_path)
    # Import matrix helpers without running full slow suite — ensure dry-run intent.
    from nexus.services.capability_registry import build_wiring_matrix

    m = build_wiring_matrix()
    assert "physical_runtime_eligible" in m
    # chdir away from repo: production writeback unchanged
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    after = writeback.read_bytes() if writeback.exists() else b""
    assert after == before
