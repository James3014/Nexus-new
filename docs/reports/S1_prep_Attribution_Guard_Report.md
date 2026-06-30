# S1-prep StrategyTrace-only + Attribution Export Guard

## Verdict: Green ✅

8/8 tests pass. StrategyTrace is trace-only, no execution effect.

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
    "canonical_span_confidence": "",
    "target_symbol": "",
    "target_symbol_source": "",
    "target_symbol_confidence": "",
    "fallback_used": false,
    "fallback_reason": "",
    "semantic_retry_mode": "",
    "model_patch_reward": 0.0,
    "deterministic_fallback_reward": 0.0,
    "ast_fallback_reward": 0.0,
    "model_calls": 0,
    "claim_eligible": false,
    "public_claim_allowed": false
  }
}
```

## Task B: Attribution Export Guard

Updated `nexus/evidence/s2t_export_guard.py` with 3 rules:

| Condition | model_patch_reward | ast_fallback_reward | can_enter_chosen_pair |
|-----------|-------------------|--------------------|-----------------------|
| deterministic_fallback_used=true | 0.0 | 0.0 | false |
| canonical_span_source=ast_boundary, model_calls=0 | 0.0 | 1.0 | false |
| llm_replace_success=true | 1.0 | 0.0 | true (if claim_eligible) |

## Task C: Report Normalization

Corrected language:
- astropy-12907: true blocker = SEARCH_MISMATCH, NOT workspace provisioning
- P0.1c: Green, abort receipt remains watch item only
- astropy-13236: Nexus semantic recovery solved, NOT pure Qwen14B
- astropy-12907: AST-boundary fallback, NOT LLM patch if model_calls=0

## Task D: T1.9 Report Template

Created template with:
- Two-task result table
- Reward attribution per task
- Claim boundary header
- S2T export eligibility table
- No-public-claim statement

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/receipt.py` | +strategy_trace expanded fields |
| `nexus/evidence/s2t_export_guard.py` | +ast_boundary rule, +canonical_span_source, +model_calls |
| `tests/unit/test_s1_prep.py` | +8 tests |

## Confirmation

- prompt injection: NO
- routing effect: NO
- SurgicalPacker effect: NO
- patcher decision effect: NO
- canonical span decision effect: NO
- StrategyTrace-only: YES
