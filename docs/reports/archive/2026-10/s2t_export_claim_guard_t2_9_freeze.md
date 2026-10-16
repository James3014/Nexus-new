# S2T Export / Claim Guard — T2.9 Freeze

**Frozen**: 2026-06-18
**Baseline**: T2_9_20_TASK_RECOVERY_BASELINE

## Guard Rules

### G01: model_calls=0 guard
**Condition**: model_calls == 0
**Enforced**:
- model_patch_reward MUST be 0.0
- export_as_model_patch_success MUST be false
- export_as_public_claim MUST be false

### G02: deterministic fallback guard
**Condition**: deterministic_fallback_reward is present and non-empty
**Enforced**:
- export_as_model_patch_success MUST be false

### G03: ast_boundary + model_calls=0 guard
**Condition**: canonical_span_source == "ast_boundary" AND model_calls == 0
**Enforced**:
- export_as_model_patch_success MUST be false
- export_as_canonical_recovery_success MAY be true

### G04: locked_search replay guard
**Condition**: canonical_span_source == "locked_search" AND model_calls == 0
**Enforced**:
- export_as_model_patch_success MUST be false
- model_patch_reward MUST be 0.0

### G05: repro / harness failure guard
**Condition**: failure_class in [repro_failure, repro_env_noise, repro_script_fix, repro_script_wrong_expected_behavior_fix]
**Enforced**:
- count_as_model_failure MUST be false
- count_as_patcher_failure MUST be false
- export_as_internal_infra_failure MUST be true

### G06: dependency / workspace failure guard
**Condition**: failure_class in [dependency_missing, workspace, workspace_config_fix, parser_dependency_missing_fix, astropy_html_dependency_fix, sympy_python39_workspace_fix, django_workspace_validation]
**Enforced**:
- count_as_model_failure MUST be false
- count_as_patcher_failure MUST be false
- export_as_internal_infra_failure MUST be true

### G07: internal baseline guard
**Condition**: baseline_type == "internal_recovery_baseline"
**Enforced**:
- claim_eligible MUST be false
- public_claim_allowed MUST be false
- export_as_public_claim MUST be false

### G08: model patch success candidate guard
**Condition**: export_as_model_patch_success == true (internal only)
**Required ALL**:
- model_calls > 0
- llm_replace_success == true
- deterministic_fallback_used == false
- verification_result == "PASS"
**Note**: public_claim_allowed still false unless separate public-claim process approves

## Test Results

### G01 Test: model_calls=0
```
Input: model_calls=0, model_patch_reward=0.0
Expected: export_as_model_patch_success=false
Result: PASS
```

### G02 Test: deterministic fallback
```
Input: deterministic_fallback_reward="AST_SYMBOL_FIX"
Expected: export_as_model_patch_success=false
Result: PASS
```

### G03 Test: ast_boundary + model_calls=0
```
Input: canonical_span_source="ast_boundary", model_calls=0
Expected: export_as_model_patch_success=false, export_as_canonical_recovery_success=true
Result: PASS
```

### G04 Test: locked_search replay
```
Input: canonical_span_source="locked_search", model_calls=0
Expected: export_as_model_patch_success=false, model_patch_reward=0.0
Result: PASS
```

### G05 Test: repro failure
```
Input: failure_class="repro_env_noise"
Expected: count_as_model_failure=false, count_as_patcher_failure=false, export_as_internal_infra_failure=true
Result: PASS
```

### G06 Test: dependency failure
```
Input: failure_class="dependency_missing"
Expected: count_as_model_failure=false, count_as_patcher_failure=false, export_as_internal_infra_failure=true
Result: PASS
```

### G07 Test: internal baseline
```
Input: baseline_type="internal_recovery_baseline"
Expected: claim_eligible=false, public_claim_allowed=false, export_as_public_claim=false
Result: PASS
```

### G08 Test: model patch candidate
```
Input: model_calls=1, llm_replace_success=true, deterministic_fallback_used=false, verification_result="PASS"
Expected: export_as_model_patch_success=true (internal), public_claim_allowed=false
Result: PASS
```

## Verdict

**EXPORT/CLAIM GUARD v1.0 FROZEN** — All 8 guard rules pass. No public claim leakage possible from internal baseline.
