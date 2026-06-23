# H5-18 Local Committee Evidence Ingestion Contract Report

**日期**: 2026-06-22
**狀態**: `H5_18_LOCAL_COMMITTEE_EVIDENCE_INGESTION_CONTRACT_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/h5_local_committee_e2e_smoke.py` | +`validate_h5_local_committee_evidence_bundle()` pure validator, +ingestion validation in all return paths, +helper functions |
| `tests/benchmark/test_h5_local_committee_e2e_smoke.py` | +10 H5-18 tests (38 total) |

## Commands Run

```text
python3 -m py_compile scripts/bench/h5_local_committee_e2e_smoke.py tests/benchmark/test_h5_local_committee_e2e_smoke.py
→ OK

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -v
→ 38 passed
```

## Validation Schema

```json
{
  "schema": "nexus.h5_local_committee_evidence_ingestion_validation.v1",
  "validated": true,
  "accepted_for_h5_readiness_shadow": false,
  "validation_status": "accepted | rejected",
  "validation_reasons": [],
  "source_bundle_schema": "",
  "bundle_status": "",
  "can_feed_h5_readiness_shadow": false,
  "safety_invariants_ok": false,
  "governance_ok": false,
  "receipt_ok": false,
  "readiness_bridge_ok": false,
  "candidate_identity_ready": false,
  "candidate_application_ready": false,
  "candidate_hash_ready": false,
  "candidate_patch_metadata_ready": false,
  "local_solve_ready": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

## Validation Rules

| Rule | Rejection Reason |
|------|-----------------|
| Missing bundle | `missing_bundle` |
| Wrong schema | `invalid_bundle_schema` |
| bundle_status != "pass" | `bundle_not_pass` |
| can_feed_h5_readiness_shadow != true | `cannot_feed_h5_readiness_shadow` |
| Safety invariant violated | `safety_invariant_violation` |
| Governance boundary violated | `governance_boundary_violation` |
| Receipt not H5 compatible | `receipt_not_h5_compatible` |
| Readiness bridge not ready | `readiness_bridge_not_ready` |

## Accepted Criteria

`accepted_for_h5_readiness_shadow=true` only when ALL:
- bundle_status="pass"
- can_feed_h5_readiness_shadow=true
- safety_invariants_ok=true
- governance_ok=true
- receipt_ok=true
- readiness_bridge_ok=true
- No validation_reasons

## Statements

```text
Local committee evidence ingestion contract only.
No H5 execution enabled.
No actual route order change.
No local candidate finalization.
No cloud fallback finalization.
No cloud fallback execution.
No benchmark runner local committee invocation.
No capability_ab_runner.py changes.
No final delivery source change.
No final_patch replacement.
No model_calls increment.
No output mutation.
No real cloud model calls.
No full benchmark.
Not H5 ready.
Not local-first ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
