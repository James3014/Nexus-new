"""Repro: claim-gate fail-closed contract bypassed by two receipt adapters.

AGENTS.md: "Missing verifier artifact/status or source hash fails claim gates closed."
CLAIM_AND_RECEIPT_OVERLAY.md: "Receipt adapters must validate verifier artifact/status and source hash;
never trust claim_verified=true alone."
"""
import sys
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.engine.capability_receipts import build_trace_receipts
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS

TELEM = {"telemetry_source": "measured", "wall_time_ms": 10, "token_usage": 5,
         "provider_costs": 0, "overhead_ms": 1, "model_calls": 1}

# A) local_model_executor: caller-supplied dict receipt copied verbatim (no verifier, no source hash,
#    claim_verified=False).
caps = {"claim_verified": False,
        "local_executor_receipt": {"invoked": True, "evidence_present": True, "gate_passed": True,
                                   "outcome_contributed": True, "evidence_refs": ["forged:ref"],
                                   "telemetries": TELEM}}
r = build_trace_receipts(plan={"selected_capabilities": ["local_model_executor"]}, capabilities=caps)[0]
print("A local_model_executor gate_passed=%s outcome_contributed=%s public_claim_safe=%s" %
      (r.gate_passed, r.outcome_contributed, r.public_claim_safe))
# semantic invariant check: outcome without evidence
r2 = RECEIPT_ADAPTERS["local_model_executor"].build(claim_verified=False, payload={"local_executor_receipt": {
    "invoked": False, "evidence_present": False, "gate_passed": False, "outcome_contributed": True}})
print("A' outcome_contributed without invoked/evidence/gate:", r2.outcome_contributed)

# B) local_heal hybrid_route LOCAL_ONLY_EXECUTED with selected != applied hash but boolean says match;
#    no verifier_artifact / source_hash anywhere.
hr = {"schema": "nexus.hybrid_route_decision.v1", "execution_world": "product_runtime",
      "execution_topology": "ASSISTED_CANONICAL", "route_mode": "local_only_executed",
      "route_truth_source": "CapabilityPlanner", "authority": "candidate_only",
      "local_model_called": True, "verifier_result": "pass", "evidence_refs": ["x"],
      "candidate_output_isolated": True,
      "selected_candidate_hash": "sha256:" + "a" * 64, "applied_patch_hash": "sha256:" + "b" * 64,
      "selected_candidate_hash_matches_applied": True}
from nexus.contracts.hybrid_route import validate_hybrid_route_decision
print("B validate_hybrid_route_decision blockers (hashes differ):", validate_hybrid_route_decision(hr))
r3 = RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload={"hybrid_route": hr})
print("B local_heal gate_passed=%s outcome_contributed=%s" % (r3.gate_passed, r3.outcome_contributed))

# Contrast: claim_gate with the same (missing source_hash/verifier) fails closed
r4 = RECEIPT_ADAPTERS["claim_gate"].build(claim_verified=True, payload={"claim_refs": ["x"]})
print("contrast claim_gate gate_passed=%s reason=%s" % (r4.gate_passed, r4.failure_reason))
