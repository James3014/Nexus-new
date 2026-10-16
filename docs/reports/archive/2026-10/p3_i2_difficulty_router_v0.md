# P3-I2 Difficulty Router Minimal Policy Report

## Status: ✅ COMPLETE (uncommitted, code live)

## Files Changed

| File | Action |
|------|--------|
| `nexus/engine/capability_planner.py` | Replace P3-I1 block with P3-I2 difficulty-aware routing |
| `tests/engine/test_p3_difficulty_router.py` | +9 tests |

## System Behavior Change

- `NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW=1` + difficulty source → routes:
  - **easy** → `execution_topology=local_only`, `p3_shadow_route=false`
  - **medium/hard** → `execution_topology=cloud_with_local_assist`, `p3_shadow_route=true`
- Difficulty source priority: `route["difficulty"]` > `NEXUS_P3_DIFFICULTY` env var > heuristic from `task_desc`
- Heuristic: complex/hard/cross-module/multi-step → hard, simple/trivial/easy → easy, else → medium
- Flag off → existing topology preserved

## New Signal Fields

| Field | Type | Example |
|-------|------|---------|
| `task_difficulty` | str | `"easy"`, `"medium"`, `"hard"` |
| `route_policy_version` | str | `"p3_difficulty_router_v1"` |
| `route_selected_by` | str | `"p3_difficulty_router"` |
| `route_reason` | str | `"difficulty=easy"`, `"difficulty=hard_shadow_enabled"` |

## Test Results

```
P3-I2: 9 passed, 0 failed
P3-I1: 6 passed, 0 failed
Full suite: 1333 passed, 1 skipped, 0 failed (+9)
```

## Next

✅ P3-I2 complete → ready for **P3-I3: Stage 1 Local Diagnosis + Compact Prompt**
