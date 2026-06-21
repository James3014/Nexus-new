# AO2 — Live Regression Entrypoint Plan

**Date**: 2026-06-21
**Status**: PLAN READY

---

## Goal

Restore/add executable C_12481 and C_13453 regression entrypoints for live verification.

## Current State

- C_12481 and C_13453 are referenced in tests as regression anchors
- No executable entrypoint exists for live SWE-bench regression
- Fixture data may exist in `artifacts/runtime/` directories

## Required Steps

### 1. Locate Existing Fixtures

```
artifacts/runtime/c4_7b_repair_v0/C_12481/
artifacts/runtime/c4_7b_repair_v0/C_13453/
```

Check for:
- `receipt.json`
- `verification_report.json`
- Problem statements
- Source file snapshots

### 2. Create Executable Entrypoint Scripts

**Script 1**: `scripts/bench/run_c12481_regression.py`
- Load fixture data
- Run local_heal pipeline
- Verify against expected behavior
- Write receipt to `artifacts/runtime/ao2_regression/C_12481/`

**Script 2**: `scripts/bench/run_c13453_regression.py`
- Same structure as above
- Write receipt to `artifacts/runtime/ao2_regression/C_13453/`

### 3. Required Fixtures Per Task

| Fixture | C_12481 | C_13453 |
|---------|---------|---------|
| problem_statement | Required | Required |
| target_file | Required | Required |
| failing_symbol | Required | Required |
| expected_behavior | Required | Required |
| verifier_command | Required | Required |

### 4. Verifier Commands

**C_12481**: 
```bash
python -m pytest tests/unit/ -k "test_constructor_normalization" -q
```

**C_13453**:
```bash
python -m pytest tests/unit/ -k "test_output_formatting" -q
```

### 5. Expected Artifact Paths

```
artifacts/runtime/ao2_regression/C_12481/
  receipt.json
  verification_report.json
  evidence_graph.json
  model_output.txt

artifacts/runtime/ao2_regression/C_13453/
  receipt.json
  verification_report.json
  evidence_graph.json
  model_output.txt
```

### 6. Avoid Hardcoded Expected Patches

- Verifier must check behavior, not exact patch content
- Expected behavior defined in problem statement
- Pass/fail determined by test execution, not string matching

### 7. Unavailable External Dependencies

If SWE-bench test suites are not available locally:
- Mark as `EXTERNAL_DEPENDENCY_MISSING`
- Use local unit tests as proxy
- Record in receipt as `VERIFIER_PROXY`

## Implementation Priority

1. Check if fixtures exist in existing artifact directories
2. Create minimal entrypoint scripts
3. Wire into test suite
4. Verify live execution
