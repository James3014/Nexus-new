# LocalHeal Sprint C15-4C-1: Controlled Verifier Failure Task Spec

**Status**: `C15_4C_1_CONTROLLED_VERIFIER_FAILURE_TASK_SPEC_PASS`

**Date**: 2026-07-03

---

## Task ID Added

`toy-math-verifier-evidence-gap`

---

## Task Intent

Create a bounded task where:
1. First-pass solution is unlikely because the problem statement is underspecified
2. Verifier script emits actionable evidence revealing the missing rule
3. Delegated retry can use verifier evidence to produce the correct repair

---

## Why First-Pass Should Be Less Likely to Solve

The problem statement says:
```
Bug: The function `normalize_score` in toy/math_util.py has a correctness issue.
Fix it so that the verifier tests pass. The verifier script tests multiple edge cases.
```

This does NOT reveal:
- The function should clamp output to [0, 1] range
- The function should handle max_val == min_val case
- The function should avoid ZeroDivisionError

The model would need to guess the correct behavior without knowing the specific requirements.

---

## What Verifier Evidence Reveals

The verifier script checks three conditions and prints evidence on failure:

1. **Clamp check**: `EVIDENCE: normalize_score does not clamp output to [0, 1] range`
2. **Divide-by-zero check**: `EVIDENCE: normalize_score does not handle max_val == min_val case`
3. **ZeroDivisionError check**: `EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val`

Expected behavior printed:
```
EXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max
```

This evidence is actionable — a delegated retry can use it to produce the correct fix.

---

## Commands Run

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py tests/benchmark/test_m1_real_local_solve_benchmark.py
```

```bash
uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -k "c15_4c_1 or m1_real_local_solve" -q
```

**Result**: 19 passed

---

## Test Counts

| File | Tests |
|------|-------|
| `test_m1_real_local_solve_benchmark.py` | 19 (14 existing + 5 new C15-4C-1) |

---

## Optional Live Row

Not run (task-spec and test only, live proof is C15-4C-2).

---

## Statements

- **No runtime behavior changed**: This task only adds a task spec and tests.
- **No route authority changed**: No new RouteMode, Router, Planner, or topology selector.
- **delegated_retry solved NOT_PROVEN**: This task does not prove delegated_retry solved.
- **production_ready=false**: This task spec is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.

---

## Next Recommended Task

`C15-4C-2 Forced Delegated Retry Live Probe`

Run bounded live attempts with `toy-math-verifier-evidence-gap` to verify:
1. First-pass fails verifier
2. Verifier evidence is captured
3. Delegated retry uses evidence
4. Delegated retry produces correct patch
