# Workspace Failure Claim Guard

**日期**: 2026-06-17

---

## Purpose

Ensures workspace/infra failures are never counted as patcher or model failures.
Ensures model_calls=0 and deterministic/AST fallback are never exported as model patch success.

---

## Rules

### Workspace failure classes

If `failure_class` in:
- `workspace_not_configured`
- `workspace_provisioning`
- `repo_not_mounted`
- `import_error`
- `target_path_unresolved`
- `file_not_found`
- `env_fixable_by_agent`
- `DEPENDENCY_MISMATCH`
- `TOOLCHAIN_MISSING`

Then:
- `count_as_patcher_failure = false`
- `count_as_model_failure = false`
- `claim_eligible = false`
- `public_claim_allowed = false`
- `export_as_model_patch_success = false`
- `export_as_internal_infra_failure = true`

---

### model_calls=0

- `model_patch_reward = 0.0`
- `export_as_model_patch_success = false`

---

### deterministic_fallback_used=true

- `model_patch_reward = 0.0`
- `export_as_model_patch_success = false`

---

### canonical_span_source=ast_boundary and model_calls=0

- `export_as_canonical_recovery_success = true`
- `export_as_model_patch_success = false`

---

### claim_eligible=false

- `public_claim_allowed = false`
- `export_as_public_claim = false`

---

## Implementation

Module: `nexus/services/local_heal/export_guard.py`

Functions:
- `is_workspace_failure(failure_class)` → bool
- `should_export_as_model_patch_success(...)` → bool
- `should_export_as_canonical_recovery_success(...)` → bool
- `should_export_as_internal_infra_failure(...)` → bool
- `get_export_eligibility(...)` → dict
- `apply_export_guard(receipt)` → receipt

---

## Tests

15 tests in `tests/unit/test_export_guard.py`:
- `TestIsWorkspaceFailure` (2 tests)
- `TestExportModelPatchSuccess` (5 tests)
- `TestExportCanonicalRecovery` (3 tests)
- `TestExportInfraFailure` (2 tests)
- `TestGetExportEligibility` (2 tests)
- `TestApplyExportGuard` (1 test)
