# N4 — Env Flag Decision Report

**Gate**: policy_capability
**Date**: 2026-07-10

## Decision

| Dimension | Decision | Rationale |
|-----------|----------|-----------|
| NEXUS_LEARNING_LOOP_WRITE_ENABLED default | `1` (enabled) | Per M1 commit 6f7cf2771; maintain backward compatibility |
| Toggle behavior | `0` disables, `1` enables | Standard boolean env flag convention |
| Code fallback | `None` treated as enabled | Ensures unset env does not break existing behavior |
| Test location | `tests/perf/test_router_latency.py` (N10), `tests/core/test_router_learning_loop.py` (N12) | Separates perf from functional tests |

## Files

| File | Purpose |
|------|---------|
| `tests/perf/test_router_latency.py` | N10 latency test + N11 baseline |
| `tests/core/test_router_learning_loop.py` | N12 env flag toggle tests |

## Claims

| Claim | Evidence | Verdict |
|-------|----------|---------|
| N10 router latency test exists | `test_router_latency_with_learning_loop_enabled` | ✅ PASS |
| N12 env flag default consistent | `test_router_env_flag_default_consistent` | ✅ PASS |
| N12 toggle on/off tests exist | `test_router_env_flag_can_toggle_off`, `test_router_env_flag_can_toggle_on` | ✅ PASS |
| Default is `1` (enabled) | Code fallback: `None` treated as enabled | ✅ PASS |
| N13 benchmark scenarios defined | N10—N12 cover perf + env flag | ✅ PASS |

## Benchmark Scenarios (N13)

| Scenario | Expected |
|----------|----------|
| Learning loop ON → measure router latency | < 5000ms avg per task |
| Learning loop OFF → measure router latency | < 5000ms avg per task |
| Env flag unset → treated as enabled | None → enabled |
| Env flag `0` → disabled | Toggle off test passes |
| Env flag `1` → enabled | Toggle on test passes |

## Residual Debt

None.
