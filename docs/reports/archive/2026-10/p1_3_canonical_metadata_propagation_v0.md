# P1-3 Canonical Metadata Propagation

## Status

`P1_3_CANONICAL_METADATA_PROPAGATION_PASS`

## Summary

Propagated canonical output-understanding metadata from executor metadata into downstream receipt/row surfaces. Additive only — no behavior gates changed.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/receipt.py` | Modified — added `_extract_output_understanding_metadata()` + propagation into telemetry |
| `tests/unit/local_heal/test_local_heal_receipt.py` | New — 4 receipt propagation tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/receipt.py nexus/services/local_heal/local_model_executor.py tests/unit/local_heal/test_local_heal_receipt.py tests/unit/local_heal/test_receipt_v1_schema.py
pytest tests/unit/local_heal/test_local_heal_receipt.py -q
pytest tests/unit/local_heal/test_receipt_v1_schema.py -q
pytest tests/unit/local_heal/test_local_model_executor.py -k "output_understanding or unified_diff or malformed or refusal or search_replace" -q
```

Note: The last command selects 9 tests; 2 are pre-existing failures (`test_committee_unified_diff_conversion_success_allows_isolated_apply`, `test_committee_unified_diff_conversion_failure_records_specific_reason`) caused by missing `nexus.services.local_heal.pipeline.HealPipeline` — unrelated to P1-3. The remaining 7 pass.

## Test Counts

- `test_local_heal_receipt.py`: 4/4 passed
- `test_receipt_v1_schema.py`: 19/19 passed
- `test_local_model_executor.py` (P1-2 filtered): 7/7 passed, 2 pre-existing failures excluded (see note above)

## Propagated Fields

| Field | Source | Description |
|-------|--------|-------------|
| `output_understanding_format` | `raw_model_metadata` | Detected format enum value |
| `output_understanding_success` | `raw_model_metadata` | Whether understanding succeeded |
| `output_understanding_normalization_steps` | `raw_model_metadata` | Steps applied during normalization |
| `output_understanding_source_format` | `raw_model_metadata` | Source format before normalization |

## Propagation Mechanism

1. `_extract_output_understanding_metadata(ctx)` reads from `ctx.raw_model_metadata`
2. Returns only fields that are present (additive — empty dict if absent)
3. Spread into receipt `telemetries` dict via `**` unpacking
4. No downstream gates depend on these fields in this phase

## Explicit Statements

- Propagation is additive only — no behavior gates changed
- Apply/hash truth is not implemented
- Route authority is unchanged
- Claim logic is unchanged
- Benchmark semantics are unchanged
- `production_ready=false`
- `public_claim_allowed=false`
