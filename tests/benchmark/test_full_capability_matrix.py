"""P7 full capability matrix — causal acceptance for runtime-eligible capabilities.

Not a report artifact. Asserts A/B/C/D/unclassified/consumer gaps for the
Planner∪SPXDRAC catalog under the frozen mainchain, and requires physical
executor success for every runtime-eligible production/beta row.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import get_executor
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.capability_evidence_bundle import (
    record_consumption,
    verify_capability_evidence_bundle,
)
from nexus.services.capability_registry import (
    ESCALATE_ONLY,
    EXECUTOR_REGISTRY_ALIASES,
    build_default_mainchain_invokers,
    classify_gap,
    list_planner_capability_names,
)
from nexus.services.mainchain_route_freeze import build_capability_catalog
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
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


class _SelectPlanner:
    def __init__(self, selected: list[str]) -> None:
        self._selected = list(selected)

    def plan(self, **_: object) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=list(self._selected),
            required_capabilities=list(self._selected[:1]),
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


def test_catalog_union_accounted_and_historical_classified() -> None:
    root = Path(__file__).resolve().parents[2]
    catalog = build_capability_catalog(repo_root=root)
    assert catalog["union_unaccounted_count"] == 0
    assert catalog["legacy_inventory_unclassified_count"] == 0
    assert catalog["canonical_union_count"] == catalog["union_accounted_count"]
    assert catalog["selection_authority"] == "CapabilityPlanner"
    assert catalog["alias_validation"]["ok"] is True


def test_production_f_executors_have_no_synthetic_claim_theater() -> None:
    """Registry production executors must not hardcode synthetic claim proofs."""
    import inspect

    from nexus.core import capability_executor_registry as cer
    from nexus.services.capability_registry import WIRED_REAL, classify_gap

    # claim_gate body: no synthetic theater *assignments*
    src = inspect.getsource(cer._exec_claim_gate)
    for banned in (
        'source_hash="abc123"',
        "source_hash='abc123'",
        "owner_approved=True",
        "candidate_hash_matches_applied=True",
        "--- a/file.py",
        "sha256:testdeterministic",
    ):
        assert banned not in src, banned

    # belief must not wrap no_evaluate as success path
    belief_src = inspect.getsource(cer._exec_belief)
    assert "no_evaluate" not in belief_src or "error" in belief_src
    assert "assess_confidence" in belief_src

    # Every F_wired_ok name still classifies honestly
    for name in sorted(WIRED_REAL):
        assert classify_gap(name) == "F_wired_ok", name


def test_postflight_gates_point_to_strict_postflight_callable() -> None:
    """artifact/claim/delivery catalog rows must point at evaluate_postflight_gate."""
    from nexus.services.capability_registry import build_wiring_matrix

    matrix = build_wiring_matrix()
    by_name = {r["name"]: r for r in matrix["rows"]}
    for name in ("artifact_gate", "claim_gate", "delivery_gate"):
        row = by_name[name]
        assert row["gap_class"] == "F_wired_ok", (name, row)
        assert row["handler_kind"] == "postflight_evaluator", (name, row["handler_kind"])
        hint = str(row.get("physical_callable_hint") or "")
        assert "online_nexus_context.evaluate_postflight_gate" in hint, (name, hint)
        assert not hint.startswith("capability_executor_registry:"), (name, hint)


def test_runtime_eligible_gap_classes_zero_abcd() -> None:
    """Final Gate bar for runtime-eligible production/beta rows."""
    root = Path(__file__).resolve().parents[2]
    catalog = build_capability_catalog(repo_root=root)
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for row in catalog["rows"]:
        if not row.get("runtime_eligible"):
            continue
        gap = str(row.get("gap_class") or classify_gap(row["canonical_id"]))
        if gap == "A_missing_invoker":
            counts["A"] += 1
        elif gap == "B_stub_only":
            counts["B"] += 1
        elif gap == "C_not_in_prompt":
            counts["C"] += 1
        elif gap == "D_selected_not_executed":
            counts["D"] += 1
        # Eligible rows must be F-wired (or Local stage)
        assert gap == "F_wired_ok", (row["canonical_id"], gap)
    assert counts["A"] == 0, counts
    assert counts["B"] == 0, counts
    assert counts["C"] == 0, counts
    assert counts["D"] == 0, counts


def test_runtime_eligible_production_beta_physical_executor_success() -> None:
    """Every runtime-eligible production/beta capability has a working physical path.

    Not just gap_class reclassification — get_executor (or built-in pre/post/local)
    must invoke without structural stub.
    """
    root = Path(__file__).resolve().parents[2]
    catalog = build_capability_catalog(repo_root=root)
    invokers = build_default_mainchain_invokers()
    builtins = {
        "codeintel",
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
        "local_model_executor",
    }
    failures: list[str] = []
    for row in catalog["rows"]:
        if not row.get("runtime_eligible"):
            continue
        name = str(row["canonical_id"])
        maturity = str(row.get("maturity") or "").lower()
        if maturity in {"experimental", "deprecated", "legacy_alias"}:
            failures.append(f"{name}:eligible_but_maturity={maturity}")
            continue

        # Physical registry presence (alias-aware) except built-ins / local stage
        if name not in builtins:
            reg_key = EXECUTOR_REGISTRY_ALIASES.get(name, name)
            # Some builtins registered under same name
            if get_executor(reg_key) is None and get_executor(name) is None:
                # Built-in postflight physical callables are allowed
                if "postflight" not in str(row.get("executor") or "") and "Local" not in str(
                    row.get("executor") or ""
                ):
                    failures.append(f"{name}:missing_get_executor")
                    continue
            ex = get_executor(reg_key) or get_executor(name)
            if ex is not None:
                plan = CapabilityExecutionPlan(
                    plan_id=f"matrix:{name}",
                    task_id=f"matrix-{name}",
                    phases=["R"],
                )
                receipt = ex(plan, f"matrix probe {name}")
                if not bool(getattr(receipt, "invoked", False)):
                    failures.append(f"{name}:executor_not_invoked:{getattr(receipt,'outcome',{})}")
                    continue
                if not str(getattr(receipt, "evidence_id", "") or ""):
                    failures.append(f"{name}:missing_evidence_id")
                # P4: import/construct alone is never real execution.
                outcome = getattr(receipt, "outcome", None) or {}
                if not isinstance(outcome, dict):
                    outcome = {}
                action = str(outcome.get("action") or "")
                shallow_keys = (
                    "class_instantiated",
                    "function_found",
                    "symbol_resolved",
                )
                shallow_actions = {
                    "resolve_service",
                    "resolve_module",
                    "resolve_providers",
                    "construct",
                    "resolve",
                    "should_run",
                    "health_check",
                    "bind",
                    "cleanup",
                    "hash_fallback",
                    "import_success",
                    "probe",
                    "fixture",
                    "deterministic_confidence_probe",
                }
                if (
                    any(outcome.get(k) for k in shallow_keys) and not action
                ) or action in shallow_actions:
                    failures.append(f"{name}:shallow_import_only:{outcome}")
                    continue
                if not action and not outcome.get("error"):
                    # Physical probe must name the method/action that ran.
                    failures.append(f"{name}:missing_physical_action:{outcome}")
                    continue

        # Mainchain invoker must not be structural stub
        inv = invokers.get(name)
        if inv is None:
            failures.append(f"{name}:missing_mainchain_invoker")
            continue
        ctx: dict[str, Any] = {
            "task_id": f"m-{name}",
            "task_statement": f"probe {name}",
            "planner": {},
            "codeintel": {"scan_report_present": True, "risk_score": 1},
            "online": {
                "invoked": True,
                "response": {"artifact_hash": "a1"},
            },
            "verifier": {
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"v:m-{name}"],
                "verifier_status": "pass",
                "verifier_artifact": f"sha256:matrixverifierartifact{name[:8]}0001",
            },
            "capability_evidence_bundle": {
                "source_hash": "src_hash_for_matrix_probe_01",
                "bundle_hash": "bh",
            },
            "source_hash": "src_hash_for_matrix_probe_01",
            "task_statement": f"probe {name}",
        }
        if name in ESCALATE_ONLY:
            ctx["escalate_triggered"] = True
        result = inv(ctx)
        if result.get("stub"):
            failures.append(f"{name}:structural_stub")
        if name in ESCALATE_ONLY:
            # triggered: real or BLOCKED, never stub
            if result.get("skipped") and "POLICY" in str(result.get("skip_reason") or "").upper():
                failures.append(f"{name}:policy_skip_while_triggered")
        elif name != "local_model_executor":
            if result.get("skipped") and result.get("skip_reason") == "not_implemented_mainchain_v1":
                failures.append(f"{name}:not_implemented_skip")
            if not result.get("invoked") and not result.get("skipped"):
                # postflight may fail gate but must still invoke
                if name not in {"artifact_gate", "claim_gate", "delivery_gate"}:
                    failures.append(f"{name}:not_invoked:{result.get('status')}")

    assert failures == [], failures


def test_planner_gap_matrix_no_silent_missing_or_stub_success() -> None:
    """Every planner node has a handler; residual A/B/C/D only if honest."""
    names = list_planner_capability_names()
    invokers = build_default_mainchain_invokers()
    assert set(invokers.keys()) == set(names)

    a = b = c = d = 0
    for name in names:
        gap = classify_gap(name)
        if gap == "A_missing_invoker":
            a += 1
        elif gap == "B_stub_only":
            b += 1
        elif gap == "C_not_in_prompt":
            c += 1
        elif gap == "D_selected_not_executed":
            d += 1
        result = invokers[name](
            {
                "task_id": f"m-{name}",
                "task_statement": f"probe {name}",
                "planner": {},
            }
        )
        if result.get("stub"):
            assert result.get("outcome_contributed") is False
        if result.get("skipped"):
            assert result.get("skip_reason")
            assert result.get("evidence_refs")
    # Final Gate residual bar for the whole planner surface
    assert a == 0
    assert b == 0
    assert c == 0
    assert d == 0


def test_capability_on_off_and_negative_control_for_real_wired() -> None:
    """Off baseline vs on arm for a real-wired capability (codeintel)."""
    off_receipt = UnifiedRuntime(
        planner=_SelectPlanner(["artifact_gate", "claim_gate", "delivery_gate"])
    ).run(
        UnifiedRuntimeRequest(
            task_id="matrix-off",
            workspace_revision="r",
            task_statement="scan impact risk",
            task_type="codeintel",
            route={
                "recommended_flow": "direct",
                "injected_transport": True,
                "online_policy": "auto",
                "mainchain_entry": True,
            },
            online_enabled=True,
            online_prompt="task",
            codeintel={"scan_report_present": True, "risk_score": 2},
        ),
        online_invoker=_online,
        verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"v:{c['task_id']}"],
        },
        learning=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"l:{c['task_id']}"],
        },
    )
    off_caps = {r["name"] for r in off_receipt["capabilities"]}
    assert "codeintel" not in off_caps

    on_receipt = UnifiedRuntime(
        planner=_SelectPlanner(
            ["codeintel", "artifact_gate", "claim_gate", "delivery_gate"]
        )
    ).run(
        UnifiedRuntimeRequest(
            task_id="matrix-on",
            workspace_revision="r",
            task_statement="scan impact risk codeintel",
            task_type="codeintel",
            route={
                "recommended_flow": "direct",
                "injected_transport": True,
                "online_policy": "auto",
                "mainchain_entry": True,
            },
            online_enabled=True,
            online_prompt="task",
            codeintel={"scan_report_present": True, "risk_score": 2},
        ),
        online_invoker=_online,
        verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"v:{c['task_id']}"],
        },
        learning=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"l:{c['task_id']}"],
        },
    )
    rows = {r["name"]: r for r in on_receipt["capabilities"]}
    assert "codeintel" in rows
    assert rows["codeintel"]["invoked"] is True
    assert rows["codeintel"].get("evidence_refs")
    assert on_receipt["claim_boundary"]["public_claim_allowed"] is False

    bundle = on_receipt["capability_evidence_bundle"]
    assert verify_capability_evidence_bundle(bundle)["ok"] is True
    cons = record_consumption(
        bundle=bundle, consumer="Online", consumed_evidence_ids=[]
    )
    assert cons["capability_consumed"] is False


def test_escalation_trigger_off_and_on() -> None:
    """Escalation-only: untriggered policy skip; triggered real or BLOCKED."""
    invokers = build_default_mainchain_invokers()
    name = "swarm"
    assert name in ESCALATE_ONLY
    off = invokers[name]({"task_id": "esc-off", "task_statement": "x", "planner": {}})
    assert off.get("skipped") is True
    assert off.get("skip_reason")

    on = invokers[name](
        {
            "task_id": "esc-on",
            "task_statement": "x",
            "planner": {},
            "escalate_triggered": True,
        }
    )
    assert on.get("stub") is not True
    if on.get("invoked"):
        assert on.get("physical_callable")
        assert on.get("evidence_refs") or on.get("evidence_ids")
    else:
        assert "BLOCKED" in str(on.get("status") or on.get("reason") or "")


def test_formal_callers_use_mainchain_entry_contract() -> None:
    """P6 sample: MainchainEntry path keeps single planner_decision_id."""
    from nexus.services.mainchain_entry import run_mainchain, stamp_mainchain_route

    route = stamp_mainchain_route({"recommended_flow": "direct"}, product_entry="gateway")
    assert route["mainchain_entry"] is True
    assert route["with_nexus_armor"] is True

    receipt = run_mainchain(
        UnifiedRuntimeRequest(
            task_id="caller-1",
            workspace_revision="r",
            task_statement="scan impact risk codeintel",
            task_type="codeintel",
            route={
                "recommended_flow": "direct",
                "injected_transport": True,
                "online_policy": "auto",
                "mainchain_entry": True,
            },
            online_enabled=True,
            online_prompt="task",
            codeintel={"scan_report_present": True, "risk_score": 1},
        ),
        online_invoker=_online,
        planner=_SelectPlanner(
            ["codeintel", "artifact_gate", "claim_gate", "delivery_gate"]
        ),
        verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"v:{c['task_id']}"],
        },
        learning=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"l:{c['task_id']}"],
        },
    )
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt["planner_decision_id"]
    assert (
        receipt["capability_evidence_bundle"]["planner_decision_id"]
        == receipt["planner_decision_id"]
    )
