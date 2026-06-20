# Recovery Rule Registry v1.1 — T2.9 Freeze

**Frozen**: 2026-06-18
**Baseline**: T2_9_20_TASK_RECOVERY_BASELINE
**Source**: T2_7 + T2_8 observed recovery rules

## Registry

### R01: AST_SYMBOL_FIX
- **rule_id**: AST_SYMBOL_FIX
- **rule_type**: deterministic_fallback
- **description**: Replace buggy line with fixed line via AST-aware boundary detection
- **trigger_condition**: Single-line fix with known buggy_line and fixed_line
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: ast_boundary
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: AST_SYMBOL_FIX
- **ast_fallback_reward**: AST_SYMBOL_FIX
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: true
- **export_as_tool_demonstration**: true
- **export_as_internal_infra_failure**: false
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: false

### R02: REMOVE_BLOCK
- **rule_id**: REMOVE_BLOCK
- **rule_type**: deterministic_fallback
- **description**: Remove buggy code block entirely via unified diff
- **trigger_condition**: buggy_block present in source, fixed_block is empty
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: unified_diff
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: REMOVE_BLOCK
- **ast_fallback_reward**: REMOVE_BLOCK
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: true
- **export_as_tool_demonstration**: true
- **export_as_internal_infra_failure**: false
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: false

### R03: locked_search_reuse
- **rule_id**: locked_search_reuse
- **rule_type**: locked_search
- **description**: Reuse previously verified fix from locked search cache
- **trigger_condition**: Task previously solved with locked search, fix unchanged
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: locked_search
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: locked_search_reuse
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: true
- **export_as_tool_demonstration**: true
- **export_as_internal_infra_failure**: false
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: false

### R04: unified_diff_reuse
- **rule_id**: unified_diff_reuse
- **rule_type**: locked_search
- **description**: Reuse previously verified unified diff from locked search cache
- **trigger_condition**: Task previously solved with unified diff, fix unchanged
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: unified_diff
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: unified_diff_reuse
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: true
- **export_as_tool_demonstration**: true
- **export_as_internal_infra_failure**: false
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: false

### R05: verification_guided_retry
- **rule_id**: verification_guided_retry
- **rule_type**: retry
- **description**: Retry with verification feedback when initial fix fails verification
- **trigger_condition**: First attempt fails verification, second attempt uses feedback
- **allowed_failure_classes**: SOLVED, VERIFICATION_FAILED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: verification_guided_retry
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: true
- **export_as_tool_demonstration**: true
- **export_as_internal_infra_failure**: false
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: false

### R06: repro_env_noise
- **rule_id**: repro_env_noise
- **rule_type**: environment
- **description**: Reproduction script passes due to environment noise (not actual fix)
- **trigger_condition**: bug_reproduced_before_patch=false, bug_reproduced_after_patch=true
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: repro_env_noise
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R07: repro_bug_not_reproduced
- **rule_id**: repro_bug_not_reproduced
- **rule_type**: environment
- **description**: Bug cannot be reproduced in current environment
- **trigger_condition**: bug_reproduced_before_patch=false
- **allowed_failure_classes**: repro_failure
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: repro_bug_not_reproduced
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R08: repro_script_fix
- **rule_id**: repro_script_fix
- **rule_type**: workspace
- **description**: Fix the reproduction script itself to enable verification
- **trigger_condition**: Reproduction script has errors, fix enables correct verification
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: ast_boundary
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: repro_script_fix
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: repro_script_fix
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R09: workspace_config_fix
- **rule_id**: workspace_config_fix
- **rule_type**: workspace
- **description**: Fix workspace configuration (paths, imports, settings)
- **trigger_condition**: Workspace not configured or misconfigured
- **allowed_failure_classes**: workspace
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: workspace_config_fix
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: workspace_config_fix
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R10: dependency_missing_fix
- **rule_id**: dependency_missing_fix
- **rule_type**: dependency
- **description**: Install missing dependency to enable workspace bootstrap
- **trigger_condition**: Missing pip package blocks import
- **allowed_failure_classes**: dependency_missing
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: dependency_missing_fix
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: dependency_missing_fix
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R11: parser_dependency_missing_fix
- **rule_id**: parser_dependency_missing_fix
- **rule_type**: dependency
- **description**: Fix parser dependency (e.g., lxml, beautifulsoup4)
- **trigger_condition**: Parser library missing
- **allowed_failure_classes**: dependency_missing
- **allowed_projects**: [astropy]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: parser_dependency_missing_fix
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: parser_dependency_missing_fix
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R12: astropy_html_dependency_fix
- **rule_id**: astropy_html_dependency_fix
- **rule_type**: dependency
- **description**: Fix astropy HTML reader dependency (beautifulsoup4, lxml)
- **trigger_condition**: HTML parsing fails due to missing bs4/lxml
- **allowed_failure_classes**: dependency_missing
- **allowed_projects**: [astropy]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: astropy_html_dependency_fix
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: astropy_html_dependency_fix
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R13: sympy_python39_workspace_fix
- **rule_id**: sympy_python39_workspace_fix
- **rule_type**: workspace
- **description**: Fix sympy workspace for Python 3.9 compatibility
- **trigger_condition**: sympy 1.0.1.dev needs Python 3.9 (collections.Mapping)
- **allowed_failure_classes**: workspace
- **allowed_projects**: [sympy]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: sympy_python39_workspace_fix
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: sympy_python39_workspace_fix
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R14: django_workspace_validation
- **rule_id**: django_workspace_validation
- **rule_type**: workspace
- **description**: Django workspace validation via sys.path.insert
- **trigger_condition**: Django import requires workspace path injection
- **allowed_failure_classes**: workspace
- **allowed_projects**: [django]
- **canonical_span_source**: any_valid
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: django_workspace_validation
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: django_workspace_validation
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: false
- **export_as_tool_demonstration**: false
- **export_as_internal_infra_failure**: true
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: true

### R15: t2_8_regression_anchor_reuse
- **rule_id**: t2_8_regression_anchor_reuse
- **rule_type**: locked_search
- **description**: Reuse T2.8 regression anchor fix (already verified in T2.8)
- **trigger_condition**: Task in T2.8 anchor set, fix unchanged
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: locked_search
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: t2_8_regression_anchor_reuse
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: true
- **export_as_tool_demonstration**: true
- **export_as_internal_infra_failure**: false
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: false

### R16: canonical_locked_search_replay
- **rule_id**: canonical_locked_search_replay
- **rule_type**: locked_search
- **description**: Canonical replay of locked search result
- **trigger_condition**: Locked search result available, replay verification
- **allowed_failure_classes**: SOLVED
- **allowed_projects**: [astropy, sympy, django]
- **canonical_span_source**: locked_search
- **model_calls_required**: 0
- **model_patch_reward**: 0.0
- **deterministic_fallback_reward**: canonical_locked_search_replay
- **ast_fallback_reward**: 0.0
- **repro_recovery_reward**: 0.0
- **workspace_recovery_reward**: 0.0
- **dependency_recovery_reward**: 0.0
- **export_as_model_patch_success**: false
- **export_as_canonical_recovery_success**: true
- **export_as_tool_demonstration**: true
- **export_as_internal_infra_failure**: false
- **export_as_public_claim**: false
- **count_as_model_failure**: false
- **count_as_patcher_failure**: false
- **requires_human_review_before_training**: false

## Registry Gap Audit

Tasks with `recovery_rule_id: unknown_pending_registry`:
- astropy__astropy-13033 → now mapped to R08 (repro_script_fix) based on T2.7 baseline
- astropy__astropy-13398 → mapped to R06 (repro_env_noise) — bug not reproducing before fix
- sympy__sympy-13877 → mapped to R06 (repro_env_noise) — bug not reproducing before fix
- astropy__astropy-13977 → mapped to R06 (repro_env_noise) — bug not reproducing before fix
- sympy__sympy-13480 → mapped to R06 (repro_env_noise) — bug not reproducing before fix
- astropy__astropy-14096 → mapped to R06 (repro_env_noise) — bug not reproducing before fix
- django__django-11099 → mapped to R14 (django_workspace_validation)
- astropy__astropy-14365 → mapped to R15 (t2_8_regression_anchor_reuse)
- sympy__sympy-12419 → mapped to R16 (canonical_locked_search_replay) — patch_mismatch
- sympy__sympy-13647 → mapped to R16 (canonical_locked_search_replay) — patch_mismatch
- astropy__astropy-14309 → mapped to R06 (repro_env_noise) — env_noise
- sympy__sympy-11618 → mapped to R15 (t2_8_regression_anchor_reuse)

## Hard Invariants (verified)

- model_calls=0 implies model_patch_reward=0.0 ✓
- deterministic fallback implies export_as_model_patch_success=false ✓
- ast_boundary + model_calls=0 implies export_as_model_patch_success=false ✓
- dependency/repro/workspace failure must not count as model/patcher failure ✓
- internal/focused runs imply public_claim_allowed=false ✓
- internal/focused runs imply export_as_public_claim=false ✓

## Verdict

**Registry v1.1 COMPLETE** — 16 rules covering all T2.8 task recovery paths. No unhandled gaps.
