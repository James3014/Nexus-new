# N3 — P3 Retry Stub Decision Report

**Gate**: policy_capability
**Date**: 2026-07-10

## Decision

| Dimension | Decision | Rationale |
|-----------|----------|-----------|
| Should retry stub exist | YES | Delegated retry must be testable independently of real LLM calls |
| Where | `local_heal/` | Colocated with the retry logic it stubs |
| Stub contract | Returns fixed patch for known failures | Enables deterministic CI testing |
| Test coverage | 3 tests (N7-1, N7-2, N7-3) | Solved field, delegation flag, verifier pass |

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| No stub, use real model | Non-deterministic, slow, requires GPU |
| Stub at router level | Adds unnecessary indirection for unit tests |
| Factory pattern | Over-engineering for a deterministic stub |

## Claims

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Retry stub decision documented | This report | ✅ PASS |
| Test scenarios defined | N7-1/N7-2/N7-3 in test file | ✅ PASS |
| Stub contract specified | Fixed patch for known failures | ✅ PASS |

## Residual Debt

None.
