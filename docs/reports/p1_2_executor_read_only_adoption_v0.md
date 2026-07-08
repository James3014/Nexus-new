# P1-2 Executor Read-Only Adoption

## Status

`P1_2_EXECUTOR_READ_ONLY_ADOPTION_PASS`

## Summary

Adopted `OutputUnderstandingResult` inside `local_model_executor.py` for the single_local_model output parsing path. The executor now reads the canonical understanding layer, injects understanding metadata into `raw_meta`, and adds fail-closed failure-surface mapping for malformed/refusal/empty outputs. No changes to apply logic, route logic, or claim logic.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Modified — added `understand_output()` call + metadata injection + fail-closed mapping |
| `tests/unit/local_heal/test_local_model_executor.py` | Modified — added 5 P1-2 tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/output_understanding.py nexus/services/local_heal/local_model_executor.py tests/unit/local_heal/test_output_understanding.py tests/unit/local_heal/test_local_model_executor.py
pytest tests/unit/local_heal/test_output_understanding.py -q
pytest tests/unit/local_heal/test_local_model_executor.py -k "output_understanding or canonical or malformed or refusal or search_replace" -q
pytest tests/unit/local_heal/test_receipt_v1_schema.py -q
```

## Test Counts

- `test_output_understanding.py`: 9/9 passed
- `test_local_model_executor.py` (P1-2 filtered): 6/6 passed
- `test_receipt_v1_schema.py`: 19/19 passed

## Executor Call Sites Updated

1. **single_local_model topology** (line ~2491): `understand_output()` called after `prov_resp.output_text` capture, before `_normalize_candidate_patch()`
2. **Top-level raw_meta injection** (line ~2516): Understanding metadata spread into `raw_meta` via `**_understanding_meta`

## What This Phase Does

1. **Reads** `OutputUnderstandingResult` from the canonical understanding layer
2. **Injects** understanding metadata (`output_understanding_format`, `output_understanding_success`, normalization steps, source format) into `raw_meta` at top level
3. **Adds fail-closed failure-surface mapping**: when `understand_output()` returns `success=False` and `candidate_hash == empty_hash`, the executor now sets `protocol_parse_failed=True` and `error_kind="OUTPUT_UNDERSTANDING:{failure_reason}"` — this changes the failure surface visible to downstream retry/classification logic

## What This Phase Does NOT Do

- No apply/hash truth work
- No route authority changes
- No committee authority changes
- No benchmark semantics changes
- No changes to `claim_eligible`, hidden verifier authority, or cloud/local route order

## Explicit Statements

- Executor reads `OutputUnderstandingResult`, injects metadata, and adds fail-closed failure-surface mapping
- Apply/hash truth is not implemented
- Route authority is unchanged
- Committee authority is unchanged
- Benchmark semantics are unchanged
- `production_ready=false`
- `public_claim_allowed=false`
