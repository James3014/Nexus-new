# F-09A Test Suppression Audit

**Status:** `F09A_TEST_SUPPRESSION_AUDIT`

**Date:** 2026-06-29

## Summary

Inventory of 16 test suppressions across 7 tracked files (1 untracked file excluded).

## Suppressions by File

| File | Count | Type | Tracked? |
|---|---|---|---|
| `tests/integration/test_rust_kernel_smoke.py` | 6 | Rust binary guard | Yes |
| `tests/unit/test_env_resolver_imports.py` | 2 | Environment guard | Yes |
| `tests/engine/test_sandbox_elastic_profile.py` | 2 | macOS guard | Yes |
| `tests/engine/test_sandbox_actions.py` | 2 | Platform guard | Yes |
| `tests/integration/test_rust_wave3_cutover.py` | 1 | Rust binary guard | Yes |
| `tests/integration/test_real_ollama_solve_lane.py` | 1 | Ollama guard | Yes |
| `tests/integration/test_real_qwen_small_batch_solve_eval.py` | 1 | Ollama guard | Yes |

Note: `tests/benchmark/test_local_model_executor_planner_path.py` (2 suppressions) is untracked and excluded from this audit scope.

## Classification

| Classification | Count | Examples |
|---|---|---|
| Legitimate environment guard | 6 | macOS sandbox, python3 executable |
| Real external dependency guard | 7 | Ollama, Rust binary |
| Stale suppression candidate | 0 | None found |
| Likely dead test | 0 | None found |

## Top 5 Low-Risk Fixes

None identified — all 16 suppressions are legitimate environment/dependency guards.

## Commands Run

```bash
rg -n '@pytest\.mark\.skip|@pytest\.mark\.skipif|@pytest\.mark\.xfail|pytest\.skip\(' tests --glob '*.py'
rg -c '@pytest\.mark\.skip|@pytest\.mark\.skipif|@pytest\.mark\.xfail|pytest\.skip\(' tests --glob '*.py'
```

## Scope Statement

- Audit only, no test changes
- All suppressions are legitimate
- No stale/dead tests found
- Untracked file excluded from count
