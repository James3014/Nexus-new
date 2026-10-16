# N31-B/C Closeout: planner_version + anti-tampering fail-closed

**Status**: PASS

## Summary

`LocalHealCapabilityAdapter.run()` 新增 3 層 fail-closed:
1. **N31-B**: `planner_version` 必須存在 (missing → blocked)
2. **N31-B**: `planner_version` 必須是 valid 版本 (fake → blocked)
3. **N31-C**: 6 個 required planner fields 必須存在 (incomplete → blocked)

## Changes

- `nexus/services/local_heal/capability_adapter.py`: 加 planner_version check + anti-tampering (60+ 行)
- `tests/integration/test_n31_fail_closed_local_heal_adapter.py`: 5 個 test

## Test Results

```
tests/integration/test_n31_fail_closed_local_heal_adapter.py: 5 passed
tests/test_lite_route_oracle.py: 19 passed (不退步)
tests/core/test_capability_signal_set.py: 6 passed (不退步)
```

## Forbidden claims
- 不可 production_ready / public_claim_allowed / Nexus 比較好
