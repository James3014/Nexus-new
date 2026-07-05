# B1 Downstream Provider Wiring Report

**status**: B1_DOWNSTREAM_PROVIDER_WIRING_PASS
**date**: 2026-07-06

## Files Changed

| File | Change |
|---|---|
| `nexus/services/local_heal/heterogeneous_candidate_provider.py` | Removed hardcoded model defaults; `primary_model` required; fail-closed on missing |
| `nexus/services/local_heal/judge_selector.py` | Removed hardcoded judge model default; `judge_model` required; fail-closed on missing |
| `tests/unit/local_heal/test_heterogeneous_candidate_provider.py` | Updated to pass models explicitly; added fail-closed test |
| `tests/unit/local_heal/test_judge_selector.py` | Updated to pass models explicitly; added fail-closed test |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/heterogeneous_candidate_provider.py nexus/services/local_heal/judge_selector.py
uv run pytest tests/unit/local_heal -k "heterogeneous_candidate_provider or judge_selector" -q
```

## Test Results

```
10 passed in 0.58s
```

## Statements

- **No new route authority**: CapabilityPlanner / HybridRouteDecision remains the only route authority.
- **No new topology**: No execution_topology added or changed.
- **Planner remains route truth**: Models must be provided by planner/signal_snapshot, not hardcoded.
- **Committee solved not claimed**: This is downstream wiring only.
- **production_ready=false**
- **public_claim_allowed=false**
