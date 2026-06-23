# H5-13 Execution Enablement Criteria Spec

**日期**: 2026-06-22
**狀態**: `H5_13_EXECUTION_ENABLEMENT_CRITERIA_SPEC_COMPLETE`
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## 1. Current H5 Status

H5-0 ~ H5-12 完成。整個 H5 trace-only scaffold 已建立：

| Phase | Status | Commit |
|-------|--------|--------|
| H5-0 | Route semantics spec | 412343e0 |
| H5-1 | Trace-only metadata | 7d6685eb |
| H5-2 | Dry-run local attempt trace | d0f4ee22 |
| H5-3 | Cloud fallback eligibility | fc69891a |
| H5-4 | Cloud fallback decision dry-run | e36474d2 |
| H5-5 | Route-order shadow simulation | d5421a3f |
| H5-6 | Execution gate preflight | c9f66e52 |
| H5-7 | Execution adapter audit | 826a8dd6 |
| H5-8 | Execution plan builder | 3f953115 |
| H5-9 | Execution plan gate matrix | 0733ea49 |
| H5-10 | Local finalization shadow receipt | 11ebb5a1 |
| H5-11 | Cloud finalization shadow receipt | 1df8f028 |
| H5-12 | Execution readiness preflight | 9536a0e6 |

## 2. Execution is Still Disabled

```text
execution_ready = false（always）
readiness_status = "blocked"（always）
execution_gate_allows_local_first = false（always）
execution_gate_allows_cloud_fallback = false（always）
execution_gate_allows_final_source_change = false（always）
execution_gate_allows_behavior_change = false（always）
final_source = "none"（always for normal rows）
behavior_changed = false（always for normal rows）
cloud_fallback_invoked = false（always）
cloud_model_invoked = false（always）
```

## 3. Criteria Before Local Candidate Execution

Before any local candidate can become final, ALL must be true:

| # | Criterion | Source |
|---|-----------|--------|
| 1 | U3 candidate_id stable | U3-1 accepted |
| 2 | Selected candidate has candidate_id | U3-1 accepted |
| 3 | Selected candidate was applied | U3-3C accepted |
| 4 | Selected candidate hash matches applied hash | U3-3B accepted |
| 5 | Selected candidate has patch_sha256 | U3-2 accepted |
| 6 | Selected candidate has patch_length > 0 | U3-2 accepted |
| 7 | local_solve_eligible=true | U3 committee result |
| 8 | Verifier accepted | Existing verifier gate |
| 9 | Claim gate accepted | Existing claim gate |
| 10 | h5_local_finalization_shadow_receipt would_finalize_local_candidate=true in synthetic preflight | H5-10 |
| 11 | Normal finalized rows still do not change final_source | H5-9 invariant |
| 12 | Rollback/fail-closed path exists | U3 fail-closed paths |
| 13 | Focused test passes | H5-9 gate matrix |
| 14 | No public or production claims | Governance boundary |

## 4. Criteria Before Cloud Fallback Execution

Before any cloud fallback can become final, ALL must be true:

| # | Criterion | Source |
|---|-----------|--------|
| 1 | cloud_fallback_eligible=true | H5-3 |
| 2 | cloud_fallback_decision="would_invoke_cloud_fallback" | H5-4 |
| 3 | cloud_fallback_would_invoke=true | H5-4 |
| 4 | cloud_provider in {"gemini", "codex"} | H5-3 |
| 5 | Cloud fallback output captured | New |
| 6 | Cloud fallback output verified | New |
| 7 | Claim gate accepted | Existing claim gate |
| 8 | model_calls accounting defined | New |
| 9 | h5_cloud_fallback_finalization_shadow_receipt would_finalize_cloud_fallback=true in synthetic preflight | H5-11 |
| 10 | Normal finalized rows still do not invoke cloud | H5-9 invariant |
| 11 | Rollback/fail-closed path exists | New |
| 12 | No public or production claims | Governance boundary |

## 5. Criteria Before final_source May Change

final_source may not change until:

| # | Criterion |
|---|-----------|
| 1 | Execution gate has explicit future allow flag |
| 2 | Execution plan has execution_allowed=true |
| 3 | Selected final source is one of: local_candidate, cloud_fallback, fail_closed |
| 4 | Output replacement is verified |
| 5 | final_patch replacement is verified |
| 6 | behavior_changed=true is intentionally set and tested |
| 7 | Summary counters distinguish shadow vs actual |
| 8 | Receipt records before/after state |

## 6. Criteria Before behavior_changed May Become True

| # | Criterion |
|---|-----------|
| 1 | Actual execution occurred (not shadow) |
| 2 | Output was replaced with real result |
| 3 | Result was verified by verifier |
| 4 | Claim gate accepted |
| 5 | Summary counters distinguish shadow vs actual |
| 6 | Rollback path exists |

## 7. Criteria Before model_calls May Increment

| # | Criterion |
|---|-----------|
| 1 | Real cloud fallback is actually called |
| 2 | Provider is explicit |
| 3 | Call count is deterministic |
| 4 | Shadow model_calls_after_shadow has already been tested |
| 5 | No duplicate model call path exists |
| 6 | Failure path does not overcount |

## 8. Criteria Before production_ready May Become True

| # | Criterion |
|---|-----------|
| 1 | Real local committee E2E validation |
| 2 | Real cloud fallback E2E validation |
| 3 | Quality non-regression test |
| 4 | Full benchmark |
| 5 | Governance approval |

## 9. Criteria Before public_claim_allowed May Become True

| # | Criterion |
|---|-----------|
| 1 | production_ready=true |
| 2 | External provider claim boundary passes |
| 3 | Promotion readiness contract passes |
| 4 | No simulated-only claims remain |

## 10. Required Next Phases

### H5-14: Local Committee E2E Preflight Spec

```text
Audit how to run a real local committee path safely.
No execution from benchmark runner yet.
Define isolation requirements, rollback points, and verification hooks.
```

### H5-15: Local Committee E2E Focused Smoke

```text
Run local committee in isolated/focused path.
No final source change.
Verify committee trace fields with real model output.
```

### H5-16: Cloud Fallback E2E Preflight Spec

```text
Audit real cloud fallback call path.
No cloud call yet.
Define provider selection, auth, retry, and rollback.
```

### H5-17: Cloud Fallback E2E Focused Smoke

```text
One controlled cloud fallback smoke only if approved.
No production claim.
Verify cloud fallback output, model_calls accounting, and rollback.
```

### H5-18: Execution Flag Design Spec

```text
Define first disabled-by-default execution flag.
Still no execution unless explicitly approved later.
Flag must be gated by all criteria in this spec.
```

## 11. No-Go Conditions

Any of these MUST block execution:

| Condition | Reason |
|-----------|--------|
| `local_hash_mismatch` | Hash integrity violated |
| `local_missing_artifact` | Candidate artifact missing |
| `local_missing_candidate_mapping` | Candidate mapping failed |
| `cloud_provider_unavailable` | Cloud provider not available |
| `cloud_result_unverified` | Cloud result not verified |
| `unexpected_execution_side_effect` | Side effect detected |
| `governance_boundary_violation` | Governance boundary violated |
| `behavior_changed` before explicit execution | Unexpected behavior change |
| `final_source != "none"` before explicit execution | Unexpected final source |
| `cloud_fallback_invoked=true` before explicit execution | Unexpected cloud invocation |
| `model_calls increment before explicit execution` | Unexpected model call |

## 12. Commit and Governance Boundary

```text
This spec does NOT:
- Enable H5 execution
- Change route order
- Execute local committee
- Execute cloud fallback
- Change final_source
- Change behavior_changed
- Increment model_calls
- Replace final_patch
- Run benchmark
- Claim production_ready
- Claim public_claim_allowed
```

## Statements

```text
Spec only.
No production code changes.
No test changes.
No H5 execution enabled.
No actual route order change.
No local candidate finalization.
No cloud fallback finalization.
No cloud fallback execution.
No local committee invocation by benchmark runner.
No final delivery source change.
No final_patch replacement.
No model_calls increment.
No output mutation.
No real model calls.
No benchmark.
Not H5 ready.
Not local-first ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
