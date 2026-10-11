"""The 27 planner sources owned by nexus-runtime (D2, Phase 4b)."""
from __future__ import annotations

_SUPPORT = {
    "nexus.contracts.canonical_execution": "nexus_runtime.support.contracts.canonical_execution",
    "nexus.engine.canonical_execution": "nexus_runtime.support.engine.canonical_execution",
}
_PLANNING = [
    "nexus.contracts.execution_identity",
    "nexus.contracts.workforce_admission",
    "nexus.core.belief_contracts",
    "nexus.core.lite_route_oracle",
    "nexus.engine.capability_aliases",
    "nexus.engine.capability_contracts",
    "nexus.engine.capability_planner",
    "nexus.engine.capability_signals",
    "nexus.engine.harness_route_policy",
    "nexus.engine.harness_sensors",
    "nexus.engine.local_assist_recommendation",
    "nexus.engine.policy_evaluator",
    "nexus.engine.route_signal_adapter",
    "nexus.engine.planner.ab_evaluator",
    "nexus.engine.planner.policy_applier",
    "nexus.engine.planner.skill_mount_evidence",
    "nexus.evidence.claim_boundary",
    "nexus.evidence.receipt_base",
    "nexus.learning.shared_playbook",
    "nexus.learning.skill_catalog",
    "nexus.research.isolation_contracts",
    "nexus.research.isolation_policy",
    "nexus.services.capability_evidence_bundle",
    "nexus.services.model_workforce_policy",
    "nexus.services.runtime_workforce_admission",
]

PAIRS: list[tuple[str, str]] = list(_SUPPORT.items()) + [
    (n, "nexus_runtime.planning." + n[len("nexus."):]) for n in _PLANNING
]
assert len(PAIRS) == 27

# Nexus-new is AHEAD of nexus-runtime 0456b78 for these (Step 0 equivalence gate
# failed beyond import paths); they must not be aliased until runtime catches up.
DIVERGENT = {
    "nexus.engine.canonical_execution",
    "nexus.engine.capability_planner",
    "nexus.services.capability_evidence_bundle",
}
ALIASABLE_PAIRS = [p for p in PAIRS if p[0] not in DIVERGENT]
DIVERGENT_PAIRS = [p for p in PAIRS if p[0] in DIVERGENT]
