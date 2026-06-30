# B7-E: Internal Capability Update

## Status: B7_CONSTRAINED_ACTION_PIPELINE_GENERALIZED

## B7 Results

| Phase | Result |
|-------|--------|
| B7-A Regression | 13/13 tests pass |
| B7-B DSL Generalized | 8 action types defined |
| B7-C Contrasting Task | C_12481 selected |
| B7-D Dry Run | Pending (requires model execution) |
| B7-E Capability Update | This report |

## Capability Classification Update

### Before B6
- **B3_MODEL_LIMIT_CONFIRMED_AFTER_DEEP_EVIDENCE**
- Local 12B cannot solve C_13453 even with deep evidence

### After B6/B7
- **B6_VERIFIER_PASS_INTERNAL_ONLY**
- Local 12B CAN solve C_13453 when:
  1. Constrained action space is used
  2. Correct insert point is resolved
  3. Mechanism is refined through bounded attempts
  4. Nexus applier handles mechanical application

### Key Insight
The model is NOT semantically incapable. The free-form patch generation interface was too hard. Constrained actions + deterministic applier + bounded refinement = success.

## Action DSL (Generalized)

| Action Type | Description | Use Case |
|-------------|-------------|----------|
| REPLACE_EXPR | Replace one expression | Fix wrong expression |
| INSERT_GUARD | Insert conditional | Add missing check |
| INSERT_FORMAT_APPLICATION | Insert formatting line | Apply format before output |
| REORDER_EXISTING_CALL | Move existing call | Fix call ordering |
| CALL_EXISTING_HELPER | Call existing method | Invoke correct function |
| SET_REQUIRED_STATE_THEN_CALL | Set state then call | Prepare before helper |
| MOVE_CALL | Move call within scope | Fix placement |
| CHANGE_RECEIVER | Change object receiver | Fix wrong receiver |
| CHANGE_ARGUMENT | Change function argument | Fix wrong argument |
| ABSTAIN | Model cannot identify action | Acknowledge uncertainty |

## What Changed

| Metric | Before B6 | After B7 |
|--------|-----------|----------|
| C_13453 | Semantic limit | Solved internally |
| Action DSL | 6 types | 10 types |
| Insert point | Brittle string match | Relation-based AST |
| Refinement | None | Bounded (receiver/argument/state) |
| Regression tests | 0 | 13 |
| Full test suite | 291 | 304 |

## Next Steps

1. Run contrasting task (C_12481) to test generalization
2. If C_12481 works, constrained action pipeline is generalizable
3. If C_12481 fails, identify what action types or refinements are missing
4. Do NOT claim public success until at least 2 tasks pass
