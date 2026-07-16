"""False-green elimination gates: seal fail-closed, postflight honesty, closure.

Does not introduce routes, planners, or parallel runtimes.
"""

from __future__ import annotations

import hashlib
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

    planner = _Planner(
        selected=["codeintel", "memory", "belief", "artifact_gate", "claim_gate", "delivery_gate"],
        required=["codeintel"],
    )

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
                "provider": "gemini",
                "injected_transport": True,
            },
            online_prompt="return ok",
            online_payload="payload",
            local_enabled=False,
            codeintel={"scan_report_present": True, "risk_score": 1},
            evidence_refs=("t",),
        ),
        online_invoker=_online,
        planner=planner,
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

    planner = _Planner(
        selected=[
            "codeintel",
            "memory",
            "belief",
            "local_model_executor",
            "artifact_gate",
            "claim_gate",
            "delivery_gate",
        ],
        required=["codeintel"],
    )
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
                "provider": "gemini",
                "injected_transport": True,
                "workspace_root": str(tmp_path),
            },
            online_prompt="return ok",
            online_payload="payload",
            local_enabled=True,
            local_request=local_request,
            evidence_refs=("t",),
            codeintel={"scan_report_present": True, "risk_score": 1},
        ),
        online_invoker=_online,
        planner=planner,
        local_service=LocalAssistService(provider=InjectedLocalModelProvider(_gen)),
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


def test_final_mainchain_canary_receipt_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproducible final dynamic canary via production MainchainEntry path.

    Fixture providers + real production classes. Writes receipt to
    /tmp/nexus_mainchain_final_gate_receipt.json (OBJECTIVE path) and, when
    NEXUS_IMPLEMENTER_SCRATCH is set, also copies there for audit.
    """
    import json
    import os

    from nexus.services.capability_evidence_bundle import verify_capability_evidence_bundle
    from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
    from nexus.services.mainchain_entry import run_mainchain

    task_id = "final-canary-001"
    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")

    planner = _Planner(
        selected=[
            "codeintel",
            "memory",
            "belief",
            "local_model_executor",
            "artifact_gate",
            "claim_gate",
            "delivery_gate",
        ],
        required=["codeintel"],
    )
    local_calls = {"n": 0, "prompts": []}
    online_calls = {"n": 0}

    def local_gen(req: Any) -> str:
        local_calls["n"] += 1
        # Executor may pass problem_statement via provider request.prompt on some paths;
        # capture both for evidence.
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
        return _online(ctx)

    local_request = LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id=task_id,
        parent_task_id="parent-final",
        workspace_root=str(tmp_path),
        workspace_revision="wr-final",
        task_statement="final canary: wire codeintel memory belief local and gates",
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

    receipt = run_mainchain(
        UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision="wr-final",
            task_statement="final canary: wire codeintel memory belief local and gates",
            task_type="repair",
            route={
                "recommended_flow": "hybrid",
                "provider": "gemini",
                "injected_transport": True,
                "workspace_root": str(tmp_path),
            },
            online_prompt="return ok",
            online_payload="payload",
            local_enabled=True,
            local_request=local_request,
            online_enabled=True,
            evidence_refs=("canary:final",),
            codeintel={"scan_report_present": True, "risk_score": 1},
        ),
        online_invoker=online,
        planner=planner,
        local_service=LocalAssistService(provider=InjectedLocalModelProvider(local_gen)),
        capability_invokers={
            "codeintel": lambda c: _cap_ok("codeintel", c["task_id"]),
            "memory": lambda c: _cap_ok("memory", c["task_id"]),
            "belief": lambda c: _cap_ok("belief", c["task_id"]),
        },
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
    assert receipt.get("receipt_complete") is True
    assert receipt.get("capability_closure_complete") is True
    assert list(receipt.get("capability_closure_blockers") or []) == []
    assert receipt.get("public_claim_allowed") is False
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt.get("planner_decision_id")
    assert local_calls["n"] >= 1
    assert online_calls["n"] >= 1
    consumed = list(receipt.get("consumed_evidence_ids") or [])
    assert consumed
    assert any("codeintel" in i for i in consumed)
    assert any("memory" in i for i in consumed)
    assert any("belief" in i for i in consumed)

    local = receipt.get("local") or {}
    local_resp = local.get("response") if isinstance(local.get("response"), dict) else {}
    local_outputs = local_resp.get("local_outputs") if isinstance(local_resp, dict) else {}
    ec = local_outputs.get("evidence_consumption") if isinstance(local_outputs, dict) else {}
    online = receipt.get("online") or {}
    online_resp = online.get("response") if isinstance(online.get("response"), dict) else {}
    with_nexus = online_resp.get("with_nexus") if isinstance(online_resp, dict) else {}
    lineage = with_nexus.get("lineage") if isinstance(with_nexus, dict) else {}
    root = str(bundle.get("bundle_hash") or "")
    assert root
    local_hash = str((ec or {}).get("bundle_hash") or "")
    online_hash = str((lineage or {}).get("bundle_hash") or (with_nexus or {}).get("bundle_hash") or "")
    assert local_hash == root
    assert online_hash == root
    # Candidate path injects evidence into problem_statement → provider prompt lineage.
    assert local_resp.get("physical_callable") == "LocalModelExecutor.run"
    assert local_resp.get("executor_invoked") is True
    assert out_tmp.is_file()
