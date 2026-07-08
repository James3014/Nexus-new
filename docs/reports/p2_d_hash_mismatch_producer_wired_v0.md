# P2-D Hash Mismatch Producer Wired

## Status

`P2_D_HASH_MISMATCH_PRODUCER_WIRED_PASS`

## Summary

Wired the producer side so `candidate_hash_matches_applied` flows from executor → raw_meta → orchestrator → claim_delivery_gate. Hash mismatch now causes `claim_eligible=false`.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Modified — added `candidate_hash_matches_applied` to both raw_meta dicts |
| `nexus/services/local_heal/claim_delivery_gate.py` | Modified — added optional `candidate_hash_matches_applied` param + fallback chain |
| `nexus/services/local_heal/orchestrator.py` | Modified — derives hash_match from ctx.op/route_context and passes to gate |
| `tests/unit/local_heal/test_claim_delivery_gate.py` | Modified — added 2 P2-D tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/local_model_executor.py nexus/services/local_heal/claim_delivery_gate.py nexus/services/local_heal/orchestrator.py
pytest tests/unit/local_heal/test_claim_delivery_gate.py -v -q
```

## Test Counts

- `test_claim_delivery_gate.py`: 7/7 passed

## Where `candidate_hash_matches_applied` Was Added

| Location | Line | Value Source |
|----------|------|--------------|
| Committee raw_meta | ~1273 | `hash_match` |
| Pipeline raw_meta | ~1581 | `hash_match` |
| `validate_context_claim_delivery()` | ~60 | param > op > route_context > True |
| Orchestrator call | ~954 | derives from ctx.op/route_context |

## Bridge: executor → op → claim_gate

1. Executor computes `hash_match` in both committee and pipeline paths
2. Executor stores `candidate_hash_matches_applied` in `raw_model_metadata`
3. Orchestrator derives value from `ctx.op.selected_candidate_hash_matches_applied` or `ctx.op.route_context.candidate_hash_matches_applied`
4. Orchestrator passes to `validate_context_claim_delivery(ctx, candidate_hash_matches_applied=_hash_match)`
5. Gate validates and adds `candidate_hash_mismatch` reason if False

## Explicit Statements

- `hash_mismatch → claim_eligible=false` is now LIVE behavior
- Backward compat preserved (default True when no data)
- No executor behavior change beyond raw_meta addition
- No receipt.py change
- No candidate_isolation_gate.py change
