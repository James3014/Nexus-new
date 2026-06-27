from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RouteMode(str, Enum):
    CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY = "cloud_assisted_by_local_trace_only"
    CLOUD_ASSISTED_BY_LOCAL_COMPACT_CONTEXT = "cloud_assisted_by_local_compact_context"
    CLOUD_FIRST_LOCAL_GUARD_ADVISORY = "cloud_first_local_guard_advisory"
    CLOUD_FIRST_LOCAL_GUARD_FAIL_CLOSED = "cloud_first_local_guard_fail_closed"
    LOCAL_FIRST_CLOUD_FALLBACK = "local_first_cloud_fallback"
    LOCAL_ONLY_PLANNED = "local_only_planned"
    LOCAL_ONLY_BLOCKED = "local_only_blocked"
    LOCAL_ONLY_EXECUTED = "local_only_executed"


@dataclass(frozen=True)
class HybridRouteDecision:
    route_mode: RouteMode = RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    public_claim_allowed: bool = False
    production_ready: bool = False
    adapter_output_is_route_truth: bool = False
    route_truth_source: str = "CapabilityPlanner"
    local_guard: dict[str, Any] = field(default_factory=dict)
    behavior_changed: bool = False
    authority: str = ""
    cloud_model_called: bool = False
    local_model_called: bool = False
    candidate_output_isolated: bool = True
    verifier_result: str = "not_run"
    evidence_refs: tuple[str, ...] = ()
    fallback_block_reason: str = ""

    def __post_init__(self) -> None:
        if self.route_truth_source != "CapabilityPlanner":
            raise ValueError("route_truth_source must be 'CapabilityPlanner'")
        if self.public_claim_allowed:
            raise ValueError("public_claim_allowed=True is forbidden under current security posture")
        if self.route_mode == RouteMode.LOCAL_ONLY_EXECUTED:
            if (
                self.verifier_result == "not_run"
                or not self.evidence_refs
                or not self.candidate_output_isolated
            ):
                raise ValueError(
                    "local_only_executed requires verifier_result, evidence_refs, and candidate_output_isolated"
                )
