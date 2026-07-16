"""Mainchain capability registry (FCM F0+F1) — ROUTING FREEZE.

Maps CapabilityPlanner node names to UnifiedRuntime invokers.
Does **not** introduce execution_topology / RouteMode / product selectors.

Contract:
  selected → invoke(real) | skip(explicit reason) → evidence_refs on receipt
  Never silently omit a selected capability.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from nexus.engine.capability_planner import default_capability_nodes

# Whitelist skip reasons (receipt contract)
SKIP_NOT_IMPLEMENTED = "not_implemented_mainchain_v1"
SKIP_ESCALATE_ONLY = "escalate_only_not_default_online_stage"
SKIP_LOCAL_STAGE = "delegated_to_local_stage"
SKIP_ONLINE_ARMOR = "delegated_to_online_armor_or_flags"
SKIP_LEGACY_ALIAS = "legacy_alias_no_separate_invoker"
SKIP_CALLER_OMITTED = "caller_omitted_auto_skip"
SKIP_POLICY_NOT_TRIGGERED = "SKIPPED_POLICY_NOT_TRIGGERED"
BLOCKED_EXECUTOR_UNAVAILABLE = "BLOCKED_EXECUTOR_UNAVAILABLE"

SKIP_REASONS = frozenset(
    {
        SKIP_NOT_IMPLEMENTED,
        SKIP_ESCALATE_ONLY,
        SKIP_LOCAL_STAGE,
        SKIP_ONLINE_ARMOR,
        SKIP_LEGACY_ALIAS,
        SKIP_CALLER_OMITTED,
        SKIP_POLICY_NOT_TRIGGERED,
        BLOCKED_EXECUTOR_UNAVAILABLE,
    }
)

# Planner canonical id → capability_executor_registry key (semantic reuse only).
EXECUTOR_REGISTRY_ALIASES: dict[str, str] = {
    "mempalace_gate": "mempalace",
    "hyper": "hyper_sprint",
    "swarm": "swarm_multi_agent",
    "multi_agent": "swarm_multi_agent",
    "meta_opt": "benchmark_meta_opt",
    "file_lock": "file_lock_security_gate",
    "forecast_gate": "forecast_pregate",
    "registry_sync": "registry_skills_sync",
    "learn_scheduler": "learn_scheduler_service",
    "metabolism": "metabolism_resume",
    "direct_mode": "direct_master_loop",
    "sandbox": "sandbox_runner",
    "research_route": "research",
}

GAP_CLASSES = frozenset(
    {
        "A_missing_invoker",
        "B_stub_only",
        "C_not_in_prompt",
        "D_selected_not_executed",
        "E_escalate_ok",
        "F_wired_ok",
    }
)

# L5: never default Online stages — explicit skip when selected without escalate trigger.
ESCALATE_ONLY: frozenset[str] = frozenset(
    {
        "hyper",
        "nightshift",
        "swarm",
        "drone",
        "multi_agent",
        "integration_manager",
        "oracle_shadow",
        "ultra_review",  # full ultra; dry flags may still appear in guidance
        "committee",
        "federation",
        "metabolism",
        "stress_test",
        "ui_validator",
        "registry_sync",
        "meta_opt",
        "research_control_plane",
        "benchmark",
        "forecast_gate",
        "formal_report",
        "asi_constraint_extractor",
        "architecture_scout",
        "external_doc_scout",
        "xray",
        "msa_router",
        "autonomic_router",
        "direct_mode",
        "file_lock",
        "prompt_compression",
        "learn_scheduler",
        "swarm_quiet_moment",
    }
)

# Handled by Local stage, not a preflight invoker map entry that "runs" Online.
LOCAL_STAGE_CAPABILITIES: frozenset[str] = frozenset({"local_model_executor"})

# Online armor / executor flags path (flags in prompt; not separate preflight callable yet).
ONLINE_ARMOR_FLAG_CAPABILITIES: frozenset[str] = frozenset(
    {
        "autoreason",
        "ddtree",
        "judge_panel",
        "llm_judge_panel",
        "repair_loop",
    }
)

# Real production-quality invokers available on mainchain today (honest F).
# Presence of get_executor alone is NOT enough — must be production engine callable.
WIRED_REAL: frozenset[str] = frozenset(
    {
        "codeintel",
        "memory",
        "belief",
        "lancedb",
        "semantic_searcher",
        "repair_loop",
        "sandbox",
        "mempalace_gate",
        "acceptance_check",
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
        "harness_preflight_sensor",
        "jit_validation",
        "plan_quality_gate",
        "pregate",
    }
)

# Registered executors that only probe/health/should_run — not F_wired_ok.
# Reclassified to E_escalate_ok with explicit reason_code.
PROBE_ONLY_REASON_CODES: dict[str, str] = {
    "research": "shallow_should_run_only",
    "research_route": "shallow_should_run_only",
    "drone": "shallow_health_check_only",
    "hyper": "escalate_probe_or_unavailable",
    "swarm": "escalate_probe_or_unavailable",
    "multi_agent": "escalate_probe_or_unavailable",
    "nightshift": "escalate_probe_or_unavailable",
    "ultra_review": "escalate_probe_or_unavailable",
    "autonomic_router": "route_probe_not_production_execute",
    "autoreason": "requires_model_execution_boundary",
    "ddtree": "requires_model_execution_boundary",
    "judge_panel": "requires_model_execution_boundary",
    "llm_judge_panel": "requires_model_execution_boundary",
    "learn_mode": "scheduler_probe_not_production",
    "learn_phase_slo": "scheduler_probe_not_production",
    "learn_scheduler": "scheduler_probe_not_production",
    "metabolism": "resume_probe_not_production",
    "bdd_acceptance_skill": "skill_probe_not_production",
    "semantic_failure_sensor": "sensor_probe_not_production",
}

# Historical stub set retained for documentation only.
# Any name that has a physical get_executor is F-wired and is NOT treated as stub.
# Empty means: no residual structural-stub-only production path on mainchain.
WIRED_STUB: frozenset[str] = frozenset()

CapabilityInvoker = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def list_planner_capability_names() -> tuple[str, ...]:
    nodes = default_capability_nodes()
    return tuple(sorted(str(name) for name in nodes.keys()))


def _node_meta(name: str) -> dict[str, Any]:
    nodes = default_capability_nodes()
    node = nodes.get(name)
    if node is None:
        return {
            "name": name,
            "maturity": "unknown",
            "category": "unknown",
            "default_state": "optional",
        }
    return {
        "name": str(getattr(node, "name", name)),
        "maturity": str(getattr(node, "maturity", "") or "unknown"),
        "category": str(getattr(node, "category", "") or "unknown"),
        "default_state": str(getattr(node, "default_state", "") or "optional"),
        "cost": int(getattr(node, "cost", 0) or 0),
        "benefit": int(getattr(node, "benefit", 0) or 0),
    }


def _has_physical_executor(name: str) -> bool:
    try:
        from nexus.core.capability_executor_registry import get_executor

        return get_executor(_resolve_executor_registry_key(name)) is not None
    except Exception:
        return False


def classify_gap(name: str) -> str:
    """Closed enum gap_class for F0 matrix — honest, no reclass cheat.

    F: production physical engine callable (not probe/health/should_run alone)
    B: structural stub only (no physical executor)
    C: online armor flag only (no physical executor)
    E: escalate-only / probe-only reclassified path (trigger-gated)
    A: missing invoker entirely
    """
    key = str(name or "").strip()
    if key in LOCAL_STAGE_CAPABILITIES:
        return "F_wired_ok"
    if key in PROBE_ONLY_REASON_CODES:
        return "E_escalate_ok"
    if key in WIRED_REAL:
        return "F_wired_ok"
    # get_executor alone is insufficient for F — must be in WIRED_REAL production set.
    if key in ESCALATE_ONLY or key == "llm_judge_panel":
        return "E_escalate_ok"
    if _has_physical_executor(key):
        # Registered but not audited as production → escalate/probe class.
        return "E_escalate_ok"
    if key in ONLINE_ARMOR_FLAG_CAPABILITIES:
        return "C_not_in_prompt"
    if key in WIRED_STUB:
        return "B_stub_only"
    return "A_missing_invoker"


def physical_runtime_eligible_count() -> int:
    """Honest count of production-physical F_wired_ok capabilities (not forced 91)."""
    names = list_planner_capability_names()
    return sum(1 for n in names if classify_gap(n) == "F_wired_ok")


def build_wiring_matrix() -> dict[str, Any]:
    """F0: machine-readable inventory of all planner capability nodes."""
    names = list_planner_capability_names()
    rows: list[dict[str, Any]] = []
    for name in names:
        meta = _node_meta(name)
        gap = classify_gap(name)
        escalate = name in ESCALATE_ONLY or name in PROBE_ONLY_REASON_CODES
        has_exec = _has_physical_executor(name)
        reason_code = str(PROBE_ONLY_REASON_CODES.get(name) or "")
        if name in LOCAL_STAGE_CAPABILITIES:
            handler = "local_stage"
            has_invoker = True
            feeds_online = True
        elif name in WIRED_REAL and gap == "F_wired_ok":
            handler = "real_invoker"
            has_invoker = True
            feeds_online = True
        elif name in WIRED_STUB and not has_exec:
            handler = "stub_invoker"
            has_invoker = True
            feeds_online = True  # compact may be thin
        elif name in ONLINE_ARMOR_FLAG_CAPABILITIES and not has_exec and gap != "E_escalate_ok":
            handler = "online_armor_flags"
            has_invoker = True  # explicit skip/flag path
            feeds_online = False
        elif escalate or gap == "E_escalate_ok":
            handler = "escalate_only_skip" if not (has_exec and name in WIRED_REAL) else "real_invoker_escalate_gated"
            has_invoker = True
            feeds_online = bool(has_exec and name in WIRED_REAL)
            if not reason_code and name not in WIRED_REAL:
                reason_code = "no_production_engine_callable"
        else:
            handler = "explicit_skip"
            has_invoker = True  # F1 always installs skip
            feeds_online = False
            gap = "A_missing_invoker" if gap == "A_missing_invoker" else gap

        # After F1 every name has a handler (real/stub/skip) — A means not deep-wired.
        rows.append(
            {
                "name": name,
                "maturity": meta["maturity"],
                "category": meta["category"],
                "default_state": meta["default_state"],
                "has_mainchain_handler": has_invoker,
                "handler_kind": handler,
                "feeds_online_compact": feeds_online,
                "escalate_only": escalate or name in ESCALATE_ONLY,
                "gap_class": gap if gap in GAP_CLASSES else "A_missing_invoker",
                "reason_code": reason_code,
                "physical_callable_hint": (
                    f"capability_executor_registry:{name}"
                    if gap == "F_wired_ok"
                    else f"capability_registry:{handler}:{name}"
                ),
            }
        )

    counts: dict[str, int] = {g: 0 for g in sorted(GAP_CLASSES)}
    for row in rows:
        counts[str(row["gap_class"])] = counts.get(str(row["gap_class"]), 0) + 1
    physical_eligible = sum(1 for row in rows if row["gap_class"] == "F_wired_ok")

    return {
        "schema": "nexus.capability_wiring_matrix.v1",
        "source": "nexus.engine.capability_planner.default_capability_nodes",
        "node_count": len(rows),
        "gap_class_counts": counts,
        "physical_runtime_eligible": physical_eligible,
        "routing_surface_changed": False,
        "new_topology_introduced": False,
        "new_route_mode_introduced": False,
        "rows": rows,
    }


def build_explicit_skip_invoker(
    capability_name: str,
    *,
    skip_reason: str = SKIP_NOT_IMPLEMENTED,
) -> CapabilityInvoker:
    """Invoker that records SKIPPED with whitelist reason (never silent omit)."""
    reason = str(skip_reason or SKIP_NOT_IMPLEMENTED)
    if reason not in SKIP_REASONS:
        reason = SKIP_NOT_IMPLEMENTED
    name = str(capability_name)

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id") or "")
        return {
            "task_id": task_id,
            "invoked": False,
            "skipped": True,
            "skip_reason": reason,
            "gate_passed": True,  # coverage success: explicit skip is intentional
            "outcome_contributed": False,
            "evidence_refs": [f"capability:{name}:{task_id}:skipped:{reason}"],
            "physical_callable": f"capability_registry.explicit_skip:{name}",
            "delegated_to": "PlannerOnly",
            "telemetry": {"token_usage": 0, "model_calls": 0},
            "stub": False,
            "response": {
                "status": "SKIPPED",
                "skip_reason": reason,
                "capability": name,
            },
        }

    return invoke


def _resolve_executor_registry_key(capability_name: str) -> str:
    key = str(capability_name or "").strip()
    return EXECUTOR_REGISTRY_ALIASES.get(key, key)


def build_real_executor_invoker(capability_name: str) -> CapabilityInvoker | None:
    """Wrap existing get_executor physical callable — never reimplement the capability."""
    name = str(capability_name)
    registry_key = _resolve_executor_registry_key(name)
    try:
        from nexus.core.capability_executor_registry import get_executor
        from nexus.core.belief_contracts import CapabilityExecutionPlan
    except Exception:
        return None

    executor = get_executor(registry_key)
    if executor is None:
        return None

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id") or "")
        task_statement = str(context.get("task_statement") or "")
        plan_hash = ""
        planner = context.get("planner") if isinstance(context.get("planner"), Mapping) else {}
        plan_hash = str(planner.get("plan_hash") or planner.get("planner_decision_id") or "")
        try:
            plan = CapabilityExecutionPlan(
                plan_id=plan_hash or f"mainchain:{task_id}:{name}",
                task_id=task_id,
                phases=["R"],
                constraints={},
            )
        except TypeError:
            # Older/newer signature tolerance
            plan = CapabilityExecutionPlan(  # type: ignore[call-arg]
                plan_id=plan_hash or f"mainchain:{task_id}:{name}",
                task_id=task_id,
            )
        try:
            receipt = executor(plan, task_statement)
        except Exception as exc:
            return {
                "task_id": task_id,
                "invoked": False,
                "skipped": False,
                "status": "BLOCKED",
                "gate_passed": False,
                "outcome_contributed": False,
                "evidence_refs": [f"capability:{name}:{task_id}:blocked"],
                "physical_callable": f"capability_executor_registry.get_executor({registry_key!r})",
                "reason": BLOCKED_EXECUTOR_UNAVAILABLE,
                "skip_reason": BLOCKED_EXECUTOR_UNAVAILABLE,
                "telemetry": {"token_usage": 0, "model_calls": 0},
                "stub": False,
                "response": {
                    "status": "BLOCKED_EXECUTOR_UNAVAILABLE",
                    "error": str(exc)[:300],
                    "capability": name,
                    "registry_key": registry_key,
                },
            }

        invoked = bool(getattr(receipt, "invoked", False))
        gate_passed = bool(getattr(receipt, "gate_passed", False))
        evidence_id = str(getattr(receipt, "evidence_id", "") or "")
        telemetries = getattr(receipt, "telemetries", None)
        telemetry = dict(telemetries) if isinstance(telemetries, Mapping) else {}
        if "token_usage" not in telemetry:
            telemetry["token_usage"] = 0
        if "model_calls" not in telemetry:
            telemetry["model_calls"] = 0
        outcome = getattr(receipt, "outcome", None)
        outcome_map = dict(outcome) if isinstance(outcome, Mapping) else {"raw": str(outcome)}
        # Import/construct-only outcomes are never real success (P4).
        shallow_keys = {
            "class_instantiated",
            "function_found",
            "symbol_resolved",
        }
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
        action = str(outcome_map.get("action") or "")
        is_shallow = (
            (any(outcome_map.get(k) for k in shallow_keys) and not action)
            or action in shallow_actions
            or str(outcome_map.get("error") or "") == "import_construct_not_execution"
        )
        # Import/construct without invoke must not count as real success
        if not invoked or is_shallow:
            return {
                "task_id": task_id,
                "invoked": False,
                "skipped": False,
                "status": "BLOCKED",
                "gate_passed": False,
                "outcome_contributed": False,
                "evidence_refs": [evidence_id] if evidence_id else [],
                "evidence_ids": [evidence_id] if evidence_id else [],
                "physical_callable": f"capability_executor_registry:{registry_key}",
                "reason": BLOCKED_EXECUTOR_UNAVAILABLE,
                "telemetry": telemetry,
                "stub": False,
                "response": {
                    "status": "BLOCKED_EXECUTOR_UNAVAILABLE",
                    "capability": name,
                    "registry_key": registry_key,
                    "outcome": outcome_map,
                    "shallow_rejected": is_shallow,
                },
            }
        status = "SUCCEEDED" if gate_passed else "FAILED"
        return {
            "task_id": task_id,
            "invoked": True,
            "skipped": False,
            "status": status,
            "gate_passed": gate_passed,
            "outcome_contributed": gate_passed,
            "evidence_refs": [evidence_id] if evidence_id else [f"capability:{name}:{task_id}:real"],
            "evidence_ids": [evidence_id] if evidence_id else [f"capability:{name}:{task_id}:real"],
            "physical_callable": f"capability_executor_registry:{registry_key}",
            "telemetry": telemetry,
            "stub": False,
            "response": {
                "status": status,
                "capability": name,
                "registry_key": registry_key,
                "outcome": outcome_map,
                "stub": False,
            },
        }

    return invoke


def build_escalate_gated_invoker(
    capability_name: str,
    *,
    real_invoker: CapabilityInvoker | None = None,
) -> CapabilityInvoker:
    """Escalation-only: policy skip when untriggered; real executor or BLOCKED when on."""
    name = str(capability_name)
    skip_invoker = build_explicit_skip_invoker(
        name, skip_reason=SKIP_POLICY_NOT_TRIGGERED
    )

    def _triggered(context: Mapping[str, Any]) -> bool:
        if bool(context.get("escalate_triggered")):
            return True
        route = context.get("route") if isinstance(context.get("route"), Mapping) else {}
        if bool(route.get("escalate")) or bool(route.get("escalate_triggered")):
            return True
        if str(route.get("recommended_flow") or "").lower() in {
            "escalate",
            "hyper",
            "swarm",
            "nightshift",
        }:
            return True
        flags = context.get("executor_flags") if isinstance(context.get("executor_flags"), Mapping) else {}
        if bool(flags.get(name)) or bool(flags.get(f"enable_{name}")):
            return True
        selected_escalations = context.get("triggered_escalations") or []
        if isinstance(selected_escalations, (list, tuple)) and name in selected_escalations:
            return True
        return False

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        if not _triggered(context):
            return dict(skip_invoker(context))
        if real_invoker is None:
            task_id = str(context.get("task_id") or "")
            return {
                "task_id": task_id,
                "invoked": False,
                "skipped": False,
                "status": "BLOCKED",
                "gate_passed": False,
                "outcome_contributed": False,
                "evidence_refs": [f"capability:{name}:{task_id}:blocked_unavailable"],
                "physical_callable": f"capability_registry.escalate_unavailable:{name}",
                "reason": BLOCKED_EXECUTOR_UNAVAILABLE,
                "skip_reason": BLOCKED_EXECUTOR_UNAVAILABLE,
                "telemetry": {"token_usage": 0, "model_calls": 0},
                "stub": False,
                "response": {
                    "status": BLOCKED_EXECUTOR_UNAVAILABLE,
                    "capability": name,
                },
            }
        return dict(real_invoker(context))

    return invoke


def build_structural_stub_invoker(
    capability_name: str,
    *,
    delegated_to: str = "Local",
) -> CapabilityInvoker:
    """Lightweight structural invoker — INVOKED with stub=true (F1 depth, not F2)."""
    name = str(capability_name)

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id") or "")
        return {
            "task_id": task_id,
            "invoked": True,
            "skipped": False,
            "gate_passed": True,
            "outcome_contributed": False,
            "evidence_refs": [f"capability:{name}:{task_id}:stub_preflight"],
            "physical_callable": f"capability_registry.structural_stub:{name}",
            "delegated_to": delegated_to,
            "telemetry": {"token_usage": 0, "model_calls": 0},
            "stub": True,
            "evidence": {
                "capability": name,
                "stub": True,
                "note": "F1 structural stub — deep body is F2+",
            },
            "response": {
                "status": "STUB_OK",
                "capability": name,
                "stub": True,
            },
        }

    return invoke


def build_default_mainchain_invokers(
    *,
    codeintel: Mapping[str, Any] | None = None,
    include_postflight_gates: bool = True,
) -> dict[str, CapabilityInvoker]:
    """Full-name handler map for mainchain (real, stub, or explicit skip).

    Does not hand-pick a partial set as "full Nexus". Every planner node name
    gets a handler. UnifiedRuntime only *runs* handlers for selected names.
    """
    from nexus.services.online_nexus_context import (
        build_codeintel_preflight_invoker,
        build_plan_gated_postflight_invokers,
    )

    invokers: dict[str, CapabilityInvoker] = {}

    # Real wired
    invokers["codeintel"] = build_codeintel_preflight_invoker(codeintel=codeintel)
    if include_postflight_gates:
        invokers.update(build_plan_gated_postflight_invokers())

    for name in list_planner_capability_names():
        if name in invokers:
            continue
        if name in LOCAL_STAGE_CAPABILITIES:
            # Local stage owns execution; registry records skip-from-preflight map.
            invokers[name] = build_explicit_skip_invoker(
                name, skip_reason=SKIP_LOCAL_STAGE
            )
            continue
        real = build_real_executor_invoker(name)
        # Escalation-only / probe-only reclass: untriggered → policy skip; triggered → real or BLOCKED.
        if (
            name in ESCALATE_ONLY
            or name == "llm_judge_panel"
            or name in PROBE_ONLY_REASON_CODES
        ):
            invokers[name] = build_escalate_gated_invoker(name, real_invoker=real)
            continue
        if name in ONLINE_ARMOR_FLAG_CAPABILITIES:
            if real is not None:
                invokers[name] = real
            else:
                invokers[name] = build_explicit_skip_invoker(
                    name, skip_reason=SKIP_ONLINE_ARMOR
                )
            continue
        # Prefer real physical executor from registry (P4) over stub/skip.
        if real is not None:
            invokers[name] = real
            continue
        if name in WIRED_STUB:
            # No physical executor: explicit skip (not structural stub success).
            invokers[name] = build_explicit_skip_invoker(
                name, skip_reason=SKIP_NOT_IMPLEMENTED
            )
            continue
        # Remaining: explicit not-implemented skip (visible gap, not silent)
        invokers[name] = build_explicit_skip_invoker(
            name, skip_reason=SKIP_NOT_IMPLEMENTED
        )

    return invokers


def ensure_selected_coverage_invokers(
    selected: list[str] | tuple[str, ...] | None,
    existing: Mapping[str, CapabilityInvoker] | None,
    *,
    codeintel: Mapping[str, Any] | None = None,
) -> dict[str, CapabilityInvoker]:
    """Merge caller invokers with full registry; fill missing selected with auto-skip.

    Caller-provided invokers win for the same name.
    """
    base = build_default_mainchain_invokers(codeintel=codeintel)
    if existing:
        base.update(dict(existing))
    for name in selected or ():
        key = str(name)
        if key not in base:
            base[key] = build_explicit_skip_invoker(
                key, skip_reason=SKIP_CALLER_OMITTED
            )
    return base


def coverage_counts_from_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Compute selected vs invoked/skipped coverage from a UnifiedRuntime receipt."""
    selected = []
    ctx = receipt.get("context_trace") if isinstance(receipt.get("context_trace"), Mapping) else {}
    selected = [str(x) for x in (ctx.get("selected_capabilities") or [])]
    if not selected:
        planner = receipt.get("planner") if isinstance(receipt.get("planner"), Mapping) else {}
        selected = [str(x) for x in (planner.get("selected_capabilities") or [])]

    caps = receipt.get("capabilities") if isinstance(receipt.get("capabilities"), list) else []
    by_name = {
        str(item.get("name")): item
        for item in caps
        if isinstance(item, Mapping) and item.get("name")
    }

    invoked: list[str] = []
    skipped: list[dict[str, str]] = []
    missing: list[str] = []
    for name in selected:
        row = by_name.get(name)
        if row is None:
            missing.append(name)
            continue
        status = str(row.get("status") or "")
        if status == "SKIPPED" or row.get("skipped") is True:
            skipped.append(
                {
                    "name": name,
                    "skip_reason": str(row.get("skip_reason") or row.get("reason") or ""),
                }
            )
        elif status == "INVOKED" or row.get("invoked") is True:
            invoked.append(name)
        elif status == "SELECTED_NOT_EXECUTED":
            # Treat as skipped-with-reason if reason present, else missing coverage
            reason = str(row.get("reason") or row.get("skip_reason") or "")
            if reason:
                skipped.append({"name": name, "skip_reason": reason})
            else:
                missing.append(name)
        else:
            if row.get("invoked"):
                invoked.append(name)
            else:
                skipped.append(
                    {
                        "name": name,
                        "skip_reason": str(row.get("skip_reason") or row.get("reason") or status),
                    }
                )

    surface_ok = len(missing) == 0 and len(selected) == len(invoked) + len(skipped)

    real_invoked: list[str] = []
    stub_invoked: list[str] = []
    consumer_proven: list[str] = []
    verified_ok: list[str] = []
    for name in invoked:
        row = by_name.get(name) or {}
        stub = bool(row.get("stub")) or str(row.get("physical_callable") or "").endswith(
            f"structural_stub:{name}"
        ) or "structural_stub" in str(row.get("physical_callable") or "")
        if stub:
            stub_invoked.append(name)
            continue
        if not row.get("evidence_refs") and not row.get("evidence_ids"):
            continue
        real_invoked.append(name)
        if row.get("outcome_contributed") or row.get("consumer_proof"):
            consumer_proven.append(name)
        if row.get("gate_passed") and str(row.get("status") or "") not in {
            "SELECTED_NOT_EXECUTED",
            "FAILED",
            "BLOCKED",
        }:
            verified_ok.append(name)

    real_execution_coverage_ok = surface_ok and len(stub_invoked) == 0 and (
        len(real_invoked) + len(skipped) == len(selected) or len(selected) == 0
    )
    # Consumer proof: at least one real capability with non-empty evidence when any real ran
    consumer_coverage_ok = True
    if real_invoked:
        consumer_coverage_ok = len(consumer_proven) > 0 or any(
            bool((by_name.get(n) or {}).get("evidence_refs")) for n in real_invoked
        )
    verified_outcome_ok = all(
        bool((by_name.get(n) or {}).get("gate_passed")) for n in real_invoked
    ) if real_invoked else surface_ok

    return {
        "selected_count": len(selected),
        "invoked_count": len(invoked),
        "skipped_count": len(skipped),
        "missing_count": len(missing),
        "coverage_ok": surface_ok,  # surface only — not real/claim success
        "surface_coverage_ok": surface_ok,
        "real_execution_coverage_ok": real_execution_coverage_ok and len(stub_invoked) == 0,
        "consumer_coverage_ok": consumer_coverage_ok,
        "verified_outcome_ok": verified_outcome_ok,
        "selected": selected,
        "invoked": invoked,
        "skipped": skipped,
        "missing": missing,
        "real_invoked": real_invoked,
        "stub_invoked": stub_invoked,
        "public_claim_allowed": False,
    }
