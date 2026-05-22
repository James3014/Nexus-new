from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def dict_view(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def dict_list_view(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def phase_wall_from_trace(*, timing: dict[str, Any], usage_trace: dict[str, Any]) -> dict[str, Any]:
    phase_wall = dict_view(timing).get("phase_wall_sec") or dict_view(usage_trace).get("phase_wall_sec") or {}
    return dict_view(phase_wall)


@dataclass(frozen=True)
class SkillMountView:
    contracts: list[dict[str, Any]]
    violations: list[dict[str, Any]]
    status: str


def skill_mount_view(usage_trace: dict[str, Any]) -> SkillMountView:
    trace = dict_view(usage_trace)
    raw_contracts = trace.get("skill_mount_contract")
    if raw_contracts is None:
        raw_contracts = trace.get("skill_mount_contracts")
    contracts = dict_list_view(raw_contracts)
    violations = dict_list_view(trace.get("skill_mount_violations"))
    if violations:
        status = "RETURN"
    elif contracts:
        status = "PASS"
    else:
        status = "EMPTY"
    return SkillMountView(contracts=contracts, violations=violations, status=status)


def governance_event_types(events: Any) -> list[str]:
    rows = events if isinstance(events, list) else []
    return sorted(
        {
            str(item.get("event_type") or "")
            for item in rows
            if isinstance(item, dict) and str(item.get("event_type") or "")
        }
    )
