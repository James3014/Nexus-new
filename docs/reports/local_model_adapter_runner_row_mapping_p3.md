# Local Model Adapter: Runner Row Mapping Schema (P3)

## 1. Row Field Designation

A new adapter bridge field `row["local_model_adapter"]` will be added to the finalized with-nexus benchmark row payload.

---

## 2. Disabled Default Row Schema

By default, or when local model integration is disabled, the adapter row payload will default to:

```json
{
  "schema": "nexus.local_model_adapter_row.v1",
  "enabled": false,
  "adapter_invoked": false,
  "route_mode": "cloud_assisted_by_local_trace_only",
  "authority": "trace_only",
  "route_truth_source": "CapabilityPlanner",
  "adapter_output_is_route_truth": false,
  "public_claim_allowed": false,
  "production_ready": false,
  "behavior_changed": false,
  "local_model_called": false,
  "candidate_output_isolated": true,
  "selected_candidate_hash": "",
  "applied_patch_hash": "",
  "selected_candidate_hash_matches_applied": false,
  "verifier_result": "not_run",
  "evidence_refs": [],
  "fallback_block_reason": "disabled",
  "blockers": ["disabled"],
  "metadata": {}
}
```

---

## 3. Mapping from HybridRouteDecision

When enabled, fields from the contract's output `HybridRouteDecision.to_dict()` are mapped as follows:

| Source (HybridRouteDecision) | Destination (row.local_model_adapter) |
|---|---|
| `route_mode` | `route_mode` |
| `authority` | `authority` |
| `route_truth_source` | `route_truth_source` |
| `adapter_output_is_route_truth` | `adapter_output_is_route_truth` |
| `public_claim_allowed` | `public_claim_allowed` |
| `production_ready` | `production_ready` |
| `behavior_changed` | `behavior_changed` |
| `local_model_called` | `local_model_called` |
| `candidate_output_isolated` | `candidate_output_isolated` |
| `selected_candidate_hash` | `selected_candidate_hash` |
| `applied_patch_hash` | `applied_patch_hash` |
| `selected_candidate_hash_matches_applied` | `selected_candidate_hash_matches_applied` |
| `verifier_result` | `verifier_result` |
| `evidence_refs` | `evidence_refs` |
| `fallback_block_reason` | `fallback_block_reason` |
| `blockers` | `blockers` |
| `metadata` | `metadata` |

---

## 4. Mapping from LocalHealCapabilityResponse

When the adapter responds, the execution meta-data fields map to the row payload:

| Source (LocalHealCapabilityResponse) | Destination (row.local_model_adapter) |
|---|---|
| `response.invoked` | `row.local_model_adapter.adapter_invoked` |
| `response.capability_payload` | `row.local_model_adapter.metadata.adapter_payload` |
| `response.hybrid_route` | (Triggers the `HybridRouteDecision` fields mapping above) |

---

## 5. Evidence Bundle Summary Payload

The final benchmark runner summary will accumulate adapter statistics in the `local_model_adapter_summary` object inside the evidence bundle:

```json
{
  "local_model_adapter_summary": {
    "adapter_trace_count": 0,
    "adapter_invoked_count": 0,
    "local_model_called_count": 0,
    "candidate_isolated_count": 0,
    "hash_match_count": 0,
    "verifier_pass_count": 0,
    "fail_closed_count": 0,
    "behavior_changed_count": 0,
    "public_claim_allowed_count": 0,
    "production_ready_count": 0
  }
}
```

---

## 6. Relationship with h5_route

- `h5_route` remains the existing H5 trace scaffold.
- `local_model_adapter` functions as the adapter bridge row.
- The evidence bundle will summarize both fields separately.
- **Do not merge** the two fields; they must remain isolated until a subsequent explicit mapping phase.

---

## 7. Required Blockers

The following explicit failure/blocker strings must be populated in the `blockers` list when applicable:
- `missing_adapter_context`
- `model_call_not_allowed`
- `mutation_not_allowed`
- `verifier_not_allowed`
- `missing_required_control`
- `local_guard_fail_closed`
- `invalid_route_truth_source`
- `public_claim_allowed_must_be_false`
- `production_ready_must_be_false`
- `behavior_changed_true`

---
**Status**: SPEC_DEFINED (Ready for P4 implementation wiring)
