# N30R-R3 Closeout: Transfer Screen (uv env, production path)

**Status**: N30R_R3_TRANSFER_SCREEN_INVALID

## environment
- python: .venv/bin/python3 (3.14.0, uv managed)
- lancedb: 0.30.2

## run ID
20260710T111959Z

## 32-row results
- Bare solved: 0/16
- Core solved: 0/16
- Core INFRA_INVALID: 16/16 (production pipeline timeout 69-250s)
- planner_called core: 16/16
- pipeline_called core: 16/16
- trust_mismatch: 0
- receipt_complete: 32/32

## conclusion
Benchmark status = INVALID. All 16 core rows are INFRA_INVALID due to
localheal_pipeline execution timeout in benchmark environment.
The production pipeline IS reached (planner=True, pipeline=True), but
the pipeline's model call + isolation + verify cycle exceeds timeout.

This is a production infrastructure constraint, not a bridge wiring issue.
