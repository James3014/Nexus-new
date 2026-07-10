# N30R-R4 Closeout: C1 ExecutionEvidence Retry (uv env)

**Status**: INVALID_AS_PRODUCTION_CAPABILITY_TEST

## Superseded by
N30R-W0 Contract Audit — C1 does not invoke LocalModelExecutor.run(),
does not execute production localheal_pipeline retry, and contains
self-asserted production provenance.

## run ID
20260710T112500Z (approx)

## environment
- python: .venv/bin/python3 (3.14.0, uv managed)

## 8-row results
- Core baseline: 4/4 INFRA_INVALID (production pipeline timeout)
- C1 arm: 4/4 VERIFIED_FAIL (retries triggered, 1 retry each)
- C1 retries: 4/4 (all tasks got evidence retry)
- trust_mismatch: 0
- receipt_complete: 8/8

## conclusion
C1 retry mechanism works (4/4 retries triggered).
Core baseline INFRA_INVALID due to production pipeline timeout.
C1 arm doesn't hit production pipeline timeout because it runs through
a lighter path (not localheal_pipeline).
