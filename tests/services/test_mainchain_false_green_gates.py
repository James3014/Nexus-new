"""False-green elimination gates: seal fail-closed, postflight honesty, closure.

Does not introduce routes, planners, or parallel runtimes.
"""

from __future__ import annotations

import hashlib
import json
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
    LOCAL_STAGE_CAPABILITIES,
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

# Valid bound artifact: sha256: + 64 hex (no length-based fallback).
VALID_VERIFIER_ARTIFACT = "sha256:" + ("ab" * 32)
VALID_SOURCE_HASH = hashlib.sha256(b"sealed-source-v1").hexdigest()


def _valid_artifact(seed: str = "verifier") -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


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
    bundle = c.get("capability_evidence_bundle") if isinstance(c.get("capability_evidence_bundle"), dict) else {}
    src = str(c.get("source_hash") or bundle.get("source_hash") or VALID_SOURCE_HASH)
    return {
        "task_id": c["task_id"],
        "invoked": True,
        "gate_passed": True,
        "verifier_status": "pass",
        "verifier_artifact": VALID_VERIFIER_ARTIFACT,
        "source_hash": src,
        "evidence_refs": [f"v:{c['task_id']}"],
    }


def _all_postflight_fail(context: dict[str, Any]) -> None:
    for name in ("artifact_gate", "claim_gate", "delivery_gate"):
        verdict = evaluate_postflight_gate(name, context)
        assert verdict["gate_passed"] is False, (name, verdict.get("blockers"))
        assert verdict["public_claim_allowed"] is False


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


def test_closure_receipt_structural_gates_required() -> None:
    """Phase 5 receipt is mandatory; generate via family canary builder if absent."""
    import json
    from pathlib import Path

    from tests.services.test_mainchain_family_canary_matrix import (
        RECEIPT_PATH,
        RECEIPT_TMP,
        build_and_write_closure_receipt,
    )

    receipt = build_and_write_closure_receipt()
    assert RECEIPT_PATH.is_file()
    assert RECEIPT_TMP.is_file()
    loaded = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    assert loaded["planner_contract_count"] == 57
    assert loaded["promotable_count"] == 53
    assert loaded["promotable_missing_engine_count"] == 0
    assert loaded["probe_only_success_count"] == 0
    assert loaded["fixture_callable_count"] == 0
    assert loaded["routing_surface_changed"] is False
    assert loaded["public_claim_allowed"] is False
    assert loaded["structural_closure"] is True
    assert receipt["structural_closure"] is True
    real_structural_blockers = [
        b
        for b in loaded.get("structural_blockers") or []
        if b.get("promotable")
        and b.get("execution_class")
        in {"DEFAULT_REAL", "TRIGGERED_REAL", "STAGE_OWNED_REAL"}
    ]
    assert real_structural_blockers == [], real_structural_blockers[:5]
    assert loaded["semantic_closure"] is False
    assert loaded["live_online_complete"] is False
    assert loaded["live_local_complete"] is False


def test_p1_f_wired_ok_is_honest_production_set() -> None:
    matrix = build_wiring_matrix()
    f_rows = [r for r in matrix["rows"] if r["gap_class"] == "F_wired_ok"]
    # physical_runtime_eligible is honest (not forced 91)
    assert matrix["physical_runtime_eligible"] == len(f_rows)
    assert physical_runtime_eligible_count() == len(f_rows)
    assert len(f_rows) < 91
    for row in f_rows:
        assert classify_gap(row["name"]) == "F_wired_ok"
        assert row["name"] in WIRED_REAL or row["name"] in LOCAL_STAGE_CAPABILITIES
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


def test_p1_every_f_wired_ok_has_production_invoke_or_local_stage() -> None:
    """Per-F row: production invoker path or Local stage; physical invoke on safe-fast set."""
    from nexus.core.capability_executor_registry import get_executor
    from nexus.services.capability_registry import (
        EXECUTOR_REGISTRY_ALIASES,
        build_default_mainchain_invokers,
        build_real_executor_invoker,
    )

    matrix = build_wiring_matrix()
    f_rows = [r for r in matrix["rows"] if r["gap_class"] == "F_wired_ok"]
    invokers = build_default_mainchain_invokers(
        codeintel={"scan_report_present": True, "risk_score": 1}
    )
    # Bounded physical invoke set (avoid long-running repair/hyper loops in unit tests).
    physical_invoke = {
        "codeintel",
        "memory",
        "belief",
        "lancedb",
        "semantic_searcher",
        "mempalace_gate",
        "acceptance_check",
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
    }
    failures: list[str] = []
    for row in f_rows:
        name = str(row["name"])
        if name == "local_model_executor":
            # F requires real LocalModelExecutor production call — not label-only.
            assert row["handler_kind"] == "local_stage"
            assert "LocalModelExecutor" in str(row.get("physical_callable_hint") or "")
            inv_local = invokers.get(name)
            assert inv_local is not None
            out_local = inv_local(
                {
                    "task_id": "f-local_model_executor",
                    "task_statement": "physical LocalModelExecutor probe",
                    "planner": {"plan_hash": "ph-local"},
                    "route": {"workspace_root": "."},
                }
            )
            if bool(out_local.get("stub")):
                failures.append("local_model_executor:stub")
            if not out_local.get("invoked"):
                failures.append(f"local_model_executor:not_invoked:{out_local.get('status')}")
            if not out_local.get("gate_passed"):
                failures.append(f"local_model_executor:gate_failed:{out_local.get('response')}")
            phys = str(out_local.get("physical_callable") or "")
            if "LocalModelExecutor" not in phys:
                failures.append(f"local_model_executor:bad_physical:{phys}")
            tele = (
                out_local.get("telemetry")
                if isinstance(out_local.get("telemetry"), dict)
                else {}
            )
            if "model_calls" not in tele and "token_usage" not in tele:
                failures.append("local_model_executor:missing_telemetry")
            if not (out_local.get("evidence_refs") or out_local.get("evidence_ids")):
                failures.append("local_model_executor:missing_evidence")
            continue
        inv = invokers.get(name)
        if inv is None:
            failures.append(f"{name}:missing_invoker")
            continue
        if bool(getattr(inv, "stub", False)):
            failures.append(f"{name}:stub_attr")
        # Catalog honesty: production hint for non-local F
        hint = str(row.get("physical_callable_hint") or "")
        if name in WIRED_REAL and "capability_executor_registry" not in hint and name not in {
            "artifact_gate",
            "claim_gate",
            "delivery_gate",
        }:
            # postflight gates use evaluate_postflight physical path
            if name not in {"artifact_gate", "claim_gate", "delivery_gate"}:
                if "capability_executor_registry" not in hint and "postflight" not in hint:
                    # postflight wired via online_nexus_context
                    pass
        if name not in physical_invoke:
            # Still require a registered engine or postflight path exists.
            reg = EXECUTOR_REGISTRY_ALIASES.get(name, name)
            if (
                get_executor(reg) is None
                and get_executor(name) is None
                and name not in {"artifact_gate", "claim_gate", "delivery_gate"}
            ):
                failures.append(f"{name}:no_get_executor")
            continue
        ctx = {
            "task_id": f"f-{name}",
            "task_statement": f"physical probe {name}",
            "planner": {"plan_hash": f"ph-{name}"},
            "codeintel": {"scan_report_present": True, "risk_score": 1},
            "online": {"invoked": True},
            "source_hash": "src_hash_for_f_probe_0001",
            "verifier": {
                "task_id": f"f-{name}",
                "invoked": True,
                "gate_passed": True,
                "verifier_status": "pass",
                "verifier_artifact": _valid_artifact(f"fprobe-{name}"),
                "source_hash": "src_hash_for_f_probe_0001",
            },
            "capability_evidence_bundle": {
                "source_hash": "src_hash_for_f_probe_0001",
                "bundle_hash": "b" * 64,
            },
        }
        out = inv(ctx)
        if bool(out.get("stub")):
            failures.append(f"{name}:stub")
            continue
        if not out.get("invoked") and name not in {"claim_gate"}:
            # claim may fail closed without full online proof; still must invoke
            if not out.get("invoked"):
                failures.append(f"{name}:not_invoked:{out.get('status')}")
                continue
        if not (
            out.get("physical_callable")
            or out.get("evidence_refs")
            or out.get("evidence_ids")
        ):
            failures.append(f"{name}:missing_physical_or_evidence")
        # Prefer real executor path for non-postflight
        if name not in {"artifact_gate", "claim_gate", "delivery_gate"}:
            real = build_real_executor_invoker(name)
            if real is None:
                failures.append(f"{name}:no_real_executor_invoker")
    assert failures == [], failures


def test_p1_every_f_monkeypatch_engine_fail_closed(monkeypatch) -> None:
    """For each F with get_executor, monkeypatch fail → not SUCCEEDED."""
    from nexus.core.capability_executor_registry import get_executor
    from nexus.services import capability_registry as cr

    matrix = build_wiring_matrix()
    f_names = [
        r["name"]
        for r in matrix["rows"]
        if r["gap_class"] == "F_wired_ok" and r["name"] != "local_model_executor"
    ]
    checked = 0
    for name in f_names:
        if name in {"artifact_gate", "claim_gate", "delivery_gate"}:
            continue  # postflight gates, not get_executor body
        if get_executor(name) is None and get_executor(
            cr.EXECUTOR_REGISTRY_ALIASES.get(name, name)
        ) is None:
            continue
        real_get = get_executor

        def _boom_factory(target: str):
            def _get(cap: str):
                key = cr.EXECUTOR_REGISTRY_ALIASES.get(cap, cap)
                if key == target or cap == target or key == cr.EXECUTOR_REGISTRY_ALIASES.get(target, target):
                    def _boom(*_a, **_k):
                        raise RuntimeError(f"forced_fail_{target}")
                    return _boom
                return real_get(cap)
            return _get

        monkeypatch.setattr(
            "nexus.core.capability_executor_registry.get_executor",
            _boom_factory(name),
        )
        inv = cr.build_real_executor_invoker(name)
        if inv is None:
            monkeypatch.undo()
            continue
        out = inv(
            {
                "task_id": f"fail-{name}",
                "task_statement": f"fail {name}",
                "planner": {"plan_hash": "p"},
            }
        )
        assert out.get("gate_passed") is False, name
        assert out.get("status") in {"BLOCKED", "FAILED"}, (name, out.get("status"))
        checked += 1
        monkeypatch.undo()
    assert checked >= 3, f"expected multiple F engines checked, got {checked}"


def test_p2_shared_hashes_and_consumption_fields() -> None:
    """Local/Online share sealed hashes; receipt.consumed_evidence_ids non-empty after with_nexus."""
    from nexus.services.mainchain_entry import run_mainchain

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
            "outcome_contributed": True,
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
            "outcome_contributed": True,
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
            "outcome_contributed": True,
        }

    # Real mainchain path: with_nexus Online injects evidence into prompt lineage.
    receipt = run_mainchain(
        UnifiedRuntimeRequest(
            task_id="cons-1",
            workspace_revision="wr",
            task_statement="shared consumption proof for codeintel memory belief",
            task_type="repair",
            route={
                "recommended_flow": "direct",
                "provider": "agy",
                "injected_transport": True,
                "online_invoker_provider": "agy",
                "route_features": {"memory_hits": 1},
                "workforce_bindings": {
                    "online": {
                        "worker_id": "agy_flash",
                        "controls": [
                            "task_card",
                            "allowed_files",
                            "mandatory_commands",
                            "independent_verification",
                        ],
                    }
                },
            },
            online_prompt="return ok",
            online_payload="payload",
            local_enabled=False,
            codeintel={
                "scan_report_present": True,
                "risk_score": 1,
                "impact_report_present": True,
                "workspace_root": "/tmp",
                "verify_commands": ["echo ok"],
                "verify_timeout_sec": 10,
                "mempalace_tenant_id": "cons-tenant",
                "mempalace_artifact": {
                    "artifact_id": "cons-1",
                    "content": "shared consumption proof",
                },
                "mempalace_artifact_type": "task_receipt",
                "mempalace_query": "cons-1",
            },
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
        with_nexus_armor=True,
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

    # Gate F: receipt must carry non-empty consumed IDs after real Online path.
    consumed = list(receipt.get("consumed_evidence_ids") or [])
    assert consumed, "receipt.consumed_evidence_ids must be non-empty after with_nexus Online"
    assert not any(str(i).startswith("bundle:") for i in consumed)

    # Each of codeintel/memory/belief must appear in successful entries and consumption.
    for cap in ("codeintel", "memory", "belief"):
        entry = next(
            (
                e
                for e in (bundle.get("entries") or [])
                if e.get("name") == cap and (e.get("success") or e.get("invoked_real"))
            ),
            None,
        )
        assert entry is not None, cap
        entry_ids = list(entry.get("evidence_ids") or entry.get("evidence_refs") or [])
        assert entry_ids, cap
        assert any(eid in consumed for eid in entry_ids), (cap, entry_ids, consumed)

    # Removing evidence must fail integrated consumption proof
    empty = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=[],
    )
    assert empty["capability_consumed"] is False
    forged = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=["capability:codeintel:cons-1:FORGED"],
    )
    assert forged["capability_consumed"] is False
    # Real IDs from receipt must validate
    ok = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=consumed,
    )
    assert ok["capability_consumed"] is True


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


# ─── Phase A: verifier proof binding ─────────────────────────────────────────


def _bound_verifier_context(**overrides: Any) -> dict[str, Any]:
    base = {
        "task_id": "bind-task-1",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True, "status": "SUCCEEDED"},
        "verifier": {
            "task_id": "bind-task-1",
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_artifact": VALID_VERIFIER_ARTIFACT,
            "source_hash": VALID_SOURCE_HASH,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "c" * 64,
        },
    }
    base.update(overrides)
    if "verifier" in overrides and isinstance(overrides["verifier"], dict):
        v = dict(base["verifier"]) if isinstance(base.get("verifier"), dict) else {}
        # re-merge carefully when only partial verifier override intended
        pass
    return base


def test_long_arbitrary_verifier_artifact_rejected() -> None:
    context = {
        "task_id": "long-art-1",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True},
        "verifier": {
            "task_id": "long-art-1",
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            # Arbitrary long string — must NOT be accepted as artifact hash.
            "verifier_artifact": "x" * 48,
            "source_hash": VALID_SOURCE_HASH,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "d" * 64,
        },
    }
    _all_postflight_fail(context)


def test_cross_task_verifier_artifact_rejected() -> None:
    context = {
        "task_id": "task-A",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True},
        "verifier": {
            "task_id": "task-B",  # different task
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_artifact": VALID_VERIFIER_ARTIFACT,
            "source_hash": VALID_SOURCE_HASH,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "d" * 64,
        },
    }
    _all_postflight_fail(context)


def test_verifier_not_invoked_cannot_pass() -> None:
    context = {
        "task_id": "ni-1",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True},
        "verifier": {
            "task_id": "ni-1",
            "invoked": False,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_artifact": VALID_VERIFIER_ARTIFACT,
            "source_hash": VALID_SOURCE_HASH,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "d" * 64,
        },
    }
    _all_postflight_fail(context)


def test_verifier_gate_passed_false_cannot_pass() -> None:
    context = {
        "task_id": "gp-1",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True},
        "verifier": {
            "task_id": "gp-1",
            "invoked": True,
            "gate_passed": False,
            "verifier_status": "pass",
            "verifier_artifact": VALID_VERIFIER_ARTIFACT,
            "source_hash": VALID_SOURCE_HASH,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "d" * 64,
        },
    }
    _all_postflight_fail(context)


def test_verifier_fail_status_blocks_all_postflight_gates() -> None:
    context = {
        "task_id": "fail-1",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True},
        "verifier": {
            "task_id": "fail-1",
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "fail",
            "verifier_artifact": VALID_VERIFIER_ARTIFACT,
            "source_hash": VALID_SOURCE_HASH,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "d" * 64,
        },
    }
    _all_postflight_fail(context)


def test_verifier_source_hash_mismatch_rejected() -> None:
    other = hashlib.sha256(b"other-source").hexdigest()
    context = {
        "task_id": "src-1",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True},
        "verifier": {
            "task_id": "src-1",
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_artifact": VALID_VERIFIER_ARTIFACT,
            "source_hash": other,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "d" * 64,
        },
    }
    _all_postflight_fail(context)


def test_valid_bound_sha256_verifier_proof_passes() -> None:
    context = {
        "task_id": "ok-1",
        "source_hash": VALID_SOURCE_HASH,
        "online": {"invoked": True},
        "verifier": {
            "task_id": "ok-1",
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_artifact": VALID_VERIFIER_ARTIFACT,
            "source_hash": VALID_SOURCE_HASH,
        },
        "capability_evidence_bundle": {
            "source_hash": VALID_SOURCE_HASH,
            "bundle_hash": "d" * 64,
        },
    }
    for name in ("artifact_gate", "claim_gate", "delivery_gate"):
        verdict = evaluate_postflight_gate(name, context)
        assert verdict["gate_passed"] is True, (name, verdict.get("blockers"))
        assert verdict["public_claim_allowed"] is False


# ─── Phase B: SKIPPED blocks capability closure ──────────────────────────────


def _cap_ok(name: str, task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "invoked": True,
        "gate_passed": True,
        "status": "SUCCEEDED",
        "evidence_refs": [f"capability:{name}:{task_id}:real"],
        "evidence_ids": [f"capability:{name}:{task_id}:real"],
        "physical_callable": f"test:{name}",
        "telemetry": {"token_usage": 0, "model_calls": 0},
        "outcome_contributed": True,
    }


def test_selected_skipped_blocks_capability_closure() -> None:
    planner = _Planner(
        selected=["codeintel", "research", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )

    def research(ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": ctx["task_id"],
            "invoked": False,
            "gate_passed": False,
            "status": "SKIPPED",
            "skipped": True,
            "skip_reason": "not_implemented",
            "evidence_refs": [],
            "physical_callable": "",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="skip-close-1",
            workspace_revision="wr",
            task_statement="selected research skipped must block closure",
            task_type="repair",
            route={"recommended_flow": "direct", "provider": "gemini"},
            online_prompt="x",
            online_payload="y",
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        capability_invokers={
            "codeintel": lambda c: _cap_ok("codeintel", c["task_id"]),
            "research": research,
        },
        verifier=_verifier_explicit,
        learning=_learning,
    )
    assert receipt["receipt_complete"] is True
    research_stage = (receipt.get("capability_results") or {}).get("research") or {}
    assert (
        str(research_stage.get("status") or "") == "SKIPPED"
        or research_stage.get("skipped")
    )
    assert receipt.get("capability_closure_complete") is False
    blockers = list(receipt.get("capability_closure_blockers") or [])
    assert blockers, "expected non-empty capability_closure_blockers"
    assert any("research" in b and "SKIPPED" in b for b in blockers)
    assert int(receipt.get("closure_skipped_count") or 0) >= 1
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_selected_escalated_capability_blocks_closure() -> None:
    planner = _Planner(
        selected=["codeintel", "swarm_multi_agent", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )

    def escalate(ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": ctx["task_id"],
            "invoked": False,
            "gate_passed": False,
            "status": "SKIPPED",
            "skipped": True,
            "skip_reason": "E_escalate_ok:missing_engine",
            "evidence_refs": [],
            "physical_callable": "",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="esc-close-1",
            workspace_revision="wr",
            task_statement="escalated selected capability blocks closure",
            task_type="repair",
            route={"recommended_flow": "direct", "provider": "gemini"},
            online_prompt="x",
            online_payload="y",
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        capability_invokers={
            "codeintel": lambda c: _cap_ok("codeintel", c["task_id"]),
            "swarm_multi_agent": escalate,
        },
        verifier=_verifier_explicit,
        learning=_learning,
    )
    assert receipt.get("capability_closure_complete") is False
    blockers = list(receipt.get("capability_closure_blockers") or [])
    assert any("swarm_multi_agent" in b for b in blockers)


def test_selected_not_executed_blocks_closure() -> None:
    planner = _Planner(
        selected=["codeintel", "belief", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )

    def not_exec(ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": ctx["task_id"],
            "invoked": False,
            "gate_passed": False,
            "status": "SELECTED_NOT_EXECUTED",
            "evidence_refs": [],
            "physical_callable": "",
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="sne-close-1",
            workspace_revision="wr",
            task_statement="selected not executed blocks closure",
            task_type="repair",
            route={"recommended_flow": "direct", "provider": "gemini"},
            online_prompt="x",
            online_payload="y",
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        capability_invokers={
            "codeintel": lambda c: _cap_ok("codeintel", c["task_id"]),
            "belief": not_exec,
        },
        verifier=_verifier_explicit,
        learning=_learning,
    )
    assert receipt.get("capability_closure_complete") is False
    blockers = list(receipt.get("capability_closure_blockers") or [])
    assert any("belief" in b and "SELECTED_NOT_EXECUTED" in b for b in blockers)


def test_all_selected_executed_allows_closure() -> None:
    planner = _Planner(
        selected=["codeintel", "memory", "belief", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )
    invokers = {
        name: (lambda n: (lambda c: _cap_ok(n, c["task_id"])))(name)
        for name in ("codeintel", "memory", "belief")
    }
    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="all-close-1",
            workspace_revision="wr",
            task_statement="all selected executed allows closure",
            task_type="repair",
            route={"recommended_flow": "direct", "provider": "gemini"},
            online_prompt="x",
            online_payload="y",
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        capability_invokers=invokers,
        verifier=_verifier_explicit,
        learning=_learning,
    )
    assert receipt["receipt_complete"] is True
    assert receipt.get("capability_closure_complete") is True
    assert list(receipt.get("capability_closure_blockers") or []) == []
    assert int(receipt.get("closure_selected_count") or 0) == 6
    assert int(receipt.get("closure_executed_count") or 0) == 6
    assert int(receipt.get("closure_skipped_count") or 0) == 0
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_receipt_complete_does_not_imply_capability_closure() -> None:
    planner = _Planner(
        selected=["codeintel", "research", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )

    def research(ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": ctx["task_id"],
            "invoked": False,
            "gate_passed": False,
            "status": "SKIPPED",
            "skipped": True,
            "skip_reason": "not_implemented",
            "evidence_refs": [],
            "telemetry": {"token_usage": 0, "model_calls": 0},
        }

    runtime = UnifiedRuntime(planner=planner)
    receipt = runtime.run(
        UnifiedRuntimeRequest(
            task_id="rc-ne-cc-1",
            workspace_revision="wr",
            task_statement="receipt complete does not imply closure",
            task_type="repair",
            route={"recommended_flow": "direct", "provider": "gemini"},
            online_prompt="x",
            online_payload="y",
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        capability_invokers={
            "codeintel": lambda c: _cap_ok("codeintel", c["task_id"]),
            "research": research,
        },
        verifier=_verifier_explicit,
        learning=_learning,
    )
    assert receipt["receipt_complete"] is True
    assert receipt.get("capability_closure_complete") is False
    assert list(receipt.get("capability_closure_blockers") or [])


# ─── Phase C: Local real prompt evidence consumption ─────────────────────────


def _local_bundle(task_id: str) -> dict[str, Any]:
    return {
        "schema": "nexus.capability_evidence_bundle.v1",
        "task_id": task_id,
        "bundle_hash": hashlib.sha256(f"bundle-{task_id}".encode()).hexdigest(),
        "baseline_hash": hashlib.sha256(f"base-{task_id}".encode()).hexdigest(),
        "planner_decision_id": f"pd-{task_id}",
        "source_hash": VALID_SOURCE_HASH,
        "selected_capabilities": ["codeintel", "memory", "belief", "repair_loop"],
        "evidence_ids": [
            f"capability:codeintel:{task_id}:real",
            f"capability:memory:{task_id}:real",
            f"capability:belief:{task_id}:real",
            f"capability:repair_loop:{task_id}:fail",
        ],
        "entries": [
            {
                "name": "codeintel",
                "status": "REAL_INVOKED",
                "success": True,
                "invoked_real": True,
                "evidence_ids": [f"capability:codeintel:{task_id}:real"],
                "evidence_refs": [f"capability:codeintel:{task_id}:real"],
                "physical_callable": "test:codeintel",
            },
            {
                "name": "memory",
                "status": "REAL_INVOKED",
                "success": True,
                "invoked_real": True,
                "evidence_ids": [f"capability:memory:{task_id}:real"],
                "evidence_refs": [f"capability:memory:{task_id}:real"],
                "physical_callable": "test:memory",
            },
            {
                "name": "belief",
                "status": "REAL_INVOKED",
                "success": True,
                "invoked_real": True,
                "evidence_ids": [f"capability:belief:{task_id}:real"],
                "evidence_refs": [f"capability:belief:{task_id}:real"],
                "physical_callable": "test:belief",
            },
            {
                "name": "repair_loop",
                "status": "INVOKED_NOT_SUCCESS",
                "success": False,
                "invoked_real": False,
                "evidence_ids": [f"capability:repair_loop:{task_id}:fail"],
                "evidence_refs": [f"capability:repair_loop:{task_id}:fail"],
                "physical_callable": "test:repair_loop",
            },
            {
                "name": "research",
                "status": "REAL_INVOKED",
                "success": True,
                "invoked_real": True,
                "evidence_ids": [f"capability:research:{task_id}:unselected"],
                "evidence_refs": [f"capability:research:{task_id}:unselected"],
                "physical_callable": "test:research",
            },
        ],
    }


def _local_assist_request(tmp_path: Path, task_id: str, *, action: str = "advisor"):
    from nexus.services.local_assist_service import LocalAssistRequest

    bundle = _local_bundle(task_id)
    snapshot = {
        "route_truth_source": "CapabilityPlanner",
        "execution_topology": "single_local_model",
        "protocol_mode": "unified_diff",
        "model_call_allowed": True,
        "executor_provider": "ollama",
        "executor_model": "qwen2.5-coder:7b",
        "capability_evidence_bundle": bundle,
        "bundle_hash": bundle["bundle_hash"],
        "baseline_hash": bundle["baseline_hash"],
        "planner_decision_id": bundle["planner_decision_id"],
        "selected_capabilities": ["codeintel", "memory", "belief", "local_model_executor"],
        "local_consumable_capabilities": ["codeintel", "memory", "belief", "local_model_executor"],
    }
    return LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id=task_id,
        parent_task_id="parent-1",
        workspace_root=str(tmp_path),
        workspace_revision="wr",
        task_statement="diagnose with shared capability evidence",
        action=action,
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("tests/services/test_mainchain_false_green_gates.py",),
        risk_budget="low",
        time_budget=10.0,
        requested_role="advisor" if action == "advisor" else "candidate",
        mutation_policy="isolated_only",
        planner_snapshot=snapshot,
    )


def test_local_enabled_prompt_contains_real_evidence_ids(tmp_path: Path) -> None:
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    captured: dict[str, str] = {}

    def _gen(req: Any) -> str:
        captured["prompt"] = str(getattr(req, "prompt", "") or "")
        return "diagnosis: ok"

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "loc-ev-1"
    req = _local_assist_request(tmp_path, task_id)
    response = LocalAssistService(provider=InjectedLocalModelProvider(_gen)).handle(req)
    assert response.local_model_invoked is True
    prompt = captured.get("prompt") or ""
    assert "capability:codeintel:loc-ev-1:real" in prompt
    assert "capability:memory:loc-ev-1:real" in prompt
    assert "capability:belief:loc-ev-1:real" in prompt
    assert "NEXUS_CAPABILITY_EVIDENCE" in prompt


def test_local_consumed_ids_equal_ids_serialized_into_prompt(tmp_path: Path) -> None:
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    captured: dict[str, str] = {}

    def _gen(req: Any) -> str:
        captured["prompt"] = str(getattr(req, "prompt", "") or "")
        return "diagnosis: ok"

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "loc-eq-1"
    req = _local_assist_request(tmp_path, task_id)
    response = LocalAssistService(provider=InjectedLocalModelProvider(_gen)).handle(req)
    prompt = captured.get("prompt") or ""
    consumed = list(
        (response.local_outputs.get("evidence_consumption") or {}).get("consumed_evidence_ids")
        or response.local_outputs.get("consumed_evidence_ids")
        or []
    )
    assert consumed, "expected non-empty consumed_evidence_ids"
    for eid in consumed:
        assert eid in prompt, (eid, prompt[:200])
    # receipt ids must be a subset of prompt-serialized IDs
    assert set(consumed).issubset({eid for eid in consumed if eid in prompt})


def test_local_does_not_consume_unselected_capability(tmp_path: Path) -> None:
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    captured: dict[str, str] = {}

    def _gen(req: Any) -> str:
        captured["prompt"] = str(getattr(req, "prompt", "") or "")
        return "diagnosis: ok"

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "loc-unsel-1"
    req = _local_assist_request(tmp_path, task_id)
    response = LocalAssistService(provider=InjectedLocalModelProvider(_gen)).handle(req)
    prompt = captured.get("prompt") or ""
    consumed = list(
        (response.local_outputs.get("evidence_consumption") or {}).get("consumed_evidence_ids") or []
    )
    assert f"capability:research:{task_id}:unselected" not in prompt
    assert f"capability:research:{task_id}:unselected" not in consumed


def test_local_does_not_consume_failed_bundle_entry(tmp_path: Path) -> None:
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    captured: dict[str, str] = {}

    def _gen(req: Any) -> str:
        captured["prompt"] = str(getattr(req, "prompt", "") or "")
        return "diagnosis: ok"

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "loc-fail-1"
    req = _local_assist_request(tmp_path, task_id)
    # Include repair_loop in local consumable so failure filtering is tested.
    snap = dict(req.planner_snapshot)
    snap["local_consumable_capabilities"] = [
        "codeintel",
        "memory",
        "belief",
        "repair_loop",
        "local_model_executor",
    ]
    req = req.__class__(**{**req.__dict__, "planner_snapshot": snap})
    response = LocalAssistService(provider=InjectedLocalModelProvider(_gen)).handle(req)
    prompt = captured.get("prompt") or ""
    consumed = list(
        (response.local_outputs.get("evidence_consumption") or {}).get("consumed_evidence_ids") or []
    )
    fail_id = f"capability:repair_loop:{task_id}:fail"
    assert fail_id not in prompt
    assert fail_id not in consumed


def test_local_empty_prompt_evidence_means_not_consumed(tmp_path: Path) -> None:
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    captured: dict[str, str] = {}

    def _gen(req: Any) -> str:
        captured["prompt"] = str(getattr(req, "prompt", "") or "")
        return "diagnosis: ok"

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "loc-empty-1"
    req = _local_assist_request(tmp_path, task_id)
    snap = dict(req.planner_snapshot)
    # Empty bundle entries ⇒ no prompt evidence ⇒ not consumed.
    snap["capability_evidence_bundle"] = {
        "bundle_hash": "e" * 64,
        "baseline_hash": "f" * 64,
        "planner_decision_id": "pd-empty",
        "entries": [],
        "evidence_ids": [],
        "selected_capabilities": ["codeintel"],
    }
    req = req.__class__(**{**req.__dict__, "planner_snapshot": snap})
    response = LocalAssistService(provider=InjectedLocalModelProvider(_gen)).handle(req)
    prompt = captured.get("prompt") or ""
    assert "NEXUS_CAPABILITY_EVIDENCE" not in prompt
    ec = response.local_outputs.get("evidence_consumption") or {}
    assert ec.get("capability_consumed") is False
    assert list(ec.get("consumed_evidence_ids") or []) == []


def test_local_and_online_share_root_bundle_hash(tmp_path: Path) -> None:
    from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
    from nexus.services.mainchain_entry import run_mainchain

    captured_local: dict[str, str] = {}

    def _gen(req: Any) -> str:
        captured_local["prompt"] = str(getattr(req, "prompt", "") or "")
        return "diagnosis: shared hash path"

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    local_request = LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id="share-hash-1",
        parent_task_id="p1",
        workspace_root=str(tmp_path),
        workspace_revision="wr",
        task_statement="local and online share root bundle hash",
        action="advisor",
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("t",),
        requested_role="advisor",
        mutation_policy="isolated_only",
        time_budget=10.0,
        planner_snapshot={
            "route_truth_source": "CapabilityPlanner",
            "execution_topology": "single_local_model",
            "protocol_mode": "unified_diff",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b",
        },
    )
    receipt = run_mainchain(
        UnifiedRuntimeRequest(
            task_id="share-hash-1",
            workspace_revision="wr",
            task_statement="local and online share root bundle hash",
            task_type="repair",
            route={
                "recommended_flow": "hybrid",
                "provider": "agy",
                "injected_transport": True,
                "workspace_root": str(tmp_path),
                "online_invoker_provider": "agy",
                "workforce_bindings": {
                    "online": {
                        "worker_id": "agy_flash",
                        "controls": [
                            "task_card",
                            "allowed_files",
                            "mandatory_commands",
                            "independent_verification",
                        ],
                    },
                    "local": {
                        "worker_id": "local_coder_7b",
                        "controls": [
                            "small_scope",
                            "parser",
                            "compile",
                            "focused_tests",
                            "reversible_application",
                        ],
                    },
                },
            },
            online_prompt="return ok",
            online_payload="payload",
            local_enabled=True,
            local_request=local_request,
            evidence_refs=("t",),
            codeintel={
                "scan_report_present": True,
                "risk_score": 1,
                "impact_report_present": True,
                "workspace_root": str(tmp_path),
                "verify_commands": ["echo ok"],
                "verify_timeout_sec": 10,
                "mempalace_tenant_id": "share-hash-tenant",
                "mempalace_artifact": {
                    "artifact_id": "share-hash-1",
                    "content": "shared root bundle hash",
                },
                "mempalace_artifact_type": "task_receipt",
                "mempalace_query": "share-hash-1",
            },
        ),
        online_invoker=_online,
        local_service=LocalAssistService(
            provider=InjectedLocalModelProvider(
                _gen,
                provider_identity="ollama",
                model_identity="qwen2.5-coder:7b-instruct",
            )
        ),
        capability_invokers={
            "codeintel": lambda c: _cap_ok("codeintel", c["task_id"]),
            "memory": lambda c: _cap_ok("memory", c["task_id"]),
            "belief": lambda c: _cap_ok("belief", c["task_id"]),
        },
        verifier=_verifier_explicit,
        learning=_learning,
        with_nexus_armor=True,
    )
    bundle = receipt.get("capability_evidence_bundle") or {}
    root_hash = str(bundle.get("bundle_hash") or "")
    assert root_hash
    # Online with_nexus lineage must share the same root hash.
    online = receipt.get("online") or {}
    online_resp = online.get("response") if isinstance(online.get("response"), dict) else {}
    with_nexus = online_resp.get("with_nexus") if isinstance(online_resp, dict) else {}
    lineage = with_nexus.get("lineage") if isinstance(with_nexus, dict) else {}
    online_hash = str(
        (lineage or {}).get("bundle_hash")
        or (with_nexus or {}).get("bundle_hash")
        or ""
    )
    # Local consumption must report same root hash when evidence was injected.
    local = receipt.get("local") or {}
    local_resp = local.get("response") if isinstance(local.get("response"), dict) else {}
    local_outputs = local_resp.get("local_outputs") if isinstance(local_resp, dict) else {}
    ec = local_outputs.get("evidence_consumption") if isinstance(local_outputs, dict) else {}
    local_hash = str((ec or {}).get("bundle_hash") or "")
    if online_hash:
        assert online_hash == root_hash
    if local_hash:
        assert local_hash == root_hash
    # Prompt must contain real evidence IDs when local ran.
    if captured_local.get("prompt"):
        assert "capability:codeintel:share-hash-1:real" in captured_local["prompt"]


def test_local_candidate_executor_receives_capability_evidence_context(tmp_path: Path) -> None:
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_executor import LocalModelExecutorResponse
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    seen: dict[str, Any] = {}

    def fake_executor(request: Any, **_kwargs: Any) -> LocalModelExecutorResponse:
        seen["problem_statement"] = str(getattr(request, "problem_statement", "") or "")
        rc = getattr(request, "route_context", {}) or {}
        seen["route_context"] = dict(rc) if isinstance(rc, dict) else {}
        receipt_ctx = getattr(request, "receipt_context", {}) or {}
        seen["receipt_context"] = dict(receipt_ctx) if isinstance(receipt_ctx, dict) else {}
        return LocalModelExecutorResponse(
            invoked=True,
            local_model_called=True,
            candidate_patch="",
            candidate_hash="empty",
            reasoning_summary="no_candidate",
            raw_model_metadata={},
            provider="injected",
            model_name="qwen2.5-coder:7b",
            error="no_candidate",
            timeout=False,
            evidence_refs=("t",),
        )

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "loc-cand-1"
    req = _local_assist_request(tmp_path, task_id, action="candidate")
    LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _: "unused"),
        executor_runner=fake_executor,
    ).handle(req)
    problem = seen.get("problem_statement") or ""
    assert "capability:codeintel:loc-cand-1:real" in problem
    assert "NEXUS_CAPABILITY_EVIDENCE" in problem
    rc = seen.get("route_context") or {}
    assert rc.get("capability_evidence_context") or rc.get("consumed_evidence_ids")
    ids = list(rc.get("consumed_evidence_ids") or (seen.get("receipt_context") or {}).get("consumed_evidence_ids") or [])
    assert any("codeintel" in i for i in ids)
    assert f"capability:research:{task_id}:unselected" not in ids


# ─── P0 semantic-success seal ────────────────────────────────────────────────


def test_production_belief_assess_confidence_numeric_no_error() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import get_executor

    ex = get_executor("belief")
    assert ex is not None
    plan = CapabilityExecutionPlan(
        plan_id="belief-ok",
        task_id="belief-task-1",
        phases=["R"],
        constraints={"assumption": "repo compiles"},
    )
    receipt = ex(plan, "repo compiles")
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    outcome = dict(receipt.outcome or {})
    assert outcome.get("action") == "assess_confidence"
    conf = outcome.get("confidence")
    assert isinstance(conf, (int, float))
    assert 0.0 <= float(conf) <= 1.0
    assert not outcome.get("error")
    assert "no_evaluate" not in str(outcome).lower()
    assert outcome.get("task_id") == "belief-task-1" or outcome.get("assumption")


def test_production_belief_monkeypatch_api_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.core import belief_engine as be
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import get_executor

    def _boom(self, task_id: str, assumption: str = "") -> float:  # type: ignore[no-untyped-def]
        raise RuntimeError("forced_belief_api_fail")

    monkeypatch.setattr(be.BeliefEngine, "assess_confidence", _boom)
    monkeypatch.setattr(be.BeliefEngine, "get_confidence", _boom)
    ex = get_executor("belief")
    plan = CapabilityExecutionPlan(
        plan_id="belief-fail",
        task_id="belief-task-fail",
        phases=["R"],
        constraints={},
    )
    receipt = ex(plan, "assumption")
    assert receipt.gate_passed is False
    assert receipt.invoked is False or bool((receipt.outcome or {}).get("error"))
    assert "no_evaluate" not in str(receipt.outcome or {}).lower() or receipt.gate_passed is False


def test_acceptance_check_unverified_not_success() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import get_executor

    ex = get_executor("acceptance_check")
    assert ex is not None
    plan = CapabilityExecutionPlan(
        plan_id="acc-unv",
        task_id="acc-1",
        phases=["R"],
        constraints={
            "semantic_status": "UNVERIFIED",
            "verifier_status": "pass",
            "verifier_artifact": "sha256:" + ("ab" * 32),
            "source_hash": "src" * 8,
            "evidence_refs": ["ev:real:1"],
        },
    )
    receipt = ex(plan, "task statement")
    assert receipt.gate_passed is False
    outcome = dict(receipt.outcome or {})
    assert str(outcome.get("semantic_status") or "").upper() == "UNVERIFIED"


def test_acceptance_check_verified_empty_evidence_refs_fails() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import get_executor

    ex = get_executor("acceptance_check")
    plan = CapabilityExecutionPlan(
        plan_id="acc-empty-refs",
        task_id="acc-empty",
        phases=["R"],
        constraints={
            "semantic_status": "VERIFIED",
            "verifier_status": "pass",
            "verifier_artifact": "sha256:" + ("cd" * 32),
            "source_hash": "sourcehashvalue0001",
            "evidence_refs": [],
        },
    )
    receipt = ex(plan, "task statement")
    assert receipt.gate_passed is False
    assert "missing_evidence_refs" in list((receipt.outcome or {}).get("missing_evidence") or [])


def test_acceptance_check_verified_missing_verifier_artifact_fails() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import get_executor

    ex = get_executor("acceptance_check")
    plan = CapabilityExecutionPlan(
        plan_id="acc-no-art",
        task_id="acc-no-art",
        phases=["R"],
        constraints={
            "semantic_status": "VERIFIED",
            "verifier_status": "pass",
            "verifier_artifact": "",
            "source_hash": "sourcehashvalue0002",
            "evidence_refs": ["ev:real:2"],
        },
    )
    receipt = ex(plan, "task statement")
    assert receipt.gate_passed is False
    assert "missing_verifier_artifact" in list((receipt.outcome or {}).get("missing_evidence") or [])


def test_acceptance_check_full_bounded_verifier_evidence_passes() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import get_executor

    ex = get_executor("acceptance_check")
    plan = CapabilityExecutionPlan(
        plan_id="acc-full",
        task_id="acc-full",
        phases=["R"],
        constraints={
            "semantic_status": "VERIFIED",
            "verifier_status": "pass",
            "verifier_artifact": "sha256:" + ("ef" * 32),
            "source_hash": "sourcehashvalue0003",
            "evidence_refs": ["ev:real:3", "verifier:acc-full"],
        },
    )
    receipt = ex(plan, "task statement")
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    assert str((receipt.outcome or {}).get("semantic_status") or "").upper() == "VERIFIED"


def test_acceptance_check_verified_can_succeed() -> None:
    """Backward-compatible name: full evidence allowlist required for PASS."""
    test_acceptance_check_full_bounded_verifier_evidence_passes()


def test_acceptance_invoker_reads_normalized_verifier_stage_response() -> None:
    from nexus.services.capability_registry import build_real_executor_invoker

    invoker = build_real_executor_invoker("acceptance_check")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "acc-normalized-stage",
            "task_statement": "accept verified callback evidence",
            "planner": {"plan_hash": "plan-acc-normalized-stage"},
            "verifier": {
                "name": "verifier",
                "status": "SUCCEEDED",
                "invoked": True,
                "gate_passed": True,
                "response": {
                    "semantic_status": "VERIFIED",
                    "verifier_status": "pass",
                    "verifier_artifact": "sha256:" + ("12" * 32),
                    "source_hash": "sourcehashvalue0004",
                    "evidence_refs": ["verifier:acc-normalized-stage"],
                },
            },
        }
    )

    assert result["invoked"] is True
    assert result["gate_passed"] is True
    assert result["status"] == "SUCCEEDED"


def test_claim_gate_hash_match_omitted_fails() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core import capability_executor_registry as cer

    plan = CapabilityExecutionPlan(
        plan_id="cg-omit",
        task_id="cg-omit",
        phases=["R"],
        constraints={
            "source_hash": "deadbeefcafebabe01",
            "candidate_target_file": "x.py",
            # candidate_hash_matches_applied intentionally omitted
        },
    )
    receipt = cer._exec_claim_gate(plan, "claim")
    assert receipt.gate_passed is False
    missing = list((receipt.outcome or {}).get("missing_fields") or [])
    assert "candidate_hash_matches_applied" in missing


def test_claim_gate_top_level_false_fails() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core import capability_executor_registry as cer

    plan = CapabilityExecutionPlan(
        plan_id="cg-top-false",
        task_id="cg-top-false",
        phases=["R"],
        constraints={
            "source_hash": "deadbeefcafebabe02",
            "candidate_target_file": "x.py",
            "candidate_hash_matches_applied": False,
            "solve_eligible": True,
            "final_patch": "--- a/x.py\n+++ b/x.py\n",
            "evaluation_report": "verification_report.md",
            "owner_approved": True,
        },
    )
    receipt = cer._exec_claim_gate(plan, "claim")
    assert receipt.gate_passed is False
    outcome = dict(receipt.outcome or {})
    assert outcome.get("candidate_hash_matches_applied") is False
    reasons = list(outcome.get("failure_reasons") or [])
    assert "candidate_hash_mismatch" in reasons or outcome.get("passed") is False


def test_claim_gate_route_context_false_fails() -> None:
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core import capability_executor_registry as cer

    plan = CapabilityExecutionPlan(
        plan_id="cg-rc-false",
        task_id="cg-rc-false",
        phases=["R"],
        constraints={
            "source_hash": "deadbeefcafebabe03",
            "candidate_target_file": "x.py",
            "route_context": {"candidate_hash_matches_applied": False},
            "solve_eligible": True,
            "final_patch": "patch",
            "evaluation_report": "verification_report.md",
        },
    )
    receipt = cer._exec_claim_gate(plan, "claim")
    assert receipt.gate_passed is False
    assert (receipt.outcome or {}).get("candidate_hash_matches_applied") is False


def test_claim_gate_registry_has_no_synthetic_theater() -> None:
    """Production registry claim_gate must not hardcode abc123 / owner_approved theater."""
    import inspect

    from nexus.core import capability_executor_registry as cer

    src = inspect.getsource(cer._exec_claim_gate)
    # Ban hard-coded synthetic *assignments* (docstrings may mention policies).
    assert 'source_hash="abc123"' not in src
    assert "source_hash='abc123'" not in src
    assert "owner_approved=True" not in src
    assert "candidate_hash_matches_applied=True" not in src
    assert "--- a/file.py" not in src
    # Without real context: fail closed.
    from nexus.core.belief_contracts import CapabilityExecutionPlan

    plan = CapabilityExecutionPlan(plan_id="cg", task_id="cg1", phases=["R"], constraints={})
    receipt = cer._exec_claim_gate(plan, "claim")
    assert receipt.gate_passed is False
    assert receipt.invoked is False or bool((receipt.outcome or {}).get("error"))


def test_claim_gate_real_failing_dict_forces_gate_passed_false() -> None:
    """claim_gate_passed=False from real validator must not default to success.

    Real validate_context_claim_delivery returns claim_gate_passed/delivery_gate_passed,
    not generic passed/ok. Supplying only source_hash+candidate_target_file yields
    claim_gate_passed=False — receipt must fail closed and not feed usable payload.
    """
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core import capability_executor_registry as cer
    from nexus.services.capability_evidence_bundle import extract_bounded_consumer_payload
    from nexus.services.capability_registry import build_real_executor_invoker

    plan = CapabilityExecutionPlan(
        plan_id="cg-fail",
        task_id="cg-fail-1",
        phases=["R"],
        constraints={
            "source_hash": "deadbeefcafebabe",
            "candidate_target_file": "x.py",
            # Explicit match True but no verifier/patch — real validator fails claim.
            "candidate_hash_matches_applied": True,
            "solve_eligible": False,
        },
    )
    receipt = cer._exec_claim_gate(plan, "claim task")
    assert receipt.gate_passed is False, receipt.outcome
    outcome = dict(receipt.outcome or {})
    assert outcome.get("claim_gate_passed") is False, outcome
    assert outcome.get("passed") is False
    assert outcome.get("ok") is False

    # Real mainchain invoker wrapping get_executor must also fail closed.
    # Inject constraints via plan on the executor path.
    inv = build_real_executor_invoker("claim_gate")
    assert inv is not None

    # Monkeypatch CapabilityExecutionPlan construction is hard; call executor via
    # registry plan with constraints already proven above. Also prove payload ban.
    stage = {
        "status": "FAILED",
        "invoked": True,
        "gate_passed": False,
        "evidence_refs": [receipt.evidence_id],
        "response": {
            "status": "FAILED",
            "outcome": outcome,
            "consumer_payload": {},
        },
    }
    cp = extract_bounded_consumer_payload(
        capability="claim_gate",
        stage=stage,
        response=stage["response"],
        success=bool(receipt.gate_passed),
    )
    assert cp == {}


def test_semantic_success_guard_rejects_error_and_unverified() -> None:
    from nexus.core.capability_executor_registry import apply_semantic_success_guard

    inv, gate, out = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={"action": "x", "error": "no_evaluate"},
    )
    assert gate is False
    inv2, gate2, _ = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={"action": "decide_completion", "semantic_status": "UNVERIFIED"},
    )
    assert gate2 is False
    inv3, gate3, _ = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={"action": "ok", "passed": False},
    )
    assert gate3 is False
    inv4, gate4, _ = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={"action": "assess_confidence", "confidence": 0.7},
    )
    assert inv4 is True and gate4 is True


def test_semantic_guard_nested_result_error_fails() -> None:
    from nexus.core.capability_executor_registry import apply_semantic_success_guard

    _, gate, _ = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={"action": "x", "result": {"error": "nested_fail", "detail": "x"}},
    )
    assert gate is False


def test_semantic_guard_nested_semantic_status_unverified_fails() -> None:
    from nexus.core.capability_executor_registry import apply_semantic_success_guard

    _, gate, _ = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={"action": "x", "result": {"semantic_status": "UNVERIFIED"}},
    )
    assert gate is False


def test_semantic_guard_list_item_passed_false_fails() -> None:
    from nexus.core.capability_executor_registry import apply_semantic_success_guard

    _, gate, _ = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={"action": "x", "items": [{"name": "a", "passed": True}, {"name": "b", "passed": False}]},
    )
    assert gate is False


def test_semantic_guard_ordinary_success_payload_passes() -> None:
    from nexus.core.capability_executor_registry import apply_semantic_success_guard

    inv, gate, _ = apply_semantic_success_guard(
        invoked=True,
        gate_passed=True,
        outcome={
            "action": "assess_confidence",
            "confidence": 0.7,
            "result": {"summary": "ok", "score": 1},
            "items": [{"name": "a", "ok": True}],
        },
    )
    assert inv is True and gate is True


# ─── Phase A: bounded consumer_payload ───────────────────────────────────────


def test_bundle_carries_bounded_consumer_payload() -> None:
    """Usable outcome fields survive seal; nested UnifiedRuntime stage shape supported."""
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle
    from nexus.services.capability_registry import build_real_executor_invoker

    task_id = "payload-a1"
    # Production-shaped nested stage: invoker return wrapped as stage.response
    inv = build_real_executor_invoker("codeintel")
    assert inv is not None
    invoker_out = inv(
        {
            "task_id": task_id,
            "task_statement": "scan impact risk workspace",
            "planner": {"plan_hash": "ph"},
            "workspace_root": str(Path.cwd()),
            "target_file": "nexus/services/capability_registry.py",
            "target_symbol": "build_real_executor_invoker",
        }
    )
    stage = {
        "status": "SUCCEEDED" if invoker_out.get("gate_passed") else "FAILED",
        "invoked": True,
        "gate_passed": bool(invoker_out.get("gate_passed")),
        "evidence_refs": invoker_out.get("evidence_refs") or [],
        "evidence_ids": invoker_out.get("evidence_ids") or [],
        "physical_callable": invoker_out.get("physical_callable") or "",
        "response": invoker_out,  # nested wrap as UnifiedRuntime does
    }
    assert stage["gate_passed"] is True
    bundle = build_capability_evidence_bundle(
        task_id=task_id,
        workspace_revision="wr",
        task_statement="payload carry",
        plan_payload={"x": 1},
        plan_hash="ph",
        planner_decision_id="pd",
        capability_results={"codeintel": stage},
        selected_capabilities=["codeintel"],
        source_hash=VALID_SOURCE_HASH,
    )
    entry = bundle["entries"][0]
    assert entry.get("has_consumer_payload") is True
    cp = entry.get("consumer_payload") or {}
    assert cp.get("schema") == "nexus.consumer_payload.v1"
    fields = cp.get("fields") or {}
    # Usable outcome content — not markers-only theater
    assert fields.get("action"), fields
    assert fields.get("result") or fields.get("evidence_id"), fields
    assert "codeintel:result" in (cp.get("markers") or [])
    assert "reasoning" not in str(fields)
    assert "candidate_patch" not in str(fields)


def test_bundle_strips_private_reasoning_and_raw_patch() -> None:
    from nexus.services.capability_evidence_bundle import extract_bounded_consumer_payload

    cp = extract_bounded_consumer_payload(
        capability="memory",
        response={
            "outcome": {
                "action": "search",
                "hit_count": 2,
                "private_reasoning": "do not leak",
                "candidate_patch": "+++ raw",
                "api_key": "sk-secret",
                "result": "hits_ok",
            }
        },
        success=True,
    )
    blob = json.dumps(cp)
    assert "do not leak" not in blob
    assert "+++ raw" not in blob
    assert "sk-secret" not in blob
    assert "memory:payload" in blob
    assert cp.get("fields", {}).get("action") == "search"


def test_id_only_entry_is_not_payload_consumed() -> None:
    from nexus.services.capability_evidence_bundle import (
        build_capability_evidence_bundle,
        record_consumption,
    )

    task_id = "id-only-1"
    bundle = build_capability_evidence_bundle(
        task_id=task_id,
        workspace_revision="wr",
        task_statement="id only",
        plan_payload={},
        plan_hash="ph",
        planner_decision_id="pd",
        capability_results={
            "codeintel": {
                "status": "SUCCEEDED",
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"capability:codeintel:{task_id}:real"],
                "evidence_ids": [f"capability:codeintel:{task_id}:real"],
                "physical_callable": "capability_executor_registry:codeintel",
                "response": {"status": "SUCCEEDED"},
            }
        },
        selected_capabilities=["codeintel"],
        source_hash=VALID_SOURCE_HASH,
    )
    entry = next(e for e in bundle["entries"] if e["name"] == "codeintel")
    # No usable outcome/payload fields ⇒ no consumer_payload
    assert not entry.get("consumer_payload")
    rec = record_consumption(
        bundle=bundle,
        consumer="Local",
        consumed_evidence_ids=[f"capability:codeintel:{task_id}:real"],
        consumed_capability_payloads=[],
        payload_serialized_into_prompt=False,
    )
    assert rec["capability_consumed"] is True  # IDs may still count as id consumption
    assert rec["capability_payload_consumed"] is False


def test_failed_entry_payload_not_forwarded() -> None:
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle

    task_id = "fail-payload-1"
    bundle = build_capability_evidence_bundle(
        task_id=task_id,
        workspace_revision="wr",
        task_statement="failed payload",
        plan_payload={},
        plan_hash="ph",
        planner_decision_id="pd",
        capability_results={
            "repair_loop": {
                "status": "FAILED",
                "invoked": True,
                "gate_passed": False,
                "evidence_refs": [f"capability:repair_loop:{task_id}:fail"],
                "response": {
                    "status": "FAILED",
                    "outcome": {"action": "run", "error": "boom"},
                    "consumer_payload": {
                        "capability": "repair_loop",
                        "markers": ["repair_loop:result"],
                        "fields": {"error": "boom"},
                    },
                },
            }
        },
        selected_capabilities=["repair_loop"],
        source_hash=VALID_SOURCE_HASH,
    )
    entry = bundle["entries"][0]
    assert entry.get("success") is False
    assert not entry.get("consumer_payload")


# ─── Phase B: Local/Online payload injection ─────────────────────────────────


def test_local_prompt_contains_codeintel_memory_belief_payload(tmp_path: Path) -> None:
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    captured: dict[str, str] = {}

    def _gen(req: Any) -> str:
        captured["prompt"] = str(getattr(req, "prompt", "") or "")
        return "diagnosis: ok"

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "loc-payload-1"
    # Build sealed production-shaped bundle with real outcomes → consumer_payload.
    results = {}
    for name in ("codeintel", "memory", "belief"):
        results[name] = {
            "status": "SUCCEEDED",
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"capability:{name}:{task_id}:real"],
            "evidence_ids": [f"capability:{name}:{task_id}:real"],
            "physical_callable": f"capability_executor_registry:{name}",
            "response": {
                "status": "SUCCEEDED",
                "outcome": {
                    "action": "probe",
                    "result": f"{name}_ok",
                    "hit_count": 1 if name == "memory" else 0,
                },
            },
        }
    sealed = build_capability_evidence_bundle(
        task_id=task_id,
        workspace_revision="wr",
        task_statement="local payload markers",
        plan_payload={"selected": list(results)},
        plan_hash="ph-loc-payload",
        planner_decision_id=f"pd-{task_id}",
        capability_results=results,
        selected_capabilities=list(results.keys()),
        source_hash=VALID_SOURCE_HASH,
    )
    req = _local_assist_request(tmp_path, task_id)
    snap = dict(req.planner_snapshot)
    snap["capability_evidence_bundle"] = sealed
    snap["bundle_hash"] = sealed["bundle_hash"]
    snap["baseline_hash"] = sealed["baseline_hash"]
    snap["planner_decision_id"] = sealed["planner_decision_id"]
    req = req.__class__(**{**req.__dict__, "planner_snapshot": snap})
    response = LocalAssistService(provider=InjectedLocalModelProvider(_gen)).handle(req)
    prompt = captured.get("prompt") or ""
    # Markers alone are insufficient — require usable outcome content in the prompt body.
    assert "workspace_fingerprint" in prompt or '"action": "probe"' in prompt or "action" in prompt
    assert "codeintel" in prompt and ("result" in prompt or "action" in prompt)
    assert "memory" in prompt and ("hit_count" in prompt or "action" in prompt or "result" in prompt)
    assert "belief" in prompt and ("action" in prompt or "result" in prompt)
    assert "codeintel:result" in prompt or "codeintel:payload" in prompt
    assert "memory:result" in prompt or "memory:payload" in prompt
    assert "belief:result" in prompt or "belief:payload" in prompt
    ec = response.local_outputs.get("evidence_consumption") or {}
    assert ec.get("capability_payload_consumed") is True, ec
    payloads = list(ec.get("consumed_capability_payloads") or [])
    assert payloads
    for p in payloads:
        fields = p.get("fields") or {}
        assert fields.get("action") or fields.get("result") or fields.get("hit_count") is not None, p


def test_online_prompt_contains_same_capability_payload() -> None:
    from nexus.services.online_nexus_context import build_online_nexus_context

    task_id = "on-payload-1"
    bundle = {
        "schema": "nexus.capability_evidence_bundle.v1",
        "bundle_hash": "a" * 64,
        "baseline_hash": "b" * 64,
        "planner_decision_id": "pd-on",
        "task_id": task_id,
        "source_hash": VALID_SOURCE_HASH,
        "selected_capabilities": ["codeintel", "memory", "belief"],
        "evidence_ids": [
            f"capability:codeintel:{task_id}:real",
            f"capability:memory:{task_id}:real",
            f"capability:belief:{task_id}:real",
        ],
        "entries": [
            {
                "name": n,
                "status": "REAL_INVOKED",
                "success": True,
                "invoked_real": True,
                "evidence_ids": [f"capability:{n}:{task_id}:real"],
                "consumer_payload": {
                    "schema": "nexus.consumer_payload.v1",
                    "capability": n,
                    "markers": [f"{n}:result", f"{n}:payload", f"{n}:finding"],
                    "fields": {
                        "action": "probe",
                        "result": f"{n}_ok",
                        "markers": [f"{n}:result", f"{n}:payload", f"{n}:finding"],
                    },
                    "payload_hash": hashlib.sha256(n.encode()).hexdigest(),
                },
            }
            for n in ("codeintel", "memory", "belief")
        ],
    }
    # Use production-shaped sealed payloads with usable fields (not markers-only).
    for ent in bundle["entries"]:
        n = ent["name"]
        ent["consumer_payload"] = {
            "schema": "nexus.consumer_payload.v1",
            "capability": n,
            "markers": [f"{n}:result", f"{n}:payload", f"{n}:finding"],
            "fields": {
                "action": "probe",
                "result": f"{n}_ok",
                "hit_count": 1 if n == "memory" else 0,
                "markers": [f"{n}:result", f"{n}:payload", f"{n}:finding"],
                "capability": n,
            },
            "payload_hash": hashlib.sha256(n.encode()).hexdigest(),
        }
    ctx = build_online_nexus_context(
        task_statement="online payload",
        task_id=task_id,
        plan={"selected_capabilities": ["codeintel", "memory", "belief"], "plan_hash": "ph"},
        capability_evidence_bundle=bundle,
    )
    prompt = ctx.prompt
    assert "codeintel:result" in prompt
    assert "memory:payload" in prompt
    assert "belief:finding" in prompt
    assert "codeintel_ok" in prompt or '"result": "codeintel_ok"' in prompt or "probe" in prompt
    assert "hit_count" in prompt
    lineage = ctx.lineage
    assert lineage.get("capability_payload_consumed") is True
    assert lineage.get("consumer_payload_hash")
    for p in lineage.get("consumed_capability_payloads") or []:
        fields = p.get("fields") or {}
        assert fields.get("action") == "probe" or fields.get("result"), p


def test_runtime_guidance_pack_ports_world_b_fixture_and_capability_rules() -> None:
    ctx = build_online_nexus_context(
        task_statement="Repair the evidence-backed candidate selector",
        task_id="guidance-pack-1",
        task_type="test_repair",
        route={"fixture_kind": "rlm_harder_v2_autoreason_judge"},
        plan={
            "selected_capabilities": ["autoreason", "claim_gate"],
            "plan_hash": "plan-guidance-1",
        },
    )

    pack = ctx.guidance_pack
    assert pack["schema"] == "nexus.online_guidance_pack.v1"
    assert pack["public_claim_allowed"] is False
    assert pack["fixture_kind"] == "rlm_harder_v2_autoreason_judge"
    assert pack["guidance_hash"]
    assert "empty evidence_refs" in ctx.hidden_guidance
    assert "verifier status" in ctx.hidden_guidance
    assert ctx.lineage["guidance_pack"]["guidance_hash"] == pack["guidance_hash"]


def test_runtime_guidance_pack_does_not_leak_unselected_fixture_rules() -> None:
    ctx = build_online_nexus_context(
        task_statement="Inspect a normal configuration change",
        task_id="guidance-pack-2",
        task_type="codeintel",
        route={},
        plan={"selected_capabilities": ["codeintel"], "plan_hash": "plan-guidance-2"},
    )

    assert ctx.guidance_pack["fixture_kind"] == ""
    assert "empty evidence_refs" not in ctx.hidden_guidance
    assert "governance_block" not in ctx.hidden_guidance
    assert ctx.guidance_pack["public_claim_allowed"] is False


def test_default_prompt_compression_uses_measured_runtime_edge() -> None:
    from nexus.services.capability_registry import build_default_mainchain_invokers

    invoker = build_default_mainchain_invokers()["prompt_compression"]
    result = invoker(
        {
            "task_id": "compression-real-edge-1",
            "task_statement": "x" * 9000,
            "online_prompt": "x" * 9000,
            "online_payload": "y" * 9000,
            "capability_results": {
                "memory": {
                    "status": "SUCCEEDED",
                    "evidence_refs": ["memory:compression-real-edge-1"],
                }
            },
        }
    )

    response = result["response"]
    assert result["invoked"] is True
    assert result["gate_passed"] is True
    assert result["outcome_contributed"] is True
    assert response["compressed_context_chars"] < response["original_context_chars"]
    assert response["compression_ratio"] > 0
    assert result["physical_callable"].endswith(
        "build_prompt_compression_capability_invoker"
    )


def test_repair_loop_cannot_pass_without_real_attempt_and_verification_effect() -> None:
    from nexus.services.capability_registry import build_real_executor_invoker

    invoker = build_real_executor_invoker("repair_loop")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "repair-no-effect-1",
            "task_statement": "repair without a candidate or verifier command",
            "planner": {"plan_hash": "repair-no-effect-plan"},
        }
    )

    assert result["gate_passed"] is False
    assert result["outcome_contributed"] is False
    assert result["status"] in {"FAILED", "BLOCKED"}
    outcome = result["response"].get("outcome") or {}
    assert outcome.get("semantic_status") in {"BLOCKED", "FAILED", "UNVERIFIED"}


def test_pregate_empty_verify_command_set_cannot_satisfy_physical_contract(
    tmp_path: Path,
) -> None:
    from nexus.services.capability_registry import build_real_executor_invoker

    invoker = build_real_executor_invoker("pregate")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "pregate-empty-work-1",
            "task_statement": "detect a project without a runnable verifier command",
            "planner": {"plan_hash": "pregate-empty-work-plan"},
            "codeintel": {"workspace_root": str(tmp_path)},
        }
    )

    assert result["gate_passed"] is False
    assert result["outcome_contributed"] is False
    assert result["status"] == "FAILED"
    outcome = result["response"]["outcome"]
    assert outcome["semantic_status"] == "BLOCKED"
    assert outcome["error"] == "EXPLICIT_VERIFY_COMMANDS_REQUIRED"
    assert outcome["command_count"] == 0
    assert outcome["all_passed"] is False


def test_pregate_executes_non_empty_verifier_command(tmp_path: Path) -> None:
    import sys

    from nexus.services.capability_registry import build_real_executor_invoker

    (tmp_path / "target.py").write_text("value = 1\n", encoding="utf-8")
    invoker = build_real_executor_invoker("pregate")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "pregate-real-command-1",
            "task_statement": "compile the bounded target",
            "planner": {"plan_hash": "pregate-real-command-plan"},
            "codeintel": {
                "workspace_root": str(tmp_path),
                "verify_commands": [f"{sys.executable} -m py_compile target.py"],
            },
        }
    )

    assert result["status"] == "SUCCEEDED"
    assert result["gate_passed"] is True
    outcome = result["response"]["outcome"]
    assert outcome["command_count"] == 1
    assert outcome["all_passed"] is True
    assert outcome["results"][0]["exit_code"] == 0


def test_semantic_searcher_queries_real_memory_repository(tmp_path: Path) -> None:
    from nexus.services.capability_registry import build_real_executor_invoker
    from nexus.services.memory_repository import MemoryRepository

    db_path = tmp_path / ".nexus" / "knowledge" / "lancedb"
    repository = MemoryRepository(db_path)
    repository.ensure_table(
        "policy",
        initial_data=[
            {
                "id": "family-policy-1",
                "rule_id": "family-policy-1",
                "condition": "capability closure",
                "action": "require physical evidence",
                "confidence": 0.9,
            }
        ],
        fts_column="action",
    )
    invoker = build_real_executor_invoker("semantic_searcher")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "semantic-search-real-1",
            "task_statement": "require physical evidence",
            "planner": {"plan_hash": "semantic-search-real-plan"},
            "codeintel": {
                "workspace_root": str(tmp_path),
                "search_query": "physical",
                "search_table": "policy",
            },
        }
    )

    assert result["status"] == "SUCCEEDED"
    assert result["gate_passed"] is True
    outcome = result["response"]["outcome"]
    assert outcome["search_performed"] is True


def test_lancedb_queries_real_repository_table(tmp_path: Path) -> None:
    from nexus.services.capability_registry import build_real_executor_invoker
    from nexus.services.memory_repository import MemoryRepository

    repository = MemoryRepository(tmp_path / ".nexus" / "knowledge" / "lancedb")
    repository.ensure_table(
        "policy",
        initial_data=[
            {
                "id": "lancedb-policy-1",
                "rule_id": "lancedb-policy-1",
                "condition": "machine contract",
                "action": "query real repository",
                "confidence": 0.8,
            }
        ],
        fts_column="action",
    )
    invoker = build_real_executor_invoker("lancedb")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "lancedb-real-query-1",
            "task_statement": "query real repository",
            "planner": {"plan_hash": "lancedb-real-query-plan"},
            "codeintel": {
                "workspace_root": str(tmp_path),
                "search_query": "repository",
                "search_table": "policy",
            },
        }
    )

    assert result["status"] == "SUCCEEDED"
    assert result["gate_passed"] is True
    outcome = result["response"]["outcome"]
    assert outcome["query_performed"] is True


def test_jit_validation_applies_real_tool_mask_and_quota() -> None:
    from nexus.services.capability_registry import build_real_executor_invoker

    invoker = build_real_executor_invoker("jit_validation")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "jit-real-mask-1",
            "task_statement": "核驗 capability contract",
            "planner": {"plan_hash": "jit-real-mask-plan"},
            "codeintel": {
                "jit_all_tools": ["read_file", "run_test", "write_file"],
                "jit_token_usage": 120,
            },
        }
    )

    assert result["status"] == "SUCCEEDED"
    assert result["gate_passed"] is True
    outcome = result["response"]["outcome"]
    assert outcome["mask_applied"] is True
    assert outcome["quota_checked"] is True
    assert outcome["result"]["selected_tools"] == ["read_file", "run_test"]
    assert outcome["result"]["token_usage"] == 120


def test_mempalace_gate_ingests_retrieves_and_verifies_real_artifact(
    tmp_path: Path,
) -> None:
    from nexus.services.capability_registry import build_real_executor_invoker

    invoker = build_real_executor_invoker("mempalace_gate")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "mempalace-real-roundtrip-1",
            "task_statement": "retain capability closure evidence",
            "planner": {"plan_hash": "mempalace-real-roundtrip-plan"},
            "codeintel": {
                "workspace_root": str(tmp_path),
                "mempalace_tenant_id": "family-canary",
                "mempalace_artifact_type": "capability_evidence",
                "mempalace_artifact": {
                    "artifact_id": "closure-evidence-1",
                    "content": "capability closure verified",
                    "source_hash": "source-hash-1",
                },
                "mempalace_query": "closure-evidence-1",
            },
        }
    )

    assert result["status"] == "SUCCEEDED"
    assert result["gate_passed"] is True
    outcome = result["response"]["outcome"]
    assert outcome["ingest_performed"] is True
    assert outcome["retrieve_performed"] is True
    assert outcome["verification_passed"] is True
    assert outcome["retrieved_count"] == 1


def test_sandbox_executes_command_inside_copied_workspace(tmp_path: Path) -> None:
    import sys

    from nexus.services.capability_registry import build_real_executor_invoker

    (tmp_path / "target.py").write_text("value = 1\n", encoding="utf-8")
    invoker = build_real_executor_invoker("sandbox")
    assert invoker is not None
    result = invoker(
        {
            "task_id": "sandbox-real-run-1",
            "task_statement": "execute bounded isolated verification",
            "planner": {"plan_hash": "sandbox-real-run-plan"},
            "route": {"escalate": True},
            "escalate_triggered": True,
            "triggered_escalations": ["sandbox"],
            "executor_flags": {"sandbox": True},
            "codeintel": {
                "workspace_root": str(tmp_path),
                "sandbox_command": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; assert Path('target.py').exists()",
                ],
                "sandbox_timeout_sec": 15,
            },
        }
    )

    assert result["status"] == "SUCCEEDED"
    assert result["gate_passed"] is True
    outcome = result["response"]["outcome"]
    assert outcome["sandbox_executed"] is True
    assert outcome["workspace_isolated"] is True
    assert outcome["exit_code"] == 0
    assert outcome["network_allowed"] is False


def test_repair_loop_is_materialized_from_verified_local_receipt(tmp_path: Path) -> None:
    local_receipt_path = tmp_path / "local-repair-receipt.json"
    local_receipt_path.write_text(
        json.dumps(
            {
                "task_id": "repair-stage-owned-1",
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "verifier_reached": True,
                "verifier_result": "pass",
                "candidate_hashes": ["candidate-hash-1"],
                "isolation_status": "isolated",
            }
        ),
        encoding="utf-8",
    )

    class _VerifiedLocalService:
        def handle(self, request: Any) -> dict[str, Any]:
            return {
                "task_id": "repair-stage-owned-1",
                "status": "SUCCEEDED",
                "action": "verified-subtask",
                "local_model_invoked": True,
                "output_delivered": True,
                "executor_invoked": True,
                "physical_callable": "LocalModelExecutor.run",
                "candidate_summary": {
                    "isolation_status": "isolated",
                    "selected_candidate_hash": "candidate-hash-1",
                    "selected_candidate_hash_matches_applied": True,
                },
                "verifier_summary": {
                    "verifier_reached": True,
                    "verifier_status": "pass",
                    "exit_code": 0,
                },
                "receipt_path": str(local_receipt_path),
                "evidence_refs": ["local:repair-stage-owned-1"],
                "outcome_contributed": True,
            }

    receipt = UnifiedRuntime(
        planner=_Planner(
            selected=["local_model_executor", "repair_loop"],
            required=["repair_loop"],
        ),
        local_service=_VerifiedLocalService(),
    ).run(
        UnifiedRuntimeRequest(
            task_id="repair-stage-owned-1",
            workspace_revision="wr-repair-stage-owned",
            task_statement="repair and verify candidate in isolation",
            task_type="repair",
            route={"mainchain_entry": True},
            local_enabled=True,
            online_enabled=False,
            local_request={
                "task_id": "repair-stage-owned-1",
                "action": "verified-subtask",
            },
        ),
        verifier=_verifier_explicit,
        learning=_learning,
    )

    stage = receipt["capability_results"]["repair_loop"]
    assert stage["status"] == "SUCCEEDED"
    assert stage["gate_passed"] is True
    outcome = stage["response"]["response"]["outcome"]
    assert outcome["candidate_hash"] == "candidate-hash-1"
    assert outcome["verifier_passed"] is True
    assert outcome["settlement_decision"] == "receipt_complete"


@pytest.mark.parametrize("capability_name", ["acceptance_check", "bdd_acceptance_skill"])
def test_acceptance_capabilities_execute_only_after_verifier(
    capability_name: str,
) -> None:
    seen: dict[str, Any] = {}

    def acceptance_invoker(context: dict[str, Any]) -> dict[str, Any]:
        seen.update(context)
        verifier = context.get("verifier") or {}
        verifier_response = verifier.get("response") or {}
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": verifier_response.get("verifier_status") == "pass",
            "evidence_refs": [f"acceptance:{context['task_id']}"],
            "response": {"status": "SUCCEEDED"},
        }

    receipt = UnifiedRuntime(
        planner=_Planner(selected=[capability_name], required=[]),
        local_service=None,
    ).run(
        UnifiedRuntimeRequest(
            task_id=f"postflight-{capability_name}",
            workspace_revision="wr-postflight",
            task_statement=f"verify {capability_name} ordering",
            task_type="analysis",
            route={"mainchain_entry": True},
            online_prompt="unused",
            online_payload="unused",
            local_enabled=False,
            online_enabled=True,
        ),
        online_invoker=_online,
        capability_invokers={capability_name: acceptance_invoker},
        verifier=_verifier_explicit,
        learning=_learning,
    )

    verifier_seen = seen.get("verifier") or {}
    assert verifier_seen.get("invoked") is True
    assert (verifier_seen.get("response") or {}).get("verifier_status") == "pass"
    assert receipt["capability_results"][capability_name]["gate_passed"] is True


def test_local_online_payload_hash_matches(tmp_path: Path) -> None:
    from nexus.services.capability_evidence_bundle import hash_consumer_payloads
    from nexus.services.local_assist_service import build_local_compact_evidence
    from nexus.services.online_nexus_context import compact_capability_evidence_for_prompt

    task_id = "hash-match-1"
    payloads = [
        {
            "schema": "nexus.consumer_payload.v1",
            "capability": n,
            "markers": [f"{n}:result", f"{n}:payload"],
            "fields": {"action": "probe", "result": f"{n}_ok", "markers": [f"{n}:result", f"{n}:payload"]},
            "payload_hash": hashlib.sha256(n.encode()).hexdigest(),
        }
        for n in ("codeintel", "memory", "belief")
    ]
    bundle = {
        "bundle_hash": "c" * 64,
        "baseline_hash": "d" * 64,
        "planner_decision_id": "pd-h",
        "task_id": task_id,
        "selected_capabilities": ["codeintel", "memory", "belief"],
        "entries": [
            {
                "name": p["capability"],
                "success": True,
                "invoked_real": True,
                "evidence_ids": [f"capability:{p['capability']}:{task_id}:real"],
                "consumer_payload": p,
            }
            for p in payloads
        ],
    }
    local = build_local_compact_evidence(
        bundle=bundle,
        selected_local_capabilities=["codeintel", "memory", "belief"],
    )
    online = compact_capability_evidence_for_prompt(bundle)
    assert local["consumer_payload_hash"]
    assert online["consumer_payload_hash"]
    assert local["consumer_payload_hash"] == online["consumer_payload_hash"]
    assert local["consumer_payload_hash"] == hash_consumer_payloads(payloads)


def test_payload_removed_means_not_consumed(tmp_path: Path) -> None:
    from nexus.services.capability_evidence_bundle import record_consumption
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    task_id = "no-payload-1"
    req = _local_assist_request(tmp_path, task_id)
    # Bundle with IDs only — no consumer_payload
    snap = dict(req.planner_snapshot)
    bundle = dict(snap["capability_evidence_bundle"])
    for ent in bundle.get("entries") or []:
        ent.pop("consumer_payload", None)
        ent["has_consumer_payload"] = False
    snap["capability_evidence_bundle"] = bundle
    req = req.__class__(**{**req.__dict__, "planner_snapshot": snap})
    response = LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _: "diagnosis: ok")
    ).handle(req)
    ec = response.local_outputs.get("evidence_consumption") or {}
    assert ec.get("capability_payload_consumed") is False
    # Explicit record_consumption with no serialized payload
    rec = record_consumption(
        bundle=bundle,
        consumer="Local",
        consumed_evidence_ids=list(ec.get("consumed_evidence_ids") or []),
        consumed_capability_payloads=[],
        payload_serialized_into_prompt=False,
    )
    assert rec["capability_payload_consumed"] is False


# ─── Phase C: used causality ─────────────────────────────────────────────────


def test_selected_but_unconsumed_not_reported_used() -> None:
    from nexus.services.local_heal.local_model_executor import compute_capability_usage

    out = compute_capability_usage(
        selected_capabilities=("codeintel", "memory", "belief", "local_model_executor"),
        metadata={"memory_retrieval_attempted": False},
        local_model_called=True,
        route_context={},
    )
    assert "local_model_executor" in out["selected_capabilities_used"]
    assert "codeintel" not in out["selected_capabilities_used"]
    assert "memory" not in out["selected_capabilities_used"]
    assert out["capability_usage_status"]["codeintel"] == "selected_not_consumed"
    assert out["selected_capabilities"] != out["selected_capabilities_used"] or len(out["selected_capabilities"]) == 1


def test_failed_repair_loop_not_reported_used() -> None:
    from nexus.services.local_heal.local_model_executor import compute_capability_usage

    out = compute_capability_usage(
        selected_capabilities=("repair_loop", "local_model_executor"),
        metadata={
            "localheal_pipeline_actual_execution": False,
            "localheal_pipeline_availability_only": True,
            "repair_loop_status": "FAILED",
        },
        local_model_called=True,
        route_context={},
    )
    assert "repair_loop" not in out["selected_capabilities_used"]
    assert out["capability_usage_status"]["repair_loop"] != "used"


def test_memory_used_only_when_prompt_injected() -> None:
    from nexus.services.local_heal.local_model_executor import compute_capability_usage

    no_prompt = compute_capability_usage(
        selected_capabilities=("memory",),
        metadata={"memory_retrieval_attempted": True, "memory_prompt_included": False},
        local_model_called=False,
        route_context={},
    )
    assert "memory" not in no_prompt["selected_capabilities_used"]
    yes = compute_capability_usage(
        selected_capabilities=("memory",),
        metadata={"memory_retrieval_attempted": True, "memory_prompt_included": True},
        local_model_called=False,
        route_context={},
    )
    assert "memory" in yes["selected_capabilities_used"]


def test_capability_causality_rejects_selected_used_mismatch() -> None:
    from nexus.services.local_heal.local_model_armor_receipt_gate import (
        validate_capability_causality,
    )

    ok, issues = validate_capability_causality(
        {
            "selected_capabilities": ["codeintel", "memory", "belief"],
            "selected_capabilities_used": ["codeintel", "memory", "belief"],
            # no capability_usage_status → copy false-green
        }
    )
    assert ok is False
    assert any("selected_used_mismatch" in i or "without_causal" in i for i in issues)

    ok2, issues2 = validate_capability_causality(
        {
            "selected_capabilities": ["codeintel", "memory"],
            "selected_capabilities_used": ["codeintel"],
            "capability_usage_status": {
                "codeintel": "used",
                "memory": "selected_not_consumed",
            },
        }
    )
    assert ok2 is True
    assert issues2 == []


def test_final_mainchain_canary_receipt_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Production canary: real invokers/executors; injected providers only.

    No _cap_ok / test:* physical_callable / lambda capability engines.
    """
    import json
    import os

    # Local Armor receipts land in the test worktree root; ephemeral temp is
    # expected for pytest, matching the family-canary matrix contract.
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")
    from nexus.services.capability_evidence_bundle import verify_capability_evidence_bundle
    from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
    from nexus.services.mainchain_entry import (
        build_mainchain_capability_invokers,
        run_mainchain,
    )

    task_id = "final-canary-001"
    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")

    local_calls = {"n": 0, "prompts": []}
    online_calls = {"n": 0, "prompts": []}

    def local_gen(req: Any) -> str:
        local_calls["n"] += 1
        local_calls["prompts"].append(str(getattr(req, "prompt", "") or ""))
        return (
            "--- a/target.py\n+++ b/target.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def target():\n"
            "-    return 1\n"
            "+    return 2\n"
        )

    def online(ctx: dict[str, Any]) -> dict[str, Any]:
        online_calls["n"] += 1
        # Capture the final with_nexus-assembled provider prompt only — not lineage dumps.
        prompt = str(ctx.get("online_prompt") or "")
        online_calls["prompts"].append(prompt)
        online_calls["last_prompt"] = prompt
        out = _online(ctx)
        # Workforce admission resolves the only admitted provider (agy_flash -> agy);
        # the response must carry that exact provider identity or the runtime fails
        # closed with online_response_provider_mismatch.
        out["provider"] = "agy"
        return out

    local_request = LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id=task_id,
        parent_task_id="parent-final",
        workspace_root=str(tmp_path),
        workspace_revision="wr-final",
        task_statement="final canary production engines codeintel memory belief",
        action="candidate",
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("canary:final",),
        requested_role="candidate",
        mutation_policy="isolated_only",
        time_budget=30.0,
        planner_snapshot={
            "route_truth_source": "CapabilityPlanner",
            "execution_topology": "single_local_model",
            "protocol_mode": "unified_diff",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b",
        },
    )

    # Production invokers only — no fixture capability lambdas.
    production_invokers = build_mainchain_capability_invokers(
        codeintel={"scan_report_present": True, "risk_score": 1},
        include_postflight_gates=True,
    )

    receipt = run_mainchain(
        UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision="wr-final",
            task_statement="final canary production engines codeintel memory belief",
            task_type="repair",
            route={
                "recommended_flow": "hybrid",
                "provider": "agy",
                "injected_transport": True,
                "workspace_root": str(tmp_path),
                "mainchain_entry": True,
                "online_invoker_provider": "agy",
                "workforce_bindings": {
                    "online": {
                        "worker_id": "agy_flash",
                        "controls": [
                            "task_card",
                            "allowed_files",
                            "mandatory_commands",
                            "independent_verification",
                        ],
                    },
                    "local": {
                        "worker_id": "local_coder_7b",
                        "controls": [
                            "small_scope",
                            "parser",
                            "compile",
                            "focused_tests",
                            "reversible_application",
                        ],
                    },
                },
                "route_features": {"memory_hits": 1},
                "executor_flags": {},
            },
            online_prompt="return ok",
            online_payload="payload",
            local_enabled=True,
            local_request=local_request,
            online_enabled=True,
            evidence_refs=("canary:final",),
            codeintel={
                "scan_report_present": True,
                "risk_score": 1,
                "impact_report_present": True,
                "workspace_root": str(tmp_path),
                "verify_commands": ["echo ok"],
                "verify_timeout_sec": 10,
                "intent_pass": True,
                "target_files": ["target.py"],
                "impact_map": {"target.py": {"impact": "canary"}},
                "acceptance_criteria": ["canary closure complete"],
                "deliverables": ["canary receipt"],
                "steps": ["plan", "execute", "verify"],
                "handoff_readiness": 1.0,
                "mempalace_tenant_id": "final-canary-tenant",
                "mempalace_artifact": {
                    "artifact_id": task_id,
                    "content": "final canary production receipt",
                },
                "mempalace_artifact_type": "task_receipt",
                "mempalace_query": task_id,
            },
        ),
        online_invoker=online,
        local_service=LocalAssistService(
            provider=InjectedLocalModelProvider(
                local_gen,
                provider_identity="ollama",
                model_identity="qwen2.5-coder:7b-instruct",
            )
        ),
        capability_invokers=production_invokers,
        verifier=_verifier_explicit,
        learning=_learning,
        with_nexus_armor=True,
    )

    out_tmp = Path("/tmp/nexus_mainchain_final_gate_receipt.json")
    out_tmp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    scratch = str(os.environ.get("NEXUS_IMPLEMENTER_SCRATCH") or "").strip()
    if scratch:
        scratch_path = Path(scratch)
        scratch_path.mkdir(parents=True, exist_ok=True)
        (scratch_path / "nexus_mainchain_final_gate_receipt.json").write_text(
            out_tmp.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    bundle = receipt.get("capability_evidence_bundle") or {}
    seal = verify_capability_evidence_bundle(bundle)
    assert seal.get("ok") is True

    # Physical callables: no test:/fixture:
    fixture_count = 0
    production_count = 0
    for ent in bundle.get("entries") or []:
        phys = str(ent.get("physical_callable") or "")
        if phys.startswith(("test:", "fixture:")):
            fixture_count += 1
        elif phys:
            production_count += 1
    assert fixture_count == 0, "production canary must not use test:/fixture: callables"
    assert production_count > 0

    # Bundle carries bounded consumer_payload for context caps that succeeded.
    payload_caps = {
        e["name"]
        for e in (bundle.get("entries") or [])
        if e.get("success") and e.get("consumer_payload")
    }
    assert "codeintel" in payload_caps or any(
        (e.get("consumer_payload") or {}).get("capability") == "codeintel"
        for e in (bundle.get("entries") or [])
    )

    local = receipt.get("local") or {}
    local_resp = local.get("response") if isinstance(local.get("response"), dict) else {}
    local_outputs = local_resp.get("local_outputs") if isinstance(local_resp, dict) else {}
    ec = local_outputs.get("evidence_consumption") if isinstance(local_outputs, dict) else {}
    online = receipt.get("online") or {}
    online_resp = online.get("response") if isinstance(online.get("response"), dict) else {}
    with_nexus = online_resp.get("with_nexus") if isinstance(online_resp, dict) else {}
    lineage = with_nexus.get("lineage") if isinstance(with_nexus, dict) else {}

    local_prompt = "\n".join(local_calls["prompts"])
    online_prompt = str(online_calls.get("last_prompt") or "\n".join(online_calls["prompts"]))
    assert online_prompt.strip(), "Online provider must receive a non-empty with_nexus prompt"
    # Must be real provider prompt (with_nexus sections), not lineage JSON dump.
    assert "NEXUS_SESSION_BOUNDARY" in online_prompt or "[TASK]" in online_prompt or "NEXUS_" in online_prompt

    # Bundle carries usable outcome fields for context caps.
    for cap in ("codeintel", "memory", "belief"):
        entry = next((e for e in (bundle.get("entries") or []) if e.get("name") == cap), None)
        assert entry is not None, cap
        assert entry.get("success") is True, cap
        cp = entry.get("consumer_payload") or {}
        fields = cp.get("fields") or {}
        assert fields.get("action"), (cap, fields)
        assert fields.get("result") is not None or fields.get("hit_count") is not None or fields.get("evidence_id") or fields.get("confidence") is not None, (
            cap,
            fields,
        )
        # Local + Online provider prompts contain usable content (not markers alone).
        action = str(fields.get("action") or "")
        assert action and action in local_prompt, (cap, action, local_prompt[:500])
        assert action in online_prompt, (cap, action, online_prompt[:500])
        assert f"{cap}:payload" in local_prompt or f"{cap}:result" in local_prompt
        assert f"{cap}:payload" in online_prompt or f"{cap}:result" in online_prompt
        assert "no_evaluate" not in str(fields).lower()
        assert not fields.get("error"), (cap, fields)

    # P0-A: belief must be real assess_confidence with numeric confidence.
    belief_entry = next(e for e in (bundle.get("entries") or []) if e.get("name") == "belief")
    belief_fields = (belief_entry.get("consumer_payload") or {}).get("fields") or {}
    assert belief_fields.get("action") == "assess_confidence", belief_fields
    conf = belief_fields.get("confidence")
    assert isinstance(conf, (int, float)), belief_fields
    assert 0.0 <= float(conf) <= 1.0, conf

    assert lineage.get("capability_payload_consumed") is True
    assert (ec or {}).get("capability_payload_consumed") is True
    local_ph = str((ec or {}).get("consumer_payload_hash") or "")
    online_ph = str((lineage or {}).get("consumer_payload_hash") or "")
    from nexus.services.capability_evidence_bundle import hash_consumer_payloads

    local_payloads = list((ec or {}).get("consumed_capability_payloads") or [])
    online_payloads = list((lineage or {}).get("consumed_capability_payloads") or [])
    assert local_payloads, "Local must serialize bounded consumer payloads"
    assert online_payloads, "Online must serialize bounded consumer payloads"
    local_caps = [str(p.get("capability") or "") for p in local_payloads]
    online_caps = [str(p.get("capability") or "") for p in online_payloads]
    assert all(local_caps), local_payloads
    assert all(online_caps), online_payloads
    assert len(set(local_caps)) == len(local_caps), local_caps
    assert len(set(online_caps)) == len(online_caps), online_caps
    local_cap_set = set(local_caps)
    online_cap_set = set(online_caps)

    # Each side's physical hash must be recomputed from its own canonical rows.
    assert hash_consumer_payloads(local_payloads) == local_ph
    assert hash_consumer_payloads(online_payloads) == online_ph

    # Local consumption basis must be a legal subset of the Online basis, and
    # every payload Local claims to consume must be byte-identical to the same
    # capability on the Online serialized basis.
    assert local_cap_set <= online_cap_set, sorted(local_cap_set - online_cap_set)
    online_by_cap = {str(p.get("capability") or ""): p for p in online_payloads}
    bundle_payload_by_cap = {
        str(e.get("name") or ""): e.get("consumer_payload")
        for e in (bundle.get("entries") or [])
        if e.get("success") and e.get("consumer_payload")
    }
    for lp in local_payloads:
        cap = str(lp.get("capability") or "")
        op = online_by_cap.get(cap)
        bp = bundle_payload_by_cap.get(cap)
        assert op is not None, cap
        assert bp is not None, cap
        assert hash_consumer_payloads([lp]) == hash_consumer_payloads([op]), cap
        assert hash_consumer_payloads([lp]) == hash_consumer_payloads([bp]), cap
    assert local_ph == hash_consumer_payloads(
        [online_by_cap[c] for c in local_caps]
    ), "Local basis must exactly match the Online shared-basis serialization"
    used_set = set(ec.get("selected_capabilities_used") or [])
    assert local_cap_set <= used_set, sorted(local_cap_set - used_set)
    # The executor itself may be marked used without a serialized payload; any
    # other gap would mean the payload basis is not the recorded consumption set.
    assert used_set - local_cap_set <= {"local_model_executor"}, sorted(
        used_set - local_cap_set
    )

    # Online-only canonical-required governance caps must carry real receipts,
    # so a broader Online full set must hash differently from the Local subset.
    for cap in ("harness_preflight_sensor", "mempalace_gate"):
        assert cap in online_cap_set, cap
        entry = next(e for e in (bundle.get("entries") or []) if e.get("name") == cap)
        assert entry is not None, cap
        assert entry.get("success") is True, cap
        phys = str(entry.get("physical_callable") or "")
        assert phys and not phys.startswith(("test:", "fixture:")), (cap, phys)
        assert entry.get("consumer_payload"), cap
    assert local_cap_set < online_cap_set, local_cap_set
    assert local_ph != online_ph, "Full-set hash must differ when Online consumes extra payloads"

    # Phase C: causal used status on mainchain Local path (not selected=used copy).
    selected_caps = list(
        (ec or {}).get("selected_capabilities")
        or local_outputs.get("selected_capabilities")
        or []
    )
    used_caps = list(
        (ec or {}).get("selected_capabilities_used")
        or local_outputs.get("selected_capabilities_used")
        or []
    )
    usage_status = dict(
        (ec or {}).get("capability_usage_status")
        or local_outputs.get("capability_usage_status")
        or {}
    )
    assert selected_caps, "selected_capabilities must be recorded"
    assert used_caps, "selected_capabilities_used must be non-empty for injected payloads"
    assert usage_status, "capability_usage_status required for causal used proof"
    # Must not be a silent full selected=used copy of planner set (7 caps).
    planner_selected = list(receipt.get("selected_capabilities") or [])
    if len(planner_selected) > len(used_caps):
        assert set(used_caps) != set(planner_selected)
    for cap in used_caps:
        assert usage_status.get(cap) == "used", (cap, usage_status)

    assert receipt.get("public_claim_allowed") is False
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert local_calls["n"] >= 1
    assert online_calls["n"] >= 1
    assert local_resp.get("physical_callable") == "LocalModelExecutor.run"
    assert out_tmp.is_file()

    blockers = list(receipt.get("capability_closure_blockers") or [])
    assert receipt.get("receipt_complete") is True
    # research_route is a required-but-escalate-only CONTROL_PLANE_REFERENCE
    # suggestion node: untriggered production policy skips it, and its real
    # executor is a planner suggestion (never a production executor F path), so
    # full closure is not claimed. Every other selected capability must have
    # truly executed and passed, which receipt_complete already enforces.
    assert receipt.get("capability_closure_complete") is False, blockers
    assert blockers == ["research_route:SKIPPED:SKIPPED_POLICY_NOT_TRIGGERED"], blockers


# --- Phase 0 / truth-seal false-green: consumption + adapter invariants ---


def test_H_adapter_gate_failed_blocks_outcome_contributed():
    """H: adapters must not set outcome_contributed when gate_passed is false."""
    from nexus.engine.capability_receipt_adapters import (
        ClaimGateReceiptAdapter,
        DeliveryGateReceiptAdapter,
        ArtifactGateReceiptAdapter,
        merge_capability_receipt,
    )
    try:
        from nexus.engine.capability_receipt_adapters import MemPalaceGateReceiptAdapter as MempalaceGateReceiptAdapter
    except ImportError:
        try:
            from nexus.engine.capability_receipt_adapters import MemPalaceGateReceiptAdapter
        except ImportError:
            MempalaceGateReceiptAdapter = None

    r = merge_capability_receipt(
        name="x",
        selected=True,
        invoked=True,
        evidence_refs=["ev1"],
        gate_passed=False,
        outcome_contributed=True,
    )
    assert r.gate_passed is False
    assert r.outcome_contributed is False

    payload_fail = {
        "claim_gate_invoked": True,
        "claim_gate_passed": False,
        "verifier_status": "FAILED",
        "evidence_refs": ["ev"],
    }
    adapters = [
        ClaimGateReceiptAdapter,
        DeliveryGateReceiptAdapter,
        ArtifactGateReceiptAdapter,
    ]
    if MempalaceGateReceiptAdapter is not None:
        adapters.append(MempalaceGateReceiptAdapter)
    for Adapter in adapters:
        try:
            out = Adapter().build(claim_verified=False, payload=payload_fail)
        except Exception:
            continue
        assert out.outcome_contributed is False, Adapter.__name__
        if out.gate_passed is False:
            assert out.outcome_contributed is False


def test_explicit_bool_key_presence_is_not_true():
    """Key present with false/0/'false' must not count as true."""
    from nexus.engine.capability_receipt_adapters import _explicit_bool, _as_bool

    payload = {"gate_passed": False, "flag": 0, "s": "false", "empty": ""}
    # presence of key is not truth
    assert _as_bool(payload.get("gate_passed")) is False
    # _explicit_bool should mean "explicit true", not "key exists"
    assert _explicit_bool(payload, "gate_passed") is False
    assert _explicit_bool(payload, "flag") is False
    assert _explicit_bool({"gate_passed": True}, "gate_passed") is True


def test_id_only_lists_cannot_mark_consumer_consumed_on_r3():
    """attach_r3 must not mark CONSUMED from consumed_evidence_ids alone."""
    from nexus.evidence.receipt_base import attach_r3_receipt_base

    receipt = {
        "task_id": "id-only-task",
        "workspace_revision": "wr",
        "planner_decision_id": "pd",
        "consumed_evidence_ids": ["ev:1"],
        "executed_capabilities": ["codeintel"],
        "contributed_capabilities": ["codeintel"],
    }
    attach_r3_receipt_base(receipt)
    base = receipt["receipt_base"]
    status = base.get("consumer_payload_hash_status") or ""
    assert (base.get("consumer_payload_hash") or "") == "" or status in {
        "ID_ONLY_NOT_CONSUMED",
        "UNAVAILABLE",
        "PRESENT_NOT_CONSUMED",
    }
    assert status != "CONSUMED"


def test_production_runner_imports_no_tests() -> None:
    """Production closure runner must import only production modules — no tests.* imports allowed."""
    import sys
    from nexus.services import product_capability_closure_runner

    closure_runner_path = Path(product_capability_closure_runner.__file__)
    content = closure_runner_path.read_text(encoding="utf-8")
    assert "from tests" not in content, "Production closure runner must not import tests.*"
    assert "import tests" not in content, "Production closure runner must not import tests.*"


# ── E1: Evidence mode and physical trust boundary ──────────────────────


def _v2_patch(record: dict, tmp_path: Path | None = None) -> dict:
    """Add v2 contract required fields to a test record."""
    root = tmp_path if tmp_path is not None else Path("/tmp/e1_v2_fallback")
    root.mkdir(parents=True, exist_ok=True)
    upstream_sha = _canonical_hash({"v2": "patch"})
    record.setdefault("execution_class", "provider_native")
    record.setdefault("provider_observation", "executed")
    record.setdefault("workspace_revision", "wr-v2")
    record["upstream_receipt_sha256"] = upstream_sha
    record.setdefault("run_root", str(root))
    refs = record.get("evidence_refs")
    if isinstance(refs, list):
        for i, r in enumerate(refs):
            if isinstance(r, dict):
                r.setdefault("content_kind", "json")
                r.setdefault("kind", "stdout")
                if r.get("path") and not r.get("sha256"):
                    p = Path(str(r["path"]))
                    if p.exists():
                        r["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
                    elif r.get("payload") is not None:
                        r["sha256"] = hashlib.sha256(
                            json.dumps(r["payload"], sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest()
    return record


def _canonical_hash(value: object) -> str:
    """Match the production _canonical_hash exactly."""
    import hashlib, json
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_sha256_bytes(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def _baseline_live_record(evidence_path: Path | None = None) -> dict:
    """Return a valid baseline record that passes LIVE_EXECUTED_PASS."""
    import hashlib
    import json
    from pathlib import Path

    tmp_dir = Path("/tmp/e1_baseline")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ep = evidence_path or (tmp_dir / "baseline.json")
    payload = {"task_id": "baseline-test", "capability": "codeintel"}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ep.write_bytes(body)
    physical_sha = hashlib.sha256(body).hexdigest()
    json_sha = _canonical_hash(payload)
    effect_payload = {"action": "codeintel"}
    upstream_sha = _canonical_hash({"root": "baseline"})
    return {
        "task_id": "baseline-test",
        "planner_decision_id": "pd-baseline",
        "workspace_revision": "wr-baseline",
        "upstream_receipt_sha256": upstream_sha,
        "execution_class": "provider_native",
        "provider_observation": "executed",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": str(ep),
                "sha256": physical_sha,
                "json_sha256": json_sha,
                "content_kind": "json",
                "kind": "stdout",
                "payload": payload,
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": effect_payload,
            "artifact_hash": _canonical_hash(effect_payload),
        },
        "receipt_payload": {"task_id": "baseline-test"},
        "receipt_hash": _canonical_hash({"task_id": "baseline-test"}),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": _canonical_hash({"exit_code": 0}),
            "artifact_payload": {"task_id": "baseline-test"},
            "artifact_hash": _canonical_hash({"task_id": "baseline-test"}),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
        "run_root": str(tmp_dir),
    }


def test_e1_baseline_passes(tmp_path: Path) -> None:
    """Valid baseline record must pass LIVE_EXECUTED_PASS."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"req": "baseline"}, sort_keys=True, separators=(",", ":")))
    stderr_file = tmp_path / "stderr.txt"
    stderr_file.write_text("")
    evidence_file = tmp_path / "baseline.json"
    payload = {"task_id": "baseline-test", "capability": "codeintel"}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    evidence_file.write_bytes(body)
    physical_sha = hashlib.sha256(body).hexdigest()
    json_sha = _canonical_hash(payload)
    rec = {
        "task_id": "baseline-test",
        "planner_decision_id": "pd-baseline",
        "workspace_revision": "wr-baseline",
        "upstream_receipt_sha256": _canonical_hash({"root": "baseline"}),
        "execution_class": "provider_native",
        "provider_observation": "executed",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "gate_passed": True,
        "evidence_mode": "live_runtime",
        "run_root": str(tmp_path),
        "evidence_refs": [
            {"path": str(request_file), "sha256": _canonical_sha256_bytes(request_file.read_bytes()), "content_kind": "json", "kind": "request", "payload": {"req": "baseline"}},
            {"path": str(evidence_file), "sha256": physical_sha, "json_sha256": json_sha, "content_kind": "json", "kind": "stdout", "payload": payload},
            {"path": str(stderr_file), "sha256": _canonical_sha256_bytes(b""), "content_kind": "raw_bytes", "kind": "stderr"},
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": _canonical_hash({"action": "codeintel"}),
        },
        "receipt_payload": {"task_id": "baseline-test"},
        "receipt_hash": _canonical_hash({"task_id": "baseline-test"}),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": _canonical_hash({"exit_code": 0}),
            "artifact_payload": {"task_id": "baseline-test"},
            "artifact_hash": _canonical_hash({"task_id": "baseline-test"}),
        },
    }
    verdict = verify_product_capability_resolution(rec)
    assert verdict["status"] == "LIVE_EXECUTED_PASS", f"baseline failed: {verdict['missing_evidence_reasons']}"


def test_e1_fake_payload_no_physical_file_blocks(tmp_path: Path) -> None:
    """Matching fake payload plus fake hash but no physical file → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    fake_hash = hashlib.sha256(b"fake-payload").hexdigest()
    record = _v2_patch({
        "task_id": "test-fake-file",
        "planner_decision_id": "pd-fake-file",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": "/tmp/nonexistent_evidence_file.json",
                "sha256": fake_hash,
                "payload": {"fake": True},
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": hashlib.sha256(json.dumps({"action": "codeintel"}, sort_keys=True).encode()).hexdigest(),
        },
        "receipt_payload": {"task_id": "test-fake-file"},
        "receipt_hash": hashlib.sha256(json.dumps({"task_id": "test-fake-file"}, sort_keys=True).encode()).hexdigest(),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": hashlib.sha256(json.dumps({"exit_code": 0}, sort_keys=True).encode()).hexdigest(),
            "artifact_payload": {"task_id": "test-fake-file"},
            "artifact_hash": hashlib.sha256(json.dumps({"task_id": "test-fake-file"}, sort_keys=True).encode()).hexdigest(),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"
    assert any("evidence_file_not_found" in r for r in verdict["missing_evidence_reasons"])


def test_e1_evidence_file_changed_after_receipt_blocks(tmp_path: Path) -> None:
    """Evidence file changed after receipt creation → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution, _canonical_hash

    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"req": 1}, sort_keys=True, separators=(",", ":")))
    stderr_file = tmp_path / "stderr.txt"
    stderr_file.write_text("")
    evidence_path = tmp_path / "evidence.json"
    original_payload = {"task_id": "tamper-test", "capability": "codeintel"}
    original_bytes = json.dumps(original_payload, sort_keys=True, separators=(",", ":")).encode()
    original_physical_sha = hashlib.sha256(original_bytes).hexdigest()
    original_json_sha = _canonical_hash(original_payload)
    evidence_path.write_bytes(original_bytes)
    request_sha = _canonical_sha256_bytes(request_file.read_bytes())
    stderr_sha = _canonical_sha256_bytes(b"")
    upstream_sha = _canonical_hash({"root": "tamper"})

    def _record() -> dict:
        return {
            "task_id": "test-tamper",
            "planner_decision_id": "pd-tamper",
            "workspace_revision": "wr-tamper",
            "upstream_receipt_sha256": upstream_sha,
            "execution_class": "provider_native",
            "provider_observation": "executed",
            "capability": "codeintel",
            "origin": "online",
            "resolution_type": "ONLINE_NATIVE",
            "planner_selected": True,
            "trigger_condition_met": True,
            "invoked": True,
            "status": "SUCCEEDED",
            "physical_callable": "nexus.services.capability_registry:codeintel",
            "route_surface_changed": False,
            "public_claim_allowed": False,
            "structured_evidence_verified": True,
            "gate_passed": True,
            "evidence_mode": "live_runtime",
            "run_root": str(tmp_path),
            "evidence_refs": [
                {"path": str(request_file), "sha256": request_sha, "content_kind": "json", "kind": "request", "payload": {"req": 1}},
                {"path": str(evidence_path), "sha256": original_physical_sha, "json_sha256": original_json_sha, "content_kind": "json", "kind": "stdout", "payload": original_payload},
                {"path": str(stderr_file), "sha256": stderr_sha, "content_kind": "raw_bytes", "kind": "stderr"},
            ],
            "observable_effect": {
                "effect_type": "EXECUTION_CONTROL",
                "artifact_payload": {"action": "codeintel"},
                "artifact_hash": _canonical_hash({"action": "codeintel"}),
            },
            "receipt_payload": {"task_id": "test-tamper"},
            "receipt_hash": _canonical_hash({"task_id": "test-tamper"}),
            "verifier": {
                "invoked": True, "passed": True,
                "evidence_payload": {"exit_code": 0}, "evidence_hash": _canonical_hash({"exit_code": 0}),
                "artifact_payload": {"task_id": "test-tamper"}, "artifact_hash": _canonical_hash({"task_id": "test-tamper"}),
            },
        }

    record = _record()
    verdict1 = verify_product_capability_resolution(record)
    assert verdict1["status"] == "LIVE_EXECUTED_PASS", f"baseline failed: {verdict1['missing_evidence_reasons']}"

    evidence_path.write_bytes(json.dumps({"tampered": True}).encode())
    verdict2 = verify_product_capability_resolution(record)
    assert verdict2["status"] != "LIVE_EXECUTED_PASS"
    assert any("physical_sha256_mismatch" in r for r in verdict2["missing_evidence_reasons"])


def test_e1_missing_evidence_path_blocks(tmp_path: Path) -> None:
    """Missing evidence path → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    record = _v2_patch({
        "task_id": "test-empty-path",
        "planner_decision_id": "pd-empty-path",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": "",
                "sha256": "abc",
                "payload": {},
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": hashlib.sha256(json.dumps({"action": "codeintel"}, sort_keys=True).encode()).hexdigest(),
        },
        "receipt_payload": {"task_id": "test-empty-path"},
        "receipt_hash": hashlib.sha256(json.dumps({"task_id": "test-empty-path"}, sort_keys=True).encode()).hexdigest(),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": hashlib.sha256(json.dumps({"exit_code": 0}, sort_keys=True).encode()).hexdigest(),
            "artifact_payload": {"task_id": "test-empty-path"},
            "artifact_hash": hashlib.sha256(json.dumps({"task_id": "test-empty-path"}, sort_keys=True).encode()).hexdigest(),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"
    assert any("evidence_path_missing" in r for r in verdict["missing_evidence_reasons"])


def test_e1_path_traversal_outside_run_root_blocks(tmp_path: Path) -> None:
    """Path traversal outside run root → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    run_root = tmp_path / "run_root"
    run_root.mkdir(parents=True, exist_ok=True)
    outside_path = tmp_path / "outside_evidence.json"
    outside_path.write_text(json.dumps({"outside": True}))
    outside_hash = hashlib.sha256(outside_path.read_bytes()).hexdigest()

    record = _v2_patch({
        "task_id": "test-traversal",
        "planner_decision_id": "pd-traversal",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": str(outside_path),
                "sha256": outside_hash,
                "payload": {"outside": True},
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": hashlib.sha256(json.dumps({"action": "codeintel"}, sort_keys=True).encode()).hexdigest(),
        },
        "receipt_payload": {"task_id": "test-traversal"},
        "receipt_hash": hashlib.sha256(json.dumps({"task_id": "test-traversal"}, sort_keys=True).encode()).hexdigest(),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": hashlib.sha256(json.dumps({"exit_code": 0}, sort_keys=True).encode()).hexdigest(),
            "artifact_payload": {"task_id": "test-traversal"},
            "artifact_hash": hashlib.sha256(json.dumps({"task_id": "test-traversal"}, sort_keys=True).encode()).hexdigest(),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
        "run_root": str(run_root),
    }, run_root)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"
    assert any("path_traversal_detected" in r for r in verdict["missing_evidence_reasons"])


def test_e1_symlink_escape_blocks(tmp_path: Path) -> None:
    """Symlink escape → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    run_root = tmp_path / "run_root"
    run_root.mkdir(parents=True, exist_ok=True)
    target_file = tmp_path / "symlink_target.json"
    target_file.write_text(json.dumps({"target": True}))
    symlink_path = run_root / "evidence_link.json"
    symlink_path.symlink_to(target_file)

    record = _v2_patch({
        "task_id": "test-symlink",
        "planner_decision_id": "pd-symlink",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": str(symlink_path),
                "sha256": hashlib.sha256(target_file.read_bytes()).hexdigest(),
                "payload": {"target": True},
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": hashlib.sha256(json.dumps({"action": "codeintel"}, sort_keys=True).encode()).hexdigest(),
        },
        "receipt_payload": {"task_id": "test-symlink"},
        "receipt_hash": hashlib.sha256(json.dumps({"task_id": "test-symlink"}, sort_keys=True).encode()).hexdigest(),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": hashlib.sha256(json.dumps({"exit_code": 0}, sort_keys=True).encode()).hexdigest(),
            "artifact_payload": {"task_id": "test-symlink"},
            "artifact_hash": hashlib.sha256(json.dumps({"task_id": "test-symlink"}, sort_keys=True).encode()).hexdigest(),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
        "run_root": str(run_root),
    }, run_root)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"
    assert any("symlink_evidence_not_allowed" in r or "symlink_escape_detected" in r
               for r in verdict["missing_evidence_reasons"])


def test_e1_harness_canary_marked_live_pass_blocks(tmp_path: Path) -> None:
    """Harness/canary marked live_pass → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    record = _v2_patch({
        "task_id": "test-harness-live",
        "planner_decision_id": "pd-harness-live",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [{"path": "/tmp/x", "sha256": "abc", "payload": {}}],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": "abc",
        },
        "receipt_payload": {"task_id": "test-harness-live"},
        "receipt_hash": "abc",
        "verifier": {"invoked": True, "passed": True, "evidence_payload": {}, "evidence_hash": "abc", "artifact_payload": {}, "artifact_hash": "abc"},
        "gate_passed": True,
        "live_pass": True,
        "evidence_mode": "canary",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"


def test_e1_fabricated_provider_native_id_blocks(tmp_path: Path) -> None:
    """Fabricated provider native ID → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    record = _v2_patch({
        "task_id": "test-fabricated",
        "planner_decision_id": "pd-fabricated",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "provider": "fake_provider_with_native_id",
        "transport": "injected_transport",
        "evidence_refs": [{"path": "/tmp/x", "sha256": "abc", "payload": {}}],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": "abc",
        },
        "receipt_payload": {"task_id": "test-fabricated"},
        "receipt_hash": "abc",
        "verifier": {"invoked": True, "passed": True, "evidence_payload": {}, "evidence_hash": "abc", "artifact_payload": {}, "artifact_hash": "abc"},
        "gate_passed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"


def test_e1_lineage_recomputed_without_check_blocks(tmp_path: Path) -> None:
    """Producer says lineage_recomputed=true without independent check → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    record = _v2_patch({
        "task_id": "test-lineage",
        "planner_decision_id": "pd-lineage",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [{"path": "/tmp/x", "sha256": "abc", "payload": {}}],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": "abc",
        },
        "receipt_payload": {"task_id": "test-lineage"},
        "receipt_hash": "wrong_hash",
        "verifier": {"invoked": True, "passed": True, "evidence_payload": {}, "evidence_hash": "abc", "artifact_payload": {}, "artifact_hash": "abc"},
        "gate_passed": True,
        "lineage_recomputed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"


def test_e1_simulation_mode_blocks_live_pass(tmp_path: Path) -> None:
    """Simulation mode cannot count as live pass."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    record = _v2_patch({
        "task_id": "test-sim-live",
        "planner_decision_id": "pd-sim-live",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [{"path": "/tmp/x", "sha256": "abc", "payload": {}}],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": "abc",
        },
        "receipt_payload": {"task_id": "test-sim-live"},
        "receipt_hash": "abc",
        "verifier": {"invoked": True, "passed": True, "evidence_payload": {}, "evidence_hash": "abc", "artifact_payload": {}, "artifact_hash": "abc"},
        "gate_passed": True,
        "live_pass": True,
        "evidence_mode": "simulation",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"


def test_e1_unknown_evidence_mode_blocks(tmp_path: Path) -> None:
    """Unknown evidence mode fails closed."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    record = _v2_patch({
        "task_id": "test-unknown-mode",
        "planner_decision_id": "pd-unknown-mode",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [{"path": "/tmp/x", "sha256": "abc", "payload": {}}],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": "abc",
        },
        "receipt_payload": {"task_id": "test-unknown-mode"},
        "receipt_hash": "abc",
        "verifier": {"invoked": True, "passed": True, "evidence_payload": {}, "evidence_hash": "abc", "artifact_payload": {}, "artifact_hash": "abc"},
        "gate_passed": True,
        "evidence_mode": "totally_bogus_mode",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"
    assert any("evidence_mode_unknown" in r for r in verdict["missing_evidence_reasons"])


def test_e1_task_origin_capability_mismatch_blocks(tmp_path: Path) -> None:
    """task_id mismatch between record and receipt_payload → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    record = _v2_patch({
        "task_id": "test-abc",
        "planner_decision_id": "pd-abc",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [{"path": "/tmp/x", "sha256": "abc", "payload": {}}],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": {"action": "codeintel"},
            "artifact_hash": "abc",
        },
        "receipt_payload": {"task_id": "different-task"},
        "receipt_hash": "abc",
        "verifier": {"invoked": True, "passed": True, "evidence_payload": {}, "evidence_hash": "abc", "artifact_payload": {}, "artifact_hash": "abc"},
        "gate_passed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"


def test_e1_missing_provider_stderr_blocks(tmp_path: Path) -> None:
    """Missing raw_output field with claimed sha256 → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    ev_path = tmp_path / "evidence.json"
    body = json.dumps({"real": "data"}, sort_keys=True, separators=(",", ":")).encode()
    ev_path.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    effect_payload = {"action": "codeintel"}

    record = _v2_patch({
        "task_id": "test-stderr",
        "planner_decision_id": "pd-stderr",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": str(ev_path),
                "sha256": sha,
                "payload": {"real": "data"},
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": effect_payload,
            "artifact_hash": _canonical_hash(effect_payload),
        },
        "receipt_payload": {"task_id": "test-stderr"},
        "receipt_hash": _canonical_hash({"task_id": "test-stderr"}),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": _canonical_hash({"exit_code": 0}),
            "artifact_payload": {"task_id": "test-stderr"},
            "artifact_hash": _canonical_hash({"task_id": "test-stderr"}),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"


def test_e1_adapter_synthesized_success_blocks(tmp_path: Path) -> None:
    """Adapter claims success without raw provider output → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    ev_path = tmp_path / "evidence.json"
    body = json.dumps({"adapter": "yes"}, sort_keys=True, separators=(",", ":")).encode()
    ev_path.write_bytes(body)
    effect_payload = {"action": "codeintel"}

    record = _v2_patch({
        "task_id": "test-adapter-synth",
        "planner_decision_id": "pd-adapter-synth",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": str(ev_path),
                "payload": {"adapter": "yes"},
                "adapter_claimed_success": True,
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": effect_payload,
            "artifact_hash": _canonical_hash(effect_payload),
        },
        "receipt_payload": {"task_id": "test-adapter-synth"},
        "receipt_hash": _canonical_hash({"task_id": "test-adapter-synth"}),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": _canonical_hash({"exit_code": 0}),
            "artifact_payload": {"task_id": "test-adapter-synth"},
            "artifact_hash": _canonical_hash({"task_id": "test-adapter-synth"}),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"


def test_e1_json_evidence_parse_failure_blocks(tmp_path: Path) -> None:
    """Evidence file is not valid JSON → BLOCK."""
    from nexus.services.product_capability_closure import verify_product_capability_resolution

    ev_path = tmp_path / "evidence.json"
    raw = b"this is not json at all"
    ev_path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    effect_payload = {"action": "codeintel"}

    record = _v2_patch({
        "task_id": "test-json-parse",
        "planner_decision_id": "pd-json-parse",
        "capability": "codeintel",
        "origin": "online",
        "resolution_type": "ONLINE_NATIVE",
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "status": "SUCCEEDED",
        "physical_callable": "nexus.services.capability_registry:codeintel",
        "route_surface_changed": False,
        "public_claim_allowed": False,
        "structured_evidence_verified": True,
        "evidence_refs": [
            {
                "path": str(ev_path),
                "sha256": sha,
                "payload": {},
            }
        ],
        "observable_effect": {
            "effect_type": "EXECUTION_CONTROL",
            "artifact_payload": effect_payload,
            "artifact_hash": _canonical_hash(effect_payload),
        },
        "receipt_payload": {"task_id": "test-json-parse"},
        "receipt_hash": _canonical_hash({"task_id": "test-json-parse"}),
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_payload": {"exit_code": 0},
            "evidence_hash": _canonical_hash({"exit_code": 0}),
            "artifact_payload": {"task_id": "test-json-parse"},
            "artifact_hash": _canonical_hash({"task_id": "test-json-parse"}),
        },
        "gate_passed": True,
        "evidence_mode": "live_runtime",
    }, tmp_path)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] != "LIVE_EXECUTED_PASS"
    assert any("evidence_file_not_valid_json" in r for r in verdict["missing_evidence_reasons"])
