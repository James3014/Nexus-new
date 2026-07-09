from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class P6MainlineBoundary:
    boundary_version: str = "1.0"
    p6_can_influence_candidate_count: bool = True
    p6_can_disable_cloud: bool = True
    p6_can_force_local_only: bool = True
    p6_can_mark_solved: bool = False
    p6_can_mark_claim_eligible: bool = False
    p6_can_set_public_claim_allowed: bool = False
    p6_can_override_p4_verifier: bool = False
    p6_can_override_p3_topology: bool = False
    p6_can_override_p5_selection: bool = False
    p6_requires_env_guard: bool = True
    p6_requires_receipt: bool = True
    p6_requires_monitor: bool = True
    p6_requires_canary_gate: bool = True
    reason: str = "guarded rollout candidate only"


def build_mainline_boundary() -> P6MainlineBoundary:
    """Build the P6 mainline boundary contract."""
    return P6MainlineBoundary()
