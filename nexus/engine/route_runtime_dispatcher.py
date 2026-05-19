from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RouteRuntimeDispatcher:
    """Consume read-only route runtime plans without executing dispatch."""

    def prepare(self, runtime_plan: Mapping[str, Any]) -> dict[str, Any]:
        blockers = _blockers(runtime_plan)
        return {
            "schema": "nexus.route_runtime_dispatch_preparation.v1",
            "status": "PASS" if not blockers else "RETURN",
            "dispatch_ready": not blockers,
            "dispatch_executed": False,
            "runtime_dispatch_changed": False,
            "claim_verdict": "NOT_EVALUATED",
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "execution_slots": list(runtime_plan.get("execution_slots", []) or []),
            "isolated_serial_capabilities": list(runtime_plan.get("isolated_serial_capabilities", []) or []),
            "blockers": blockers,
            "claim_boundary": [
                "Route runtime dispatcher preparation consumes plans without executing work.",
                "It must not decide delivery, promotion, public readiness, or claim verdicts.",
            ],
        }


def _blockers(runtime_plan: Mapping[str, Any]) -> list[str]:
    blockers = list(runtime_plan.get("blockers", []) or [])
    if runtime_plan.get("status") != "PASS":
        blockers.append("route_runtime_plan_not_pass")
    if bool(runtime_plan.get("runtime_dispatch_changed", False)):
        blockers.append("runtime_dispatch_changed")
    if bool(runtime_plan.get("public_benchmark_allowed", False)):
        blockers.append("public_benchmark_allowed_in_runtime_plan")
    if bool(runtime_plan.get("runtime_update_allowed", False)):
        blockers.append("runtime_update_allowed_in_runtime_plan")
    if str(runtime_plan.get("claim_verdict") or "NOT_EVALUATED") != "NOT_EVALUATED":
        blockers.append("claim_verdict_evaluated_in_runtime_plan")
    return sorted(set(str(blocker) for blocker in blockers if str(blocker)))
