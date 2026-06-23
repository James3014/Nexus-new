# H5-19 Local Evidence Ingestion Shadow Attach Report

**日期**: 2026-06-22
**狀態**: `H5_19_LOCAL_EVIDENCE_INGESTION_SHADOW_ATTACH_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +`_build_h5_local_evidence_ingestion_shadow()` pure helper, +shadow attachment before preflight, +readiness preflight reads shadow, +5 new summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +7 H5-19 tests (93 total for H5 selector) |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 93 passed, 346 deselected
```

## Shadow Schema

```json
{
  "schema": "nexus.hybrid_h5_local_evidence_ingestion_shadow.v1",
  "evaluated": true,
  "external_evidence_present": false,
  "external_validation_schema": "",
  "accepted_for_h5_readiness_shadow": false,
  "validation_status": "",
  "validation_reasons": [],
  "local_evidence_can_feed_readiness": false,
  "local_evidence_source": "external_prevalidated",
  "local_path_ready_shadow_from_external_evidence": false,
  "blocked_reason": "",
  "public_claim_allowed": false,
  "production_ready": false
}
```

## Readiness Preflight Interaction

When `local_path_ready_shadow_from_external_evidence=true`:
- `local_external_evidence_ready_shadow=true` in readiness preflight
- `execution_ready` remains `false`
- Other missing gates still block

## Summary Counters

```text
h5_local_evidence_ingestion_shadow_count
h5_local_evidence_external_present_count
h5_local_evidence_accepted_count
h5_local_evidence_blocked_count
h5_local_external_evidence_ready_shadow_count
```

## Normal-Row Invariant

All normal finalized rows:
- `external_evidence_present=false`
- `execution_ready=false`
- `final_source="none"`
- `behavior_changed=false`

## External Accepted Evidence Invariant

When external evidence is accepted:
- `local_path_ready_shadow_from_external_evidence=true`
- `execution_ready=false` (other gates still block)
- `final_source="none"`
- `behavior_changed=false`

## Statements

```text
Local evidence ingestion shadow attach only.
No H5 execution enabled.
No actual route order change.
No local committee invocation from benchmark runner.
No local candidate finalization.
No cloud fallback finalization.
No cloud fallback execution.
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
