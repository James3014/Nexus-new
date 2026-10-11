"""Repro: validate_learning_policy_adoption (used by AdoptionStore.write_adoption and by
the sink project_adoption_into_planner_budget) only re-checks the adoption's own
self-computed content address. It never re-verifies the bound recommendation /
validation, never recomputes target_policy_hash, and never re-applies the
forbidden-delta (CapabilityPlanner / route_authority / workforce_admission) rule
that only build_learning_policy_adoption enforces."""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, "/home/user/nexus-learning")
from nexus_learning.contracts import (canonical_adoption_identity, validate_learning_policy_adoption,
                                      project_adoption_into_planner_budget)
from nexus_learning.adoption import AdoptionStore
from nexus_learning.state_root import LearningStateRoot

forged = {
    "schema": "nexus.learning_policy_adoption.v1",
    "owner_authority_reference": "anyone",
    "recommendation_id": "lrec:does-not-exist", "recommendation_hash": "0" * 64,
    "validation_id": "lval:does-not-exist", "validation_hash": "0" * 64,
    "source_revision": "rev-x",
    "adopted_scope": {"task_family": "local_heal"},
    "target_policy_delta": {"CapabilityPlanner": {"force_route": "evil"}, "workforce_admission": "open",
                            "episodic_memory_injection": {"enabled": True}},
    "target_policy_hash": "f" * 64,          # not hash(target_policy_delta)
    "previous_policy": {}, "previous_policy_hash": "e" * 64,
    "rollback_target": {"target_state": {"memory_retrieval": "shadow"}},
    "adoption_status": "ACTIVE_CANDIDATE", "claim_ceiling": "SUPPORTED_POLICY_RECOMMENDATION",
    "route_truth_source": "CapabilityPlanner", "direct_route_mutation_allowed": False,
}
h, i = canonical_adoption_identity(forged)
forged["adoption_hash"], forged["adoption_id"] = h, i
validate_learning_policy_adoption(forged)
print("validate_learning_policy_adoption(forged): ACCEPTED")
root = Path(tempfile.mkdtemp())
p = AdoptionStore(LearningStateRoot(root)).write_adoption(forged)
print("AdoptionStore.write_adoption: wrote", p.relative_to(root))
print("read_adoption delta:", json.dumps(AdoptionStore(LearningStateRoot(root)).read_adoption()["target_policy_delta"], sort_keys=True))
budget = project_adoption_into_planner_budget(forged, task_desc="local_heal repair")
print("planner budget:", json.dumps(budget["learning_policy"]["episodic_memory_injection"]), budget["learning_policy"]["adoption_lineage"]["status"])
