"""World A main-chain entry helpers (ROUTING FREEZE).

Does not introduce execution_topology / RouteMode product selectors.
with_nexus is Online prompt armor; VAP is optional Local packet consumption.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from nexus.services.capability_registry import (
    build_default_mainchain_invokers,
    ensure_selected_coverage_invokers,
)
from nexus.services.online_nexus_context import (
    make_with_nexus_online_invoker,
    prompt_has_with_nexus_sections,
)
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)

ROUTE_FLAG_WITH_NEXUS = "with_nexus_armor"
ROUTE_FLAG_MAINCHAIN = "mainchain_entry"
MAINCHAIN_ROUTE_VERSION = "mainchain.v1"
MAINCHAIN_DEFAULT_PRODUCT_ENTRY = "mainchain"


def mainchain_route_identity_projection(
    route: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Project pure canonical Mainchain route identity (no permissive defaults)."""
    r = dict(route) if isinstance(route, Mapping) else {}
    raw_prod = r.get("product_entry")
    prod = str(raw_prod or "mainchain").strip()
    if prod in ("None", "null", ""):
        prod = "mainchain"
    return {
        "mainchain_entry": bool(r.get("mainchain_entry", False)),
        "route_freeze": bool(r.get("route_freeze", False)),
        "mainchain_route_version": str(r.get("mainchain_route_version") or ""),
        "product_entry": prod,
        "with_nexus_armor": bool(r.get("with_nexus_armor", False)),
    }


def with_nexus_armor_enabled(route: Mapping[str, Any] | None) -> bool:
    """True when route requests World B prompt armor on the Online invoker."""
    if not isinstance(route, Mapping):
        return False
    if ROUTE_FLAG_WITH_NEXUS in route:
        return bool(route.get(ROUTE_FLAG_WITH_NEXUS))
    # Explicit mainchain product entry defaults armor on.
    if bool(route.get(ROUTE_FLAG_MAINCHAIN)):
        return True
    return False


def stamp_mainchain_route(
    route: Mapping[str, Any] | None,
    *,
    with_nexus_armor: bool = True,
    product_entry: str = "mainchain",
) -> dict[str, Any]:
    """Return a route dict with FREEZE-safe mainchain flags (no new topology)."""
    out = dict(route or {})
    out[ROUTE_FLAG_MAINCHAIN] = True
    out["route_freeze"] = True
    out["mainchain_route_version"] = MAINCHAIN_ROUTE_VERSION
    out[ROUTE_FLAG_WITH_NEXUS] = bool(with_nexus_armor)

    raw_prod = out.get("product_entry") or product_entry
    prod = str(raw_prod or "mainchain").strip()
    if prod in ("None", "null", ""):
        prod = "mainchain"
    out["product_entry"] = prod

    # Strip non-product reconnection labels if a caller stuffed them into topology.
    if str(out.get("execution_topology") or "") in {
        "nexus_full_stack",
        "online_nexus_v1",
        "fused_product",
    }:
        out.pop("execution_topology", None)
    return out


def build_mainchain_capability_invokers(
    *,
    codeintel: Mapping[str, Any] | None = None,
    include_postflight_gates: bool = True,
) -> dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]:
    """Full mainchain registry: every planner node has real/stub/explicit-skip handler.

    FCM F1: does **not** hand-pick a few gates as "full Nexus". Callers may
    override individual names; UnifiedRuntime still covers selected fully.
    """
    return build_default_mainchain_invokers(
        codeintel=codeintel,
        include_postflight_gates=include_postflight_gates,
    )


def wrap_mainchain_online_invoker(
    base_invoker: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    *,
    route: Mapping[str, Any] | None = None,
    force: bool = False,
    provider: str = "mainchain",
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Wrap Online invoker with true with_nexus armor when route requests it."""
    if force or with_nexus_armor_enabled(route):
        return make_with_nexus_online_invoker(base_invoker, provider=provider)
    return base_invoker


def merge_mainchain_capability_invokers(
    existing: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None,
    *,
    codeintel: Mapping[str, Any] | None = None,
    enable: bool = True,
    selected: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None:
    """Caller invokers win; registry fills full mainchain coverage when enable."""
    if not enable:
        return dict(existing) if existing else None
    return ensure_selected_coverage_invokers(
        selected or list(build_default_mainchain_invokers(codeintel=codeintel).keys()),
        existing,
        codeintel=codeintel,
    )


def run_mainchain(
    request: UnifiedRuntimeRequest,
    *,
    online_invoker: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    local_service: Any = None,
    planner: Any = None,
    capability_invokers: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None = None,
    verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    learning: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    receipt_path: Any = None,
    with_nexus_armor: bool = True,
) -> dict[str, Any]:
    """Run UnifiedRuntime with mainchain route stamps + with_nexus Online armor."""
    route = stamp_mainchain_route(
        request.route if isinstance(request.route, Mapping) else {},
        with_nexus_armor=with_nexus_armor,
        product_entry=str(
            (request.route or {}).get("product_entry")
            if isinstance(request.route, Mapping)
            else "mainchain"
        )
        or "mainchain",
    )
    # Frozen dataclass — rebuild request with stamped route.
    fields = {
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "task_statement": request.task_statement,
        "task_type": request.task_type,
        "route": route,
        "online_enabled": request.online_enabled,
        "local_enabled": request.local_enabled,
        "online_prompt": request.online_prompt,
        "online_payload": request.online_payload,
        "online_phase": request.online_phase,
        "online_model_name": request.online_model_name,
        "online_output_schema": request.online_output_schema,
        "pillars": request.pillars,
        "codeintel": request.codeintel,
        "phase_trace": request.phase_trace,
        "budget": request.budget,
        "skills": request.skills,
        "local_request": request.local_request,
        "evidence_refs": request.evidence_refs,
        "schema": request.schema,
    }
    stamped = UnifiedRuntimeRequest(**fields)
    invoker = wrap_mainchain_online_invoker(
        online_invoker,
        route=route,
        force=with_nexus_armor,
        provider="mainchain",
    )
    caps = merge_mainchain_capability_invokers(
        capability_invokers,
        codeintel=dict(stamped.codeintel) if isinstance(stamped.codeintel, Mapping) else {},
        enable=with_nexus_armor,
    )
    return UnifiedRuntime(planner=planner, local_service=local_service).run(
        stamped,
        online_invoker=invoker,
        capability_invokers=caps,
        verifier=verifier,
        learning=learning,
        receipt_path=receipt_path,
    )


def run_mainchain_replan(
    previous_receipt: Mapping[str, Any],
    request: UnifiedRuntimeRequest,
    *,
    online_invoker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    local_service: Any = None,
    planner: Any = None,
    capability_invokers: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None = None,
    verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    learning: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    receipt_path: Any = None,
    with_nexus_armor: bool = True,
) -> dict[str, Any]:
    """Run UnifiedRuntime.run_replan with mainchain route stamps + with_nexus Online armor."""
    if not with_nexus_armor:
        raise ValueError("mainchain_replan_requires_nexus_armor")

    if not isinstance(previous_receipt, Mapping):
        raise ValueError("previous_receipt_invalid")

    from nexus.evidence.receipt_base import validate_receipt_base

    res = validate_receipt_base(previous_receipt, mode="strict")
    if not res.get("ok"):
        blockers = res.get("blockers") or ["validation_failed"]
        raise ValueError(f"previous_receipt_integrity_invalid:{','.join(blockers)}")

    context_trace = previous_receipt.get("context_trace")
    if not isinstance(context_trace, Mapping):
        raise ValueError("previous_receipt_not_mainchain")

    prior_route = context_trace.get("route")
    if not isinstance(prior_route, Mapping):
        raise ValueError("previous_receipt_not_mainchain")

    selection_authority = context_trace.get("selection_authority") or previous_receipt.get("selection_authority")
    if selection_authority != "CapabilityPlanner":
        raise ValueError("previous_receipt_planner_authority_invalid")

    if not bool(prior_route.get("mainchain_entry")):
        raise ValueError("previous_receipt_not_mainchain")

    if prior_route.get("route_freeze") is not True:
        raise ValueError("previous_receipt_route_freeze_missing")

    prior_ver = prior_route.get("mainchain_route_version")
    if not prior_ver:
        raise ValueError("previous_receipt_mainchain_version_missing")
    if prior_ver != MAINCHAIN_ROUTE_VERSION:
        raise ValueError(f"previous_receipt_mainchain_version_unsupported:{prior_ver}")

    if prior_route.get("with_nexus_armor") is not True:
        raise ValueError("previous_receipt_nexus_armor_missing")

    prior_prod = str(prior_route.get("product_entry") or "").strip()
    if not prior_prod or prior_prod in ("None", "null"):
        raise ValueError("previous_receipt_product_entry_invalid")

    rb = previous_receipt.get("receipt_base") if isinstance(previous_receipt.get("receipt_base"), Mapping) else {}
    if not bool(rb.get("mainchain_entry")):
        raise ValueError("previous_receipt_not_mainchain")
    if rb.get("route_freeze") is not True:
        raise ValueError("previous_receipt_route_freeze_missing")
    if rb.get("mainchain_route_version") != MAINCHAIN_ROUTE_VERSION:
        raise ValueError(f"previous_receipt_mainchain_version_unsupported:{rb.get('mainchain_route_version')}")
    if rb.get("with_nexus_armor") is not True:
        raise ValueError("previous_receipt_nexus_armor_missing")

    if (
        prior_route.get("mainchain_entry") != rb.get("mainchain_entry")
        or prior_route.get("route_freeze") != rb.get("route_freeze")
        or prior_route.get("mainchain_route_version") != rb.get("mainchain_route_version")
        or prior_route.get("with_nexus_armor") != rb.get("with_nexus_armor")
    ):
        raise ValueError("previous_receipt_mainchain_identity_mismatch")

    route = stamp_mainchain_route(
        request.route if isinstance(request.route, Mapping) else {},
        with_nexus_armor=True,
        product_entry=prior_prod,
    )

    fields = {
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "task_statement": request.task_statement,
        "task_type": request.task_type,
        "route": route,
        "online_enabled": request.online_enabled,
        "local_enabled": request.local_enabled,
        "online_prompt": request.online_prompt,
        "online_payload": request.online_payload,
        "online_phase": request.online_phase,
        "online_model_name": request.online_model_name,
        "online_output_schema": request.online_output_schema,
        "pillars": request.pillars,
        "codeintel": request.codeintel,
        "phase_trace": request.phase_trace,
        "budget": request.budget,
        "skills": request.skills,
        "local_request": request.local_request,
        "evidence_refs": request.evidence_refs,
        "schema": request.schema,
    }
    stamped = UnifiedRuntimeRequest(**fields)

    invoker = online_invoker
    if online_invoker is not None:
        invoker = wrap_mainchain_online_invoker(
            online_invoker,
            route=route,
            force=True,
            provider="mainchain",
        )

    caps = merge_mainchain_capability_invokers(
        capability_invokers,
        codeintel=dict(stamped.codeintel) if isinstance(stamped.codeintel, Mapping) else {},
        enable=True,
    )

    return UnifiedRuntime(planner=planner, local_service=local_service).run_replan(
        previous_receipt,
        stamped,
        online_invoker=invoker,
        capability_invokers=caps,
        verifier=verifier,
        learning=learning,
        receipt_path=receipt_path,
    )


def summarize_arm_receipt(receipt: Mapping[str, Any], *, prompt: str = "") -> dict[str, Any]:
    """Machine-checkable Bare vs Nexus vs Nexus+L summary."""
    oc = {}
    ctx = receipt.get("context_trace") if isinstance(receipt.get("context_trace"), Mapping) else {}
    route = ctx.get("route") if isinstance(ctx.get("route"), Mapping) else {}
    if isinstance(ctx.get("online_received_context"), Mapping):
        oc = dict(ctx["online_received_context"])
    sections = prompt_has_with_nexus_sections(prompt)
    va = receipt.get("verified_assist") if isinstance(receipt.get("verified_assist"), Mapping) else {}
    credit = va.get("credit") if isinstance(va.get("credit"), Mapping) else {}
    local = receipt.get("local") if isinstance(receipt.get("local"), Mapping) else {}
    local_resp = local.get("response") if isinstance(local.get("response"), Mapping) else {}
    caps = receipt.get("capability_results") if isinstance(receipt.get("capability_results"), Mapping) else {}
    attempt = receipt.get("execution_attempt") if isinstance(receipt.get("execution_attempt"), Mapping) else {}
    replan_req = receipt.get("execution_replan_request") if isinstance(receipt.get("execution_replan_request"), Mapping) else {}
    online_stg = receipt.get("online") if isinstance(receipt.get("online"), Mapping) else {}
    online_resp = online_stg.get("response") if isinstance(online_stg.get("response"), Mapping) else {}
    proc_ev = online_resp.get("process_evidence") if isinstance(online_resp.get("process_evidence"), Mapping) else {}

    mc_entry = route.get("mainchain_entry") is True
    freeze = route.get("route_freeze") is True
    ver = str(route.get("mainchain_route_version") or "")
    prod = str(route.get("product_entry") or "").strip()
    armor = route.get("with_nexus_armor") is True or bool(oc.get("with_nexus_armor") or sections.get("route"))

    identity_complete = (
        mc_entry
        and freeze
        and ver == MAINCHAIN_ROUTE_VERSION
        and armor
        and bool(prod)
        and prod not in ("None", "null")
    )

    return {
        "task_id": str(receipt.get("task_id") or ""),
        "mainchain_entry": mc_entry,
        "route_freeze": freeze,
        "mainchain_route_version": ver,
        "product_entry": prod,
        "with_nexus_armor": armor,
        "mainchain_identity_complete": identity_complete,
        "prompt_has_route": bool(sections.get("route")),
        "prompt_has_codeintel": bool(sections.get("codeintel")),
        "vap_attached": bool(oc.get("vap_attached")),
        "vap_packet_hash": str(oc.get("vap_packet_hash") or ""),
        "assist_credited": bool(credit.get("assist_credited")),
        "local_status": str(local.get("status") or ""),
        "local_physical_callable": str(local_resp.get("physical_callable") or ""),
        "selected_capabilities": list(ctx.get("selected_capabilities") or []),
        "capabilities_invoked": [
            name for name, stage in caps.items() if isinstance(stage, Mapping) and stage.get("invoked")
        ],
        "public_claim_allowed": bool(
            (receipt.get("claim_boundary") or {}).get("public_claim_allowed")
        )
        if isinstance(receipt.get("claim_boundary"), Mapping)
        else False,
        "receipt_complete": bool(receipt.get("receipt_complete")),
        "treatment_core_equal": bool(
            (receipt.get("treatment_core_equal") or {}).get("equal")
        )
        if isinstance(receipt.get("treatment_core_equal"), Mapping)
        else False,
        "attempt_number": int(attempt.get("attempt_number", 1)),
        "is_replan": bool(attempt.get("is_replan", False)),
        "execution_depth": str(receipt.get("execution_depth") or ""),
        "replan_required": bool(replan_req.get("replan_required", False)),
        "requested_execution_depth": str(replan_req.get("requested_execution_depth") or ""),
        "process_invocation_id": str(proc_ev.get("process_invocation_id") or ""),
        "provider": str(proc_ev.get("provider") or ""),
        "transport": str(proc_ev.get("transport") or ""),
        "terminal_status": str(receipt.get("terminal_status") or ""),
    }



def run_three_arm_structural(
    *,
    task_statement: str,
    task_type: str = "repair",
    codeintel: Mapping[str, Any] | None = None,
    local_service: Any = None,
    local_request: Any = None,
    planner: Any = None,
    workspace_revision: str = "three-arm-structural",
) -> dict[str, Any]:
    """Bare / Nexus / Nexus+L structural compare on real UnifiedRuntime (fixture Online)."""
    ci = dict(codeintel or {
        "scan_report_present": True,
        "impact_report_present": True,
        "risk_score": 6,
        "impacted_files_count": 2,
        "dci_evidence_count": 1,
    })
    prompts: dict[str, str] = {}

    def _base(arm: str) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
        def invoker(context: Mapping[str, Any]) -> dict[str, Any]:
            prompts[arm] = str(context.get("online_prompt") or "")
            return normalize_online_invoker_payload(
                provider="fixture",
                task_id=str(context.get("task_id") or ""),
                invoked=True,
                output_delivered=True,
                gate_passed=True,
                provider_call_count=1,
                response={"status": "ok", "arm": arm},
                raw_response="ok",
                evidence_refs=[f"online:{context.get('task_id')}:{arm}"],
            )

        return invoker

    def _v(context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"verifier:{context['task_id']}"],
        }

    def _l(context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"learning:{context['task_id']}"],
        }

    route_common = {
        "recommended_flow": "direct",
        "injected_transport": True,
        "online_policy": "auto",
    }

    # Arm A — bare
    bare_req = UnifiedRuntimeRequest(
        task_id="three-arm-bare",
        workspace_revision=workspace_revision,
        task_statement=task_statement,
        task_type=task_type,
        route=dict(route_common),
        online_enabled=True,
        local_enabled=False,
        online_prompt=task_statement,
        codeintel=ci,
    )
    bare_receipt = UnifiedRuntime(planner=planner).run(
        bare_req,
        online_invoker=_base("bare"),
        verifier=_v,
        learning=_l,
    )

    # Arm B — Nexus Online armor
    nexus_req = UnifiedRuntimeRequest(
        task_id="three-arm-nexus",
        workspace_revision=workspace_revision,
        task_statement=task_statement,
        task_type=task_type,
        route=stamp_mainchain_route(route_common, product_entry="three_arm_nexus"),
        online_enabled=True,
        local_enabled=False,
        online_prompt=task_statement,
        codeintel=ci,
    )
    nexus_receipt = run_mainchain(
        nexus_req,
        online_invoker=_base("nexus"),
        planner=planner,
        verifier=_v,
        learning=_l,
        with_nexus_armor=True,
    )

    # Arm D — Nexus + Local (VAP when local succeeds)
    nexus_l_receipt: dict[str, Any] = {}
    if local_service is not None and local_request is not None:
        nexus_l_req = UnifiedRuntimeRequest(
            task_id="three-arm-nexus-local",
            workspace_revision=workspace_revision,
            task_statement=task_statement,
            task_type=task_type,
            route=stamp_mainchain_route(
                {**route_common, "recommended_flow": "hybrid", "local_enabled": True},
                product_entry="three_arm_nexus_local",
            ),
            online_enabled=True,
            local_enabled=True,
            online_prompt=task_statement,
            codeintel=ci,
            local_request=local_request,
        )
        nexus_l_receipt = run_mainchain(
            nexus_l_req,
            online_invoker=_base("nexus_local"),
            local_service=local_service,
            planner=planner,
            verifier=_v,
            learning=_l,
            with_nexus_armor=True,
        )

    result = {
        "schema": "nexus.three_arm_structural.v1",
        "routing_surface_changed": False,
        "public_claim_allowed": False,
        "arms": {
            "bare": summarize_arm_receipt(bare_receipt, prompt=prompts.get("bare", "")),
            "nexus": summarize_arm_receipt(nexus_receipt, prompt=prompts.get("nexus", "")),
            "nexus_local": summarize_arm_receipt(
                nexus_l_receipt, prompt=prompts.get("nexus_local", "")
            )
            if nexus_l_receipt
            else {"skipped": True, "reason": "local_service_or_request_missing"},
        },
        "receipts": {
            "bare": bare_receipt,
            "nexus": nexus_receipt,
            "nexus_local": nexus_l_receipt or None,
        },
        "prompts": {
            "bare": prompts.get("bare", ""),
            "nexus": prompts.get("nexus", ""),
            "nexus_local": prompts.get("nexus_local", ""),
        },
        "compare": {
            "bare_lacks_armor": not prompt_has_with_nexus_sections(prompts.get("bare", "")).get("route"),
            "nexus_has_armor": bool(prompt_has_with_nexus_sections(prompts.get("nexus", "")).get("route")),
            "nexus_local_has_vap": bool(
                (nexus_l_receipt.get("context_trace") or {})
                .get("online_received_context", {})
                .get("vap_attached")
            )
            if nexus_l_receipt
            else False,
        },
    }
    return result
