"""Plan automatic capability-to-skill discovery without runtime promotion."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from nexus.learning.skill_fit_ablation_core import build_skill_fit_ablation_plan


def _capability_list(candidate_pool: Mapping[str, Any], explicit: Iterable[str] = ()) -> list[str]:
    requested = [str(item).strip() for item in explicit if str(item).strip()]
    if requested:
        return sorted(dict.fromkeys(requested))
    capabilities = {
        str(capability)
        for candidate in candidate_pool.get("candidates", [])
        if isinstance(candidate, Mapping)
        for capability in candidate.get("capability_candidates", [])
        if str(capability)
    }
    return sorted(capabilities)


def _refresh_plan_by_capability(refresh_plan: Mapping[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(refresh_plan, Mapping):
        return {}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in refresh_plan.get("due", []) or []:
        if not isinstance(item, Mapping):
            continue
        topic = str(item.get("topic") or "")
        capability = str(item.get("capability_id") or "")
        if topic.startswith("skill:"):
            capability = topic.removeprefix("skill:")
        elif topic.startswith("sf:"):
            capability = topic.removeprefix("sf:")
        elif not capability:
            capability = topic
        if capability:
            out[capability].append(dict(item))
    return out


def _catalog_primary_by_capability(catalog: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(catalog, Mapping):
        return {}
    out = {}
    for item in catalog.get("capability_skill_catalog", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = str(item.get("capability_id") or item.get("capability") or "")
        primary = str(item.get("primary_default") or item.get("primary_skill_id") or "")
        if capability and primary:
            out[capability] = primary
    capabilities = catalog.get("capabilities")
    if isinstance(capabilities, Mapping):
        for capability, item in capabilities.items():
            if not isinstance(item, Mapping) or str(capability) in out:
                continue
            positive = str(item.get("default_candidate") or "")
            if not positive:
                candidates = item.get("replace_candidates") or item.get("alternate_candidates") or []
                positive = str(candidates[0]) if candidates else ""
            if positive:
                out[str(capability)] = positive
    return out


def _catalog_verdicts_by_capability(catalog: Mapping[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(catalog, Mapping):
        return {}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in catalog.get("skill_verdicts", []) or catalog.get("recommendations", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = str(item.get("capability") or item.get("capability_id") or "")
        if capability:
            out[capability].append(dict(item))
    capabilities = catalog.get("capabilities")
    if isinstance(capabilities, Mapping):
        for capability, item in capabilities.items():
            if not isinstance(item, Mapping):
                continue
            for skill_id in item.get("needs_more_data_normal_lane", []) or []:
                if str(skill_id):
                    out[str(capability)].append({"skill_id": str(skill_id), "verdict": "needs_more_data"})
    return out


def build_capability_skill_discovery_scheduler(
    candidate_pool: Mapping[str, Any],
    *,
    refresh_plan: Mapping[str, Any] | None = None,
    current_catalog: Mapping[str, Any] | None = None,
    capabilities: Iterable[str] = (),
    max_skill_arms: int = 4,
) -> dict[str, Any]:
    """Build a fail-closed SF discovery queue for capability-local skill tests."""

    failures: list[str] = []
    if candidate_pool.get("status") != "PASS":
        failures.append("candidate_pool_not_pass")
    due_by_capability = _refresh_plan_by_capability(refresh_plan)
    primary_by_capability = _catalog_primary_by_capability(current_catalog)
    verdicts_by_capability = _catalog_verdicts_by_capability(current_catalog)
    scheduled: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    for capability in _capability_list(candidate_pool, capabilities):
        plan = build_skill_fit_ablation_plan(
            candidate_pool,
            capability=capability,
            max_skill_arms=max_skill_arms,
        )
        skill_arms = [item for item in plan.get("arms", []) if item.get("arm_type") == "skill_ablation"]
        needs_more_data = [
            str(item.get("skill_id") or "")
            for item in verdicts_by_capability.get(capability, [])
            if str(item.get("verdict") or "") == "needs_more_data"
        ]
        if capability in primary_by_capability and needs_more_data:
            action = "targeted_replay_needs_more_data"
        elif capability in primary_by_capability:
            action = "monitor_new_candidates"
        elif not skill_arms:
            action = "refresh_sources_then_rescreen"
        elif needs_more_data:
            action = "targeted_replay_needs_more_data"
        else:
            action = "build_flash30_ablation_matrix"
        action_counts[action] += 1
        scheduled.append(
            {
                "capability_id": capability,
                "next_action": action,
                "due_source_count": len(due_by_capability.get(capability, [])),
                "candidate_arm_count": len(skill_arms),
                "candidate_skill_ids": [str(item.get("skill_id") or "") for item in skill_arms],
                "current_primary_skill_id": primary_by_capability.get(capability, ""),
                "needs_more_data_skill_ids": needs_more_data,
                "negative_control_count": int(plan.get("summary", {}).get("negative_control_count") or 0),
                "plan_status": plan.get("status", ""),
                "claim_boundary": "discovery_only_no_runtime_promotion",
            }
        )
    return {
        "schema": "nexus.sf_capability_skill_discovery_scheduler.v1",
        "status": "PASS" if not failures else "RETURN",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "summary": {
            "capability_count": len(scheduled),
            "scheduled_count": len(scheduled),
            "due_source_capability_count": len(due_by_capability),
            "action_counts": dict(sorted(action_counts.items())),
            "candidate_pool_schema": candidate_pool.get("schema", ""),
            "current_catalog_schema": current_catalog.get("schema", "") if isinstance(current_catalog, Mapping) else "",
        },
        "failures": failures,
        "scheduled": scheduled,
        "claim_boundary": [
            "This scheduler only plans discovery and validation work.",
            "Catalog verdicts require receipt-backed live evidence.",
            "Runtime defaults and public benchmarks remain separate gates.",
        ],
    }


def write_capability_skill_discovery_scheduler(
    *,
    candidate_pool_path: str | Path,
    output_path: str | Path,
    refresh_plan_path: str | Path | None = None,
    current_catalog_path: str | Path | None = None,
    capabilities: Iterable[str] = (),
    max_skill_arms: int = 4,
) -> dict[str, Any]:
    candidate_pool = json.loads(Path(candidate_pool_path).read_text(encoding="utf-8"))
    refresh_plan = (
        json.loads(Path(refresh_plan_path).read_text(encoding="utf-8"))
        if refresh_plan_path and Path(refresh_plan_path).exists()
        else None
    )
    current_catalog = (
        json.loads(Path(current_catalog_path).read_text(encoding="utf-8"))
        if current_catalog_path and Path(current_catalog_path).exists()
        else None
    )
    scheduler = build_capability_skill_discovery_scheduler(
        candidate_pool,
        refresh_plan=refresh_plan,
        current_catalog=current_catalog,
        capabilities=capabilities,
        max_skill_arms=max_skill_arms,
    )
    Path(output_path).write_text(json.dumps(scheduler, indent=2, ensure_ascii=False), encoding="utf-8")
    return scheduler
