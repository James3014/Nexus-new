from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import default_capability_nodes
from nexus.engine.capability_receipt_policy import is_receipt_backed_capability


PREFERRED_TACTICAL_ORDER = (
    "pregate",
    "memory",
    "lancedb",
    "semantic_searcher",
    "research",
    "external_doc_scout",
    "codeintel",
    "hyper",
    "autoreason",
    "judge_panel",
    "llm_judge_panel",
    "ddtree",
    "belief",
    "ultra_review",
    "formal_report",
    "delivery_gate",
    "claim_gate",
    "swarm_quiet_moment",
)

EVIDENCE_GATHERING_CAPABILITIES = {
    "semantic_searcher",
    "external_doc_scout",
    "research",
    "lancedb",
    "codeintel",
}

ALWAYS_ON_CONTROL_STEPS = ("pregate", "plan_quality_gate")

def _requires_research_evidence_step(plan: CapabilityPlan) -> bool:
    snapshot = plan.signal_snapshot if isinstance(plan.signal_snapshot, dict) else {}
    isolation = snapshot.get("research_isolation_policy")
    if not isinstance(isolation, dict):
        return False
    level = str(isolation.get("level", "")).strip().upper()
    return level in {"L1", "L2"}

def build_tactical_stop_policy(
    *,
    plan: CapabilityPlan,
    recommended_flow: str,
    base_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the tactical route policy emitted by the canonical route decision seam."""
    policy = dict(base_policy or {"type": "receipt_backed", "budget_guard": "fail_closed"})
    selected = [str(item) for item in plan.selected_capabilities if str(item).strip()]
    for control_step in ALWAYS_ON_CONTROL_STEPS:
        if control_step not in selected:
            selected.append(control_step)
    if _requires_research_evidence_step(plan) and "research" not in selected:
        selected.append("research")
    first = "hyper_sprint" if recommended_flow == "hyper_sprint" or "hyper" in selected else "baseline"
    tactical_sequence = [first]
    tactical_sequence.extend(name for name in PREFERRED_TACTICAL_ORDER if name in selected)
    tactical_sequence.extend(name for name in selected if name not in tactical_sequence)
    tactical_sequence = list(dict.fromkeys(tactical_sequence))

    nodes = default_capability_nodes()
    tactical_tool_map = []
    for index, name in enumerate(tactical_sequence):
        node = nodes.get(name)
        evidence_required = bool(node and node.evidence_outputs and is_receipt_backed_capability(name))
        if name in ALWAYS_ON_CONTROL_STEPS:
            evidence_required = False
        tactical_tool_map.append(
            {
                "capability": name,
                "after": tactical_sequence[index - 1] if index else None,
                "purpose": "gather_evidence" if name in EVIDENCE_GATHERING_CAPABILITIES else "verify_or_govern",
                "evidence_required": evidence_required,
            }
        )
    policy.setdefault("tactical_sequence", tactical_sequence)
    policy.setdefault("tactical_tool_map", tactical_tool_map)
    return policy
