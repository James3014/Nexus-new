from typing import Any, Callable, Dict, List
from nexus.research.architecture_scout import DistantScoutPlanner

def decide_auto_flow_routing(
    *,
    chosen_flow: str,
    force_flow: str | None,
    execution_profile: Dict[str, Any],
    learn_gate_blocked: bool,
    plateau_detected: bool,
    recent_window: List[Dict[str, Any]],
    history_fail_threshold: int,
) -> Dict[str, Any]:
    """
    🧠 Auto Flow Routing 決策引擎
    負責計算 Chosen Flow 覆寫、Plateau 硬重導、Nightshift 推薦與歷史強制回退邏輯。
    與 Executor 隔離，為無副作用之 Pure Logic。
    """
    # 1. Learn Gate Blocked Override
    if force_flow is None and chosen_flow == "hyper_sprint" and learn_gate_blocked and not execution_profile.get("is_hard_task", False):
        chosen_flow = "baseline"

    # 2. Plateau Pivot Override
    plateau_hard_pivot = bool(force_flow is None and plateau_detected)
    if force_flow is None and plateau_detected and chosen_flow == "baseline":
        chosen_flow = "hyper_sprint"

    # 3. Nightshift & History Fail Overrides
    recent_hyper_fails = sum(1 for item in recent_window if item.get("flow") == "hyper_sprint" and item.get("status") == "FAILED")
    stage1_fail_signals = sum(
        1
        for item in recent_window
        if item.get("flow") == "hyper_sprint"
        and item.get("status") == "FAILED"
        and "stage1_no_passing_candidate" in str(item.get("reason", ""))
    )
    nightshift_recommended = bool(recent_hyper_fails >= 2 or stage1_fail_signals >= 1)
    
    history_forced_baseline = False
    if (
        force_flow is None
        and not plateau_hard_pivot
        and chosen_flow == "hyper_sprint"
        and recent_hyper_fails >= max(1, history_fail_threshold)
    ):
        chosen_flow = "baseline"
        history_forced_baseline = True

    return {
        "chosen_flow": chosen_flow,
        "plateau_hard_pivot": plateau_hard_pivot,
        "nightshift_recommended": nightshift_recommended,
        "history_forced_baseline": history_forced_baseline,
        "recent_hyper_fails": recent_hyper_fails,
        "stage1_fail_signals": stage1_fail_signals,
    }

def enrich_route_on_plateau(
    *,
    route: Dict[str, Any],
    task_desc: str,
    task_type: str,
    plateau: Dict[str, Any],
    asi_ledger: List[Dict[str, Any]],
    build_capability_plan_fn: Callable[[Dict[str, Any]], tuple[Any, Any]],
) -> None:
    """
    當 Plateau 偵測成立時，進行特化的 Route context / scout plan / capability plan 富化。
    使用 Dependency Injection 傳入 build_capability_plan_fn 避免與 app layer 循環依賴。
    """
    route_features = route.get("route_features", {}) if isinstance(route, dict) else {}
    route_features = {**route_features, "plateau_detected": True, "route_pivot": "distant_scout"}
    context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
    risk_flags = list(context.get("risk_flags", []) or [])
    blocked_assumptions = list(context.get("blocked_assumptions", []) or [])
    
    if "plateau_detected" not in risk_flags:
        risk_flags.append("plateau_detected")
    if "local_micro_tuning_is_enough" not in blocked_assumptions:
        blocked_assumptions.append("local_micro_tuning_is_enough")
        
    context = {
        **context,
        "risk_flags": risk_flags,
        "blocked_assumptions": blocked_assumptions,
        "next_action_hint": "switch_to_architecture_scout_and_change_family",
        "route_pivot": "distant_scout",
    }
    route_features["blocked_assumptions_count"] = len(blocked_assumptions)
    route["route_features"] = route_features
    route["research_context"] = context
    
    # Build distant scout plan
    route["distant_scout_plan"] = DistantScoutPlanner().plan(
        task_desc=task_desc,
        plateau=plateau,
        asi_ledger=asi_ledger
    )
    
    # Re-build capability plan & decision through injected function
    capability_plan, route_decision = build_capability_plan_fn(route)
    route["capability_plan"] = capability_plan.to_dict()
    route["route_decision"] = route_decision
