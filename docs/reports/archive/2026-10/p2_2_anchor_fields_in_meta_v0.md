# P2-2 Anchor Fields in Meta

## Status

`P2_2_ANCHOR_FIELDS_IN_META_PASS`

## Summary

Propagated anchor fields (`target_file`, `target_symbol`, `old_block_hash`) from canonical candidate through executor `_understanding_meta` to receipt extraction. Additive only.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Modified — added 3 anchor keys to `_understanding_meta` |
| `nexus/services/local_heal/receipt.py` | Modified — added 3 anchor keys to extraction loop |
| `tests/unit/local_heal/test_output_understanding.py` | Modified — added 1 meta simulation test |
| `tests/unit/local_heal/test_local_heal_receipt.py` | Modified — added 2 receipt extraction tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/local_model_executor.py nexus/services/local_heal/receipt.py
pytest tests/unit/local_heal/test_output_understanding.py -v -q
pytest tests/unit/local_heal/test_local_heal_receipt.py -v -q
```

## Test Counts

- `test_output_understanding.py`: 15/15 passed
- `test_local_heal_receipt.py`: 6/6 passed

## Fields Passed Through

| Field | Executor Line | Receipt Line |
|-------|---------------|--------------|
| `output_understanding_candidate_target_file` | ~2537 | ~51 |
| `output_understanding_candidate_target_symbol` | ~2538 | ~52 |
| `output_understanding_candidate_old_block_hash` | ~2539 | ~53 |

## Explicit Statements

- No receipt schema change
- No CandidateIsolationReceipt change
- No blocker change
- No `claim_eligible` change
- Not P2 complete
- `public_claim_allowed=false`
- `production_ready=false`
