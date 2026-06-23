# H5-26 Controlled Execution Design Audit and Rollback Plan

**日期**: 2026-06-22
**狀態**: `H5_26_CONTROLLED_EXECUTION_DESIGN_AUDIT_ROLLBACK_PLAN_PASS`
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## 1. Current H5 State Summary

```text
H5-0 ~ H5-25 completed
trace-only scaffold complete
local/cloud evidence shadow attached to H5 readiness
execution flag contract fail-closed
H5 execution NOT enabled
public_claim_allowed=false
production_ready=false
execution_allowed=false (always, even with flag=1)
fail_closed=true (always)
```

Key invariant: `NEXUS_H5_ENABLE_CONTROLLED_EXECUTION=1` sets `execution_flag_enabled=true` but `execution_allowed` remains `false` because promotion blockers are not satisfied.

---

## 2. Candidate Execution Paths

| Path | Complexity | Side-effect Risk | model_calls Risk | Output Risk | Rollback | Testability | Status |
|------|-----------|------------------|------------------|-------------|----------|-------------|--------|
| **A. Local candidate finalization from external evidence** | Low | Low | None | Bounded | Simple | High | **First candidate** |
| B. Cloud fallback from external evidence | Medium | Medium | Yes | Yes | Complex | Medium | Blocked |
| C. Direct benchmark runner local committee | High | High | Yes | Yes | Complex | Low | Blocked |
| D. Direct benchmark runner cloud invocation | High | High | Yes | Yes | Complex | Low | Blocked |
| E. Local-only execution | High | High | Yes | Yes | Complex | Low | Blocked |

### Recommendation

**Path A (local candidate finalization) is the first controlled execution candidate.**

Reasons:
- Local evidence path has candidate identity/hash/apply metadata already validated
- Can be kept offline and bounded
- Avoids real cloud calls and model_calls accounting risk
- Rollback is simple: revert `final_source` to "none"
- Cloud fallback (Path B) should remain blocked until separate real cloud smoke validation exists

---

## 3. Minimum Safe Execution Boundary

```text
The first allowed execution boundary must satisfy ALL:

1. No local committee invocation from benchmark runner
   → local evidence comes from external prevalidated shadow, not benchmark runner

2. No cloud invocation from benchmark runner
   → cloud evidence shadow only, no real cloud call

3. No real model call
   → local candidate patch comes from pre-validated external evidence

4. No output mutation unless explicitly enabled by separate finalization flag
   → NEXUS_H5_ALLOW_LOCAL_FINALIZATION must be a separate flag

5. final_source may only change from "none" to "local_candidate_shadow_promoted"
   → not in H5-26; requires H5-27+

6. final_patch replacement must remain blocked until hash verified and rollback receipt exists
   → requires U3 hash verification AND rollback receipt path

7. All behavior changes gated behind second flag
   → NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE (separate from NEXUS_H5_ENABLE_CONTROLLED_EXECUTION)
```

---

## 4. Required Future Flags

| Flag | Purpose | Required For |
|------|---------|-------------|
| `NEXUS_H5_ENABLE_CONTROLLED_EXECUTION` | Master execution gate | All execution |
| `NEXUS_H5_ALLOW_LOCAL_FINALIZATION` | Allow local candidate to become final | local_candidate finalization |
| `NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE` | Allow final_source to change from "none" | final_source mutation |
| `NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT` | Allow final_patch to be replaced | output mutation |

All four flags must be "1" for actual final output mutation to occur.

---

## 5. Rollback Conditions

Must immediately force `execution_allowed=false`:

| Condition | Reason |
|-----------|--------|
| Local evidence missing | No source for local candidate |
| Local evidence validation rejected | Evidence not H5-compatible |
| Selected candidate hash mismatch | Hash integrity violated |
| Selected candidate not applied | Apply failed |
| Selected candidate patch missing | No patch to apply |
| Readiness closure not blocked as expected | Unexpected state |
| Quality non-regression missing | Gate not passed |
| Full benchmark missing | Gate not passed |
| Governance approval missing | Gate not passed |
| Unexpected final_source change | Side effect detected |
| Unexpected behavior_changed=true | Side effect detected |
| Unexpected model_calls increment | Side effect detected |
| Unexpected output mutation | Side effect detected |
| Cloud evidence required but missing | Cloud path incomplete |
| Cloud provider invocation observed unexpectedly | Unauthorized execution |

---

## 6. Promotion Blocker Matrix

| Blocker | Current Status | Required Proof | Owner/Test | Pass Condition |
|---------|---------------|----------------|------------|----------------|
| Quality non-regression | Missing | Real test suite passes | H5-28+ | All tests green |
| Full benchmark | Missing | Benchmark completes | H5-29+ | No regression |
| Governance approval | Missing | Owner sign-off | Manual | Approved |
| Local evidence acceptance | H5-18 validated | Smoke passes | H5-14~H5-19 | accepted_for_h5_readiness_shadow=true |
| Cloud evidence acceptance | H5-22 validated | Smoke passes | H5-20~H5-22 | accepted_for_h5_readiness_shadow=true |
| Rollback receipt | Missing | Rollback path proven | H5-27+ | Rollback receipt exists |
| final_source safety | Blocked | final_source="none" verified | H5-25 | No unexpected change |
| final_patch hash safety | U3-3B proven | Hash verified | U3-3B | selected_candidate_apply_hash_match=true |
| model_calls safety | Blocked | No unexpected increment | H5-25 | model_calls_incremented=false |
| Public/prod claim gate | Blocked | Claims stay false | H5-25 | public_claim_allowed=false |

---

## 7. Required Next Implementation Phase

**H5-27: Local Candidate Promotion Dry-Run Receipt**

H5-27 should still not mutate final output. It should only build a pure promotion receipt from:
- `h5_local_evidence_ingestion_shadow`
- `h5_overall_readiness_closure`
- `h5_execution_flag_contract`

The promotion receipt records what WOULD change if promotion were allowed, but does not execute any change.

## 8. H5-27 Success Criteria

H5-27 may only produce:
- `would_promote_local_candidate=true` (when all local evidence accepted)
- `promotion_allowed=false` (always in H5-27)
- `final_source_change_allowed=false` (always)
- `final_patch_replacement_allowed=false` (always)
- `output_mutation_allowed=false` (always)
- `rollback_required=false` (always)

---

## 9. Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 114 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
→ 38 passed

pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 18 passed
```

---

## Statements

```text
Design audit only.
No H5 execution enabled.
No execution implementation.
No actual route order change.
No local committee invocation from benchmark runner.
No cloud fallback execution from benchmark runner.
No local candidate finalization.
No cloud fallback finalization.
No final delivery source change.
No final_patch replacement.
No model_calls increment.
No output mutation.
No full benchmark.
Not H5 ready.
Not local-first ready.
Not cloud fallback ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
