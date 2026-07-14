# Recovery Rule Registry v1

## T2.1 Known Rules

| rule_id | rule_type | model_patch_reward | deterministic_fallback_reward | ast_fallback_reward | export_as_model_patch_success | export_as_canonical_recovery_success |
|---------|-----------|-------------------|-------------------------------|--------------------|------------------------------|--------------------------------------|
| AST_SYMBOL_FIX | canonical_span_recovery | 0.0 | 0.0 | 1.0 | false | true |
| REMOVE_BLOCK | deterministic_fallback | 0.0 | 1.0 | 0.0 | false | false |
| AST_BOUNDARY_EXTRACT | canonical_span_recovery | 0.0 | 0.0 | 1.0 | false | true |
| locked_search_reuse | locked_search_reuse | 0.0 | 0.0 | 0.0 | false | false |
| unified_diff_reuse | unified_diff_reuse | 0.0 | 0.0 | 0.0 | false | false |

## Hard Rules

- model_calls=0 → model_patch_reward=0.0
- deterministic fallback → export_as_model_patch_success=false
- ast_boundary + model_calls=0 → export_as_model_patch_success=false
- focused_internal_regression → public_claim_allowed=false

## Files

- `nexus/evidence/recovery_rule_registry.py`
- `tests/unit/test_recovery_registry.py`
