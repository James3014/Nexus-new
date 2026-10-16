# P2-C Hash Mismatch in Claim Gate

## Status

`P2_C_HASH_MISMATCH_IN_CLAIM_GATE_PASS`

## Summary

Added `candidate_hash_matches_applied` check to `ClaimDeliveryGate.validate()` so hash mismatch makes `claim_gate_passed=false`, which flows to `claim_eligible=false` in receipt.py.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/claim_delivery_gate.py` | Modified — added hash mismatch check + op field read |
| `tests/unit/local_heal/test_claim_delivery_gate.py` | New — 5 tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/claim_delivery_gate.py
pytest tests/unit/local_heal/test_claim_delivery_gate.py -v -q
```

## Test Counts

- `test_claim_delivery_gate.py`: 5/5 passed

## What Was Added

### `validate()` (line ~28)

```python
candidate_hash_matches_applied = payload.get("candidate_hash_matches_applied", True)
if not candidate_hash_matches_applied:
    reasons.append("candidate_hash_mismatch")
```

### `validate_context_claim_delivery()` (line ~62)

```python
"candidate_hash_matches_applied": getattr(op, "selected_candidate_hash_matches_applied", True),
```

## Explicit Statements

- Producer side NOT wired yet (P2-D)
- No executor change
- No receipt.py change
- No candidate_isolation_gate.py change
- Backward compat preserved (default True when absent)
- Not P2 complete
- `claim_eligible` still not enforced until producer wired
