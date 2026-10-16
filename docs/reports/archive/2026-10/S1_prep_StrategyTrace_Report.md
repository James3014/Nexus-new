# S1-prep StrategyTrace-only + Report/Attribution Hygiene

## Verdict: Green ✅

7/7 tests pass. StrategyTrace is trace-only, no execution effect.

## Task A: StrategyTrace-only Receipt Attachment

Added `strategy_trace` block to receipt with trace_only=true:

```json
{
  "strategy_trace": {
    "strategy_trace_only": true,
    "strategy_id": "",
    "strategy_schema": "",
    "task_goal": "",
    "bug_hypothesis": "",
    "repair_strategy": "",
    "target_symbols": [],
    "allowed_paths": [],
    "forbidden_paths": [],
    "invariants": [],
    "abort_conditions": [],
    "canonical_span_source": "",
    "target_symbol": "",
    "target_symbol_confidence": "",
    "fallback_used": false,
    "fallback_reason": "",
    "semantic_retry_mode": "",
    "model_patch_reward": 0.0,
    "deterministic_fallback_reward": 0.0
  }
}
```

## Task B: S2T Export Guard

New module `nexus/evidence/s2t_export_guard.py`:

| Condition | model_patch_reward | can_enter_chosen_pair |
|-----------|-------------------|----------------------|
| deterministic_fallback_used=true | 0.0 | false |
| llm_replace_success=true | 1.0 | true (if claim_eligible) |
| claim_eligible=false | - | false |

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/receipt.py` | +strategy_trace block |
| `nexus/evidence/s2t_export_guard.py` | New: S2T export guard |
| `tests/unit/test_s1_prep.py` | +7 tests |

## Confirmation

- prompt injection: NO
- routing effect: NO
- patcher decision effect: NO
- StrategyTrace-only: YES
