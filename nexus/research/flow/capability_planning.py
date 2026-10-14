from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from nexus.core.repo_root import REPO_ROOT
from nexus.engine.capability_executor_controls import build_executor_controls
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.learning_policy_loader import merge_runtime_learning_policy
from nexus.engine.route_decision_adapter import build_route_decision
from nexus.research.flow.rlm_trace import safe_trace_slug
from nexus.services.capability_registry import ARCHIVED_CAPABILITY_REASONS

# Plan lists an archived node must never appear in; it is moved to ``forbidden_capabilities``.
_ARCHIVED_SELECTION_LISTS = (
    "selected_capabilities",
    "required_capabilities",
    "conditional_capabilities",
    "optional_capabilities",
    "pending_capabilities",
)
# Keys left untouched by the walker: the audit-visible places where an archived name must
# stay (forbidden list, the planner's decision trace, the drop record itself).
_ARCHIVED_KEEP_KEYS = frozenset({
    "forbidden_capabilities",
    "decision_trace",
    "archived_capabilities_dropped",
    "retired_capabilities",
})
_ARCHIVED_MAX_DEPTH = 12
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_STEP_NAME_KEYS = ("capability", "name", "id")


def _normalise_capability_token(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).translate(_ZERO_WIDTH).strip()
    text = _CAMEL_BOUNDARY.sub("_", text)
    return re.sub(r"[\s\-]+", "_", text.lower()).strip("_")


def _archived_name(value: Any) -> str:
    """Canonical archived name ``value`` denotes, else "".

    Normalised with NFKC, zero-width removal, CamelCase -> snake, ``-``/space -> ``_`` and
    lower case; ``capability:<name>``, ``<name>:<suffix>`` and dotted forms
    (``flow.integration_manager.run``) match when any component names an archived capability.
    """
    if not isinstance(value, str) or not value.strip():
        return ""
    text = unicodedata.normalize("NFKC", value).translate(_ZERO_WIDTH).strip()
    if text.lower().startswith("capability:"):
        text = text.split(":", 1)[1]
    for part in [text, *re.split(r"[.:/]", text)]:
        name = _normalise_capability_token(part)
        if name in ARCHIVED_CAPABILITY_REASONS:
            return name
    return ""


def _is_capability_context(key: str) -> bool:
    """Keys whose value lists / maps capability names (never generic tags or budgets)."""
    k = _normalise_capability_token(str(key))
    return (
        "capabilit" in k
        or "route_map" in k
        or k.endswith(("tool_map", "sequence", "_layers"))
        or k.startswith(("selected", "conditional", "required", "optional", "pending", "active"))
    )


def _step_name(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    for key in _STEP_NAME_KEYS:
        name = _archived_name(entry.get(key))
        if name:
            return name
    return ""


def _strip_archived(
    value: Any,
    dropped: dict[str, str],
    depth: int = 0,
    key: str = "",
    in_context: bool = False,
) -> Any:
    """Remove archived capability names from the capability-denoting parts of a plan tree.

    Only inside capability contexts (``_is_capability_context`` keys and everything under a
    ``*route_map*`` key): archived strings leave lists, ``{"capability"|"name"|"id": X}`` steps
    are dropped, map keys naming an archived capability are dropped, and ``after`` links to a
    dropped step are re-pointed at its predecessor (or cleared).  Elsewhere (tags, budgets, ...)
    nothing is touched.  ``_ARCHIVED_KEEP_KEYS`` are kept verbatim.
    """
    if depth > _ARCHIVED_MAX_DEPTH:
        return value
    if isinstance(value, (list, tuple)):
        removed_after: dict[str, Any] = {}
        kept: list[Any] = []
        for entry in value:
            name = (_archived_name(entry) or _step_name(entry)) if in_context else ""
            if name:
                if isinstance(entry, dict):
                    removed_after[name] = entry.get("after")
                if not key.startswith("optional"):
                    dropped[name] = ARCHIVED_CAPABILITY_REASONS[name]
                continue
            kept.append(_strip_archived(entry, dropped, depth + 1, key, in_context))
        for index, entry in enumerate(kept):
            if (
                not in_context
                or not isinstance(entry, dict)
                or not _archived_name(entry.get("after"))
            ):
                continue
            after = _archived_name(entry.get("after"))
            seen: set[str] = set()
            while after in removed_after and after not in seen:
                seen.add(after)
                after = _archived_name(removed_after[after]) or removed_after[after]
            # A link to an archived step outside this list has no predecessor to point at.
            kept[index] = {**entry, "after": None if _archived_name(after) else after}
        return kept
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    route_map = "route_map" in _normalise_capability_token(key)
    for child_key, item in value.items():
        if child_key in _ARCHIVED_KEEP_KEYS:
            out[child_key] = item
            continue
        if (in_context or route_map) and _archived_name(child_key):
            continue  # per-capability map entry
        child_context = route_map or _is_capability_context(str(child_key))
        out[child_key] = _strip_archived(item, dropped, depth + 1, str(child_key), child_context)
    return out


def drop_archived_capabilities(plan_payload: dict[str, Any]) -> dict[str, Any]:
    """Copy of a CapabilityPlan / route-decision payload where archived nodes are never selected.

    The pinned nexus-runtime planner still enables some archived nodes (e.g.
    ``integration_manager`` on an "integrate"/"merge" task) until its maturity flip lands.
    Nexus-side, every archived node (``ARCHIVED_CAPABILITY_REASONS``) is removed from the
    capability-denoting parts of the payload by ``_strip_archived`` (generic tags and budgets
    are never touched), marked ``forbidden`` in
    ``decision_trace``, moved to ``forbidden_capabilities`` and named in
    ``signal_snapshot.archived_capabilities_dropped``.  Those three are the only places an
    archived name remains.
    """

    if not isinstance(plan_payload, dict):
        return plan_payload
    dropped: dict[str, str] = {}
    plan: dict[str, Any] = _strip_archived(dict(plan_payload), dropped)
    if not dropped:
        return plan
    raw_forbidden = plan.get("forbidden_capabilities")
    if raw_forbidden is not None and not isinstance(raw_forbidden, (list, tuple)):
        # Malformed: fail closed (still forbid the archived nodes) and say why.
        plan["archived_filter_error"] = "forbidden_capabilities_not_a_list"
        raw_forbidden = []
    forbidden = [str(item) for item in raw_forbidden or []]
    plan["forbidden_capabilities"] = forbidden + [name for name in dropped if name not in forbidden]
    trace = plan.get("decision_trace")
    if isinstance(trace, list):
        plan["decision_trace"] = [
            {**item, "state": "forbidden", "reasons": [*(item.get("reasons") or []), dropped[name]]}
            if isinstance(item, dict) and (name := _step_name(item)) in dropped
            else item
            for item in trace
        ]
    snapshot = plan.get("signal_snapshot")
    snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}
    snapshot["archived_capabilities_dropped"] = dict(dropped)
    plan["signal_snapshot"] = snapshot
    return plan


def compose_capability_plan(
    *,
    task_desc: str,
    task_type: str,
    recommended_flow: str,
    route_features: dict[str, Any],
    research_context: dict[str, Any] | None = None,
    target_file: str | None = None,
) -> dict[str, Any]:
    seed_selected = ["hyper_sprint"] if recommended_flow == "hyper_sprint" else ["baseline"]
    readiness = route_features.get("candidate_factory_readiness_estimate", {})
    readiness = readiness if isinstance(readiness, dict) else {}
    estimated_candidates = int(readiness.get("estimated_candidates", route_features.get("candidate_count", 1)) or 1)
    candidate_factory_ready = bool(readiness.get("ready", estimated_candidates >= 2))
    seed_acceleration = ["ddtree"] if candidate_factory_ready and estimated_candidates >= 3 else []
    research_context = research_context if isinstance(research_context, dict) else {}
    recommended_caps = {str(item) for item in (research_context.get("recommended_capabilities", []) or []) if str(item)}
    seed_route = {
        "recommended_flow": recommended_flow,
        "route_features": route_features,
        "research_context": research_context,
        "route_decision": {
            "selected_capabilities": seed_selected + (["autoreason"] if "autoreason" in recommended_caps else []),
            "acceleration_layers": seed_acceleration,
            "governance_layers": ["ultra_review"] if "ultra_review" in recommended_caps else [],
        },
    }
    plan = CapabilityPlanner(shared_playbook_root=REPO_ROOT).plan(task_desc=task_desc, task_type=task_type, route=seed_route)
    selected = {str(item) for item in plan.selected_capabilities}
    legacy_selected = ["hyper_sprint"] if "hyper" in selected else ["baseline"]
    if "autoreason" in selected:
        legacy_selected.append("autoreason")

    def _reasons(capability: str) -> list[str]:
        for item in plan.decision_trace:
            if item.get("capability") == capability:
                return list(item.get("reasons", []) or [])
        return []

    return {
        "schema_version": "legacy_capability_stack_v2_compat",
        "source": "route_decision_compat",
        "selected_capabilities": legacy_selected,
        "acceleration_layers": ["ddtree"] if "ddtree" in selected else [],
        "governance_layers": ["ultra_review"] if "ultra_review" in selected else [],
        "explain_caps": [
            {
                "capability": "hyper_sprint" if recommended_flow == "hyper_sprint" else "baseline",
                "enabled": True,
                "reasons": [f"recommended_flow:{recommended_flow}"],
                "evidence": ["route.recommended_flow"],
            },
            {
                "capability": "autoreason",
                "enabled": "autoreason" in selected,
                "reasons": _reasons("autoreason"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ddtree",
                "enabled": "ddtree" in selected,
                "reasons": _reasons("ddtree"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ultra_review",
                "enabled": "ultra_review" in selected,
                "reasons": _reasons("ultra_review"),
                "evidence": ["capability_plan.decision_trace"],
            },
        ],
        "stop_policy": {
            "type": "a_streak" if "autoreason" in selected else "budget",
            "threshold": 2 if "autoreason" in selected else 1,
            "budget_guard": "fail_closed",
        },
        "target_file": target_file or "",
    }


def build_capability_plan_and_decision(
    *,
    task_desc: str,
    task_type: str,
    route: dict[str, Any],
    task_id: str | None = None,
    budget: dict[str, Any] | None = None,
    skills: list[dict[str, Any]] | None = None,
) -> tuple[Any, dict[str, Any]]:
    decision_route = {key: value for key, value in route.items() if key != "capability_stack"}
    plan = CapabilityPlanner(shared_playbook_root=REPO_ROOT).plan(
        task_desc=task_desc,
        task_type=task_type,
        route=decision_route,
        budget=budget,
        skills=skills,
    )
    decision = build_route_decision(
        task_id=task_id or safe_trace_slug(task_desc),
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=str(route.get("recommended_flow") or ""),
        plan=plan,
    ).to_dict()
    return plan, decision


def benchmark_skill_mount_requests_from_env(*, task_id: str | None) -> list[dict[str, str]]:
    if not task_id:
        return []
    allow_ablation = os.environ.get("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "").strip().lower()
    if allow_ablation in {"0", "false", "no", "off"}:
        return []
    raw = os.environ.get("NEXUS_BENCH_SKILL_MOUNT_REQUESTS", "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(parsed, list):
        return []
    requests: list[dict[str, str]] = []
    for item in parsed:
        if isinstance(item, dict):
            skill_id = str(item.get("skill_id") or item.get("task_id") or "").strip()
        else:
            skill_id = str(item).strip()
        if skill_id:
            requests.append({"skill_id": skill_id, "source": "benchmark_env_request"})
    return requests


def runtime_capability_budget(repo_root: Path) -> dict[str, Any]:
    budget = merge_runtime_learning_policy(repo_root)
    status_report = os.environ.get("NEXUS_BENCH_SKILL_STATUS_REPORT", "").strip()
    if status_report:
        budget["skill_status_report"] = status_report
    overlay_path = (
        os.environ.get("NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY", "").strip()
        or os.environ.get("NEXUS_RUNTIME_SKILL_POLICY_OVERLAY", "").strip()
    )
    if overlay_path:
        budget["runtime_skill_policy_overlay_path"] = overlay_path
    if os.environ.get("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "").strip().lower() in {"1", "true", "yes", "on"}:
        budget["allow_ablation_skill_mounts"] = True
    return budget


def runtime_skill_overlay_requested(budget: dict[str, Any]) -> bool:
    return bool(
        budget.get("runtime_skill_policy_overlay")
        or str(budget.get("runtime_skill_policy_overlay_path") or "").strip()
    )


def build_route_executor_flags(*, task_desc: str, task_type: str, route: dict[str, Any]) -> dict[str, Any]:
    route_decision = route.get("route_decision") if isinstance(route, dict) else {}
    route_decision = route_decision if isinstance(route_decision, dict) else {}
    controls = route_decision.get("executor_controls") if isinstance(route_decision.get("executor_controls"), dict) else None
    if controls is None:
        plan_payload = route.get("capability_plan") if isinstance(route, dict) else {}
        controls = build_executor_controls(plan_payload) if isinstance(plan_payload, dict) and plan_payload.get("selected_capabilities") is not None else {}
    return {
        "enable_autoreason_executor": bool(controls.get("enable_autoreason_executor", False)),
        "enable_ddtree_executor": bool(controls.get("enable_ddtree_executor", False)),
        "ddtree_max_candidates": int(controls.get("ddtree_max_candidates", 2) or 2),
        "enable_ultra_review": bool(controls.get("enable_ultra_review", False)),
        "enable_swarm": bool(controls.get("enable_swarm", False)),
        "enable_drone": bool(controls.get("enable_drone", False)),
        "enable_nightshift": bool(controls.get("enable_nightshift", False)),
        "enable_rlm": bool(controls.get("enable_rlm", False)),
    }
