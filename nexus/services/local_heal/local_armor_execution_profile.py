import os
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class LocalArmorProfile:
    profile: str  # LITE, STANDARD, FULL
    reason: str
    planner_routing_tier: str
    planning_llm_allowed: bool
    spec_gen_allowed: bool
    candidate_cap: int
    semantic_retry_cap: int
    committee_allowed: bool
    autoreason_allowed: bool
    ddtree_allowed: bool
    escalation_allowed: bool
    required_gates: List[str] = field(default_factory=list)

def resolve_local_armor_profile(route_context: dict) -> LocalArmorProfile:
    """Resolve adaptive local armor execution profile from routing context signals."""
    if not isinstance(route_context, dict):
        route_context = {}

    signal_snapshot = route_context.get("signal_snapshot", {}) if isinstance(route_context, dict) else {}
    if not isinstance(signal_snapshot, dict):
        signal_snapshot = {}

    # Extract signals
    routing_tier = str(signal_snapshot.get("routing_tier", "") or "")
    routing_tier_reason = str(signal_snapshot.get("routing_tier_reason", "") or "")
    risk_score = int(signal_snapshot.get("risk_score_0_100", signal_snapshot.get("risk_score", 0)) or 0)
    confidence = float(signal_snapshot.get("confidence", 1.0) or 1.0)
    cross_module = bool(signal_snapshot.get("cross_module", False))
    hard_signal = bool(signal_snapshot.get("hard_signal", False))
    candidate_count = int(signal_snapshot.get("candidate_count", 1) or 1)
    reasoning_mode = str(signal_snapshot.get("reasoning_mode", "INTUITIVE"))
    task_desc = str(signal_snapshot.get("task_desc", ""))

    locked_search = str(route_context.get("locked_search", "") or "")
    verifier_command = list(route_context.get("verifier_command", []) or [])

    # Structural signals
    source_anchor_present = bool(locked_search.strip() or (route_context.get("target_file") and route_context.get("target_symbol")))
    verifier_present = bool(verifier_command)

    # Evaluator-only full mode must be resolved here so runtime controls and
    # receipts observe the same profile decision.
    if os.environ.get("NEXUS_FORCE_FULL_ARMOR") == "1":
        return build_profile_controls("FULL", "env_force_full_armor", routing_tier)

    # 1. Determine LITE preconditions
    is_routing_tier_lite = routing_tier in ("L0_micro_patch", "L1_green_lane") or "light" in routing_tier_reason.lower() or "green_lane" in routing_tier_reason.lower()
    has_lite_support = (
        is_routing_tier_lite
        and risk_score < 30
        and confidence >= 0.85
        and not cross_module
        and not hard_signal
        and candidate_count <= 1
        and source_anchor_present
        and verifier_present
        and "recursion" not in task_desc.lower()
        and "recursive" not in task_desc.lower()
        and "stateful" not in task_desc.lower()
        and reasoning_mode == "FAST"
    )

    # 2. Determine FULL preconditions
    has_full_support = (
        routing_tier == "L3_swarm_deep"
        or risk_score >= 70
        or cross_module
        or hard_signal
        or candidate_count > 1
        or confidence < 0.70
        or "recursion" in task_desc.lower()
        or "recursive" in task_desc.lower()
        or "stateful" in task_desc.lower()
    )

    # If planner signals are completely missing, fail closed to STANDARD
    if not signal_snapshot:
        profile = "STANDARD"
        reason = "missing_planner_signals_fail_closed_to_standard"
    elif has_full_support:
        profile = "FULL"
        reason = "full_profile_triggered_by_signals"
    elif has_lite_support:
        profile = "LITE"
        reason = "lite_profile_triggered_by_signals"
    else:
        profile = "STANDARD"
        reason = "standard_profile_triggered_by_signals"

    return build_profile_controls(profile, reason, routing_tier)

def build_profile_controls(profile: str, reason: str, routing_tier: str) -> LocalArmorProfile:
    """Construct granular context control switches for the specified profile."""
    # Debug bypass / force overrides
    if os.environ.get("NEXUS_FAST_MODE") == "1":
        profile = "LITE"
        reason = "env_override_fast_mode"

    if profile == "LITE":
        return LocalArmorProfile(
            profile="LITE",
            reason=reason,
            planner_routing_tier=routing_tier,
            planning_llm_allowed=False,
            spec_gen_allowed=False,
            candidate_cap=1,
            semantic_retry_cap=0,
            committee_allowed=False,
            autoreason_allowed=False,
            ddtree_allowed=False,
            escalation_allowed=True,
            required_gates=["minimal_evidence", "source_provenance", "candidate_isolation", "applied_candidate_hash", "verifier", "receipt", "claim_boundary"]
        )
    elif profile == "STANDARD":
        # spec_gen is disabled if NEXUS_DISABLE_SPEC_GEN=1 env var is set
        spec_gen = os.environ.get("NEXUS_DISABLE_SPEC_GEN", "0") != "1"
        return LocalArmorProfile(
            profile="STANDARD",
            reason=reason,
            planner_routing_tier=routing_tier,
            planning_llm_allowed=True,
            spec_gen_allowed=spec_gen,
            candidate_cap=1,
            semantic_retry_cap=1,
            committee_allowed=False,
            autoreason_allowed=False,
            ddtree_allowed=False,
            escalation_allowed=True,
            required_gates=["standard"]
        )
    else:  # FULL
        return LocalArmorProfile(
            profile="FULL",
            reason=reason,
            planner_routing_tier=routing_tier,
            planning_llm_allowed=True,
            spec_gen_allowed=True,
            candidate_cap=3,
            semantic_retry_cap=2,
            committee_allowed=True,
            autoreason_allowed=True,
            ddtree_allowed=True,
            escalation_allowed=False,
            required_gates=["full"]
        )
