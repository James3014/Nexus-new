# P2-3 Anchor Fields in CandidateIsolationReceipt

## Status

`P2_3_ANCHOR_FIELDS_IN_RECEIPT_PASS`

## Summary

Added anchor fields to `CandidateIsolationReceipt`, populated at both committee and pipeline creation sites, and added `missing_candidate_target_file` validator check.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/candidate_isolation_gate.py` | Modified — added 3 anchor fields + validator check |
| `nexus/services/local_heal/local_model_executor.py` | Modified — populated anchor fields at both creation sites |
| `tests/unit/local_heal/test_candidate_isolation_gate.py` | Modified — added 5 P2-3 tests, updated existing test |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/candidate_isolation_gate.py nexus/services/local_heal/local_model_executor.py
pytest tests/unit/local_heal/test_candidate_isolation_gate.py -v -q
```

## Test Counts

- `test_candidate_isolation_gate.py`: 10/10 passed

## Fields Added to CandidateIsolationReceipt

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `candidate_target_file` | `str` | `""` | Target file path |
| `candidate_target_symbol` | `str` | `""` | Target symbol name |
| `candidate_old_block_hash` | `str` | `""` | SHA-256 of locked_search (not available at creation sites) |

## Populated At

| Path | Line | Fields Set |
|------|------|------------|
| Committee path | ~1167 | `candidate_target_file`, `candidate_target_symbol` |
| Pipeline path | ~1556 | `candidate_target_file`, `candidate_target_symbol` |

## Validator Addition

In `validate_candidate_isolation_receipt()`, after `missing_selected_candidate_hash` check:
```python
if receipt.selected_candidate_hash.strip() and not receipt.candidate_target_file.strip():
    blockers.append("missing_candidate_target_file")
```

## Explicit Statements

- `missing_candidate_target_file` is the only new blocker
- `old_block_hash` defaulted to empty (not available at creation sites)
- No `claim_eligible` change
- Not P2 complete
- `public_claim_allowed=false`
- `production_ready=false`
