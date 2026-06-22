# H5-0 Local-First Cloud-Fallback Route Semantics Spec

**日期**: 2026-06-22
**狀態**: `H5_0_ROUTE_SEMANTICS_SPEC_COMPLETE`
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Scope

Read-only spec/audit. No implementation. No real model calls. No benchmark.

## Audited Files

| File | Lines Inspected | Purpose |
|------|----------------|---------|
| `scripts/bench/capability_ab_runner.py` | 5422-5590, 9235-9268 | hybrid_route attachment, bundle summary |
| `nexus/services/local_heal/committee_orchestrator.py` | 222-303 | U3 candidate selection, re-apply, hash verification |
| `nexus/services/local_heal/receipt.py` | 24-32, 507-508 | committee trace extraction |
| `nexus/services/local_heal/pipeline.py` | 199-205 | orchestrator selection |
| `nexus/services/local_heal/native_route_adapter.py` | 1-248 | route decision |
| `tests/benchmark/test_capability_ab_runner.py` | 13552-13719 | H3/H4/H4.5 hybrid route tests |
| `tests/unit/local_heal/test_committee_route_trace.py` | 1-850 | U3-1~U3-5 committee tests |

---

## 12 Questions Answered

### Q1: Where should H5 route mode be attached?

**Location**: `scripts/bench/capability_ab_runner.py`, inside `_finalize_with_nexus_row()` (line 5422), after the existing `hybrid_route` block (line 5526) and before `local_guard` (line 5576).

H5 metadata should be a sibling object `h5_route` on the finalized row, parallel to `hybrid_route`, `local_assist`, and `local_guard`.

### Q2: Which existing hybrid_route fields can be reused?

| Field | Reuse |
|-------|-------|
| `cloud_provider` | Yes — indicates cloud fallback target |
| `cloud_available` | Yes — indicates cloud fallback feasibility |
| `local_provider` | Yes — indicates local route provider |
| `local_available` | Yes — indicates local route feasibility |
| `cloud_model_invoked` | Yes — post-execution state |
| `local_model_invoked` | Yes — post-execution state (currently always false) |
| `behavior_changed` | Yes — must remain false in trace-only |
| `authority` | Yes — "trace_only" in H5-1 |

### Q3: Which new H5 fields are required?

See `h5_route` schema draft below. Key new fields:

- `local_attempted` — whether local committee route was attempted
- `local_route` — which local route was used ("committee")
- `local_candidate_count` — number of candidates generated
- `local_selected_candidate_id` — which candidate was selected
- `local_selected_candidate_applied` — whether selected candidate was applied
- `local_selected_candidate_hash_match` — whether hash matched
- `local_solve_eligible` — whether local route solved
- `local_failure_reason` — local route failure reason if any
- `cloud_fallback_allowed` — whether cloud fallback is permitted
- `cloud_fallback_invoked` — whether cloud fallback was invoked
- `final_source` — ultimate source of result ("none"/"local_candidate"/"cloud_fallback"/"fail_closed")

### Q4: What exact env flag should enable H5 trace-only mode?

```text
NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE=1
```

Read via `_env_truthy()` in `_finalize_with_nexus_row()`, parallel to existing `NEXUS_HYBRID_LOCAL_GUARD_TRACE`.

### Q5: What is the local attempt trigger?

```text
NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE=1
AND NEXUS_USE_COMMITTEE=1
AND local_available=true
AND U3 candidate isolation gates pass
```

In H5-1 (trace-only), local attempt is NOT triggered. The flag only produces trace metadata. Actual local attempt requires later H5-2+ approval.

### Q6: What is the cloud fallback trigger?

```text
NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE=1
AND local route attempted
AND local route failed (verifier_rejected / infra_unavailable / timeout)
AND cloud_available=true
```

In H5-1, cloud fallback is NOT triggered. Only trace metadata recorded.

### Q7: What is the fail-closed trigger?

```text
local_missing_candidate_mapping → fail_closed
local_missing_artifact → fail_closed (first implementation)
local_hash_mismatch → fail_closed
cloud_provider_unavailable → fail_closed
cloud_result_unverified → fail_closed
```

### Q8: How does U3 committee success/failure map into H5 route state?

| U3 State | H5 h5_route Mapping |
|----------|---------------------|
| U3 solve_eligible=true, hash_match=true | `local_solve_eligible=true`, `local_selected_candidate_hash_match=true`, `final_source="local_candidate"` (future) |
| U3 COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING | `local_failure_reason="COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING"`, `final_source="fail_closed"` |
| U3 COMMITTEE_SELECTED_CANDIDATE_ARTIFACT_MISSING | `local_failure_reason="COMMITTEE_SELECTED_CANDIDATE_ARTIFACT_MISSING"`, `final_source="fail_closed"` |
| U3 COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH | `local_failure_reason="COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH"`, `final_source="fail_closed"` |
| U3 VERIFIER_REJECTION | `local_failure_reason="VERIFIER_REJECTION:..."`, `cloud_fallback_allowed=true` (future) |
| U3 not invoked | `local_attempted=false`, `final_source="none"` |

### Q9: What fields prove local candidate was selected/applied/hash-matched?

```text
h5_route.local_selected_candidate_id = "C_12481#candidate-1"
h5_route.local_selected_candidate_applied = true
h5_route.local_selected_candidate_hash_match = true
h5_route.local_solve_eligible = true
```

These map from `committee_receipt.selected_candidate_id`, `selected_candidate_applied`, `selected_candidate_apply_hash_match`, and `ctx.op.solve_eligible`.

### Q10: What fields prove cloud fallback was invoked or not invoked?

```text
h5_route.cloud_fallback_allowed = false   (H5-1 trace-only)
h5_route.cloud_fallback_invoked = false   (H5-1 trace-only)
h5_route.cloud_provider = "gemini"        (from hybrid_route)
h5_route.cloud_model_invoked = false      (H5-1 trace-only)
```

### Q11: What fields prove H5 did not modify H1-H4 behavior when disabled?

```text
h5_route.enabled = false          (when NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE not set)
h5_route.behavior_changed = false
hybrid_route.behavior_changed = false  (existing H1-H4 field unchanged)
```

### Q12: What tests are required before H5-1 implementation?

1. H5 disabled leaves existing hybrid_route unchanged
2. H5 trace flag adds h5_route.enabled=true
3. H5 trace flag does not change behavior_changed
4. H5 trace flag does not invoke local committee route
5. H5 trace flag does not invoke cloud fallback
6. H5 trace fields preserve public_claim_allowed=false and production_ready=false
7. Bundle summary counts h5 trace rows without claiming success
8. Existing H1-H4 tests still pass

---

## Route Mode Names

```text
local_first_cloud_fallback_trace_only
local_first_cloud_fallback_local_attempted
local_first_cloud_fallback_cloud_used
local_first_cloud_fallback_local_success
local_first_cloud_fallback_fail_closed
```

---

## H5 Env Flag

```text
NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE=1
```

Initially enables trace-only H5 metadata. Does NOT enable production local-first behavior in H5-1.

---

## h5_route Schema Draft

```json
{
  "schema": "nexus.hybrid_h5_route.v1",
  "enabled": false,
  "route_mode": "local_first_cloud_fallback_trace_only",
  "authority": "trace_only",
  "local_attempted": false,
  "local_route": "committee",
  "local_candidate_count": 0,
  "local_selected_candidate_id": "",
  "local_selected_candidate_applied": false,
  "local_selected_candidate_hash_match": false,
  "local_solve_eligible": false,
  "local_failure_reason": "",
  "cloud_fallback_allowed": false,
  "cloud_fallback_invoked": false,
  "cloud_provider": "",
  "cloud_model_invoked": false,
  "final_source": "none",
  "behavior_changed": false,
  "blocked_delivery": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

### final_source Values

| Value | Meaning |
|-------|---------|
| `none` | H5 not active or no route executed |
| `local_candidate` | Local committee candidate solved (future) |
| `cloud_fallback` | Cloud fallback invoked after local failure (future) |
| `fail_closed` | All paths failed or invariant violated |

---

## Trigger Semantics

### Rule A: H5 disabled

```text
NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE not set
→ h5_route absent or h5_route.enabled=false
→ Existing H1-H4 behavior unchanged
→ behavior_changed=false
```

### Rule B: H5 trace-only enabled (H5-1)

```text
NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE=1
→ h5_route.enabled=true
→ h5_route.authority="trace_only"
→ No route order changes
→ No local-first execution change
→ No cloud fallback execution change
→ behavior_changed=false
```

### Rule C: Future H5 local-first enabled (NOT in this task)

```text
Local committee route may be attempted first only after explicit later approval.
If local candidate succeeds and hash matches, final_source="local_candidate".
If local fails safely, cloud fallback may be invoked.
If both fail or mapping/hash invariants fail, final_source="fail_closed".
```

---

## Fallback Gates

| Trigger | H5-1 Behavior | Future Behavior |
|---------|---------------|-----------------|
| local_missing_candidate_mapping | fail_closed | fail_closed |
| local_missing_artifact | fail_closed | fail_closed (recommended) |
| local_hash_mismatch | fail_closed | fail_closed |
| local_verifier_rejected | cloud_fallback_allowed | cloud_fallback_allowed |
| local_infra_unavailable | cloud_fallback_allowed | cloud_fallback_allowed |
| local_timeout | cloud_fallback_allowed | cloud_fallback_allowed |
| cloud_provider_unavailable | fail_closed | fail_closed |
| cloud_result_unverified | fail_closed | fail_closed |

---

## H5-1 Test Plan

| # | Test | Assertion |
|---|------|-----------|
| 1 | H5 disabled | h5_route absent or enabled=false, hybrid_route unchanged |
| 2 | H5 trace flag | h5_route.enabled=true, route_mode="trace_only" |
| 3 | H5 behavior_changed | h5_route.behavior_changed=false |
| 4 | H5 no local attempt | h5_route.local_attempted=false |
| 5 | H5 no cloud fallback | h5_route.cloud_fallback_invoked=false |
| 6 | H5 internal-only | h5_route.public_claim_allowed=false, production_ready=false |
| 7 | Bundle summary | h5_trace_count in hybrid_route_summary, no success claim |
| 8 | H1-H4 regression | All existing tests pass unchanged |

---

## Statements

```text
No implementation.
No real model calls.
No benchmark.
Not H5 ready.
Not local-first ready.
public_claim_allowed=false.
production_ready=false.
```
