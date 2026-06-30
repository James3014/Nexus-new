# M1.2 Benchmark Telemetry Hygiene Report

**Status**: M1_2_BENCHMARK_TELEMETRY_HYGIENE_PASS

## Summary

Verified and stabilized all 10 wiring telemetry fields in the M1 benchmark. Added dedicated tests confirming telemetry is observational-only and does not influence solved outcomes.

## Files Changed

- `tests/benchmark/test_m1_real_local_solve_benchmark.py` — **created** (4 tests)

## Commands Run

| Command | Output |
|---------|--------|
| `python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py` | OK |
| `python3 -m py_compile tests/benchmark/test_m1_real_local_solve_benchmark.py` | OK |
| `uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -q` | 4 passed in 0.12s |

## Test Count

- **Total**: 4
- **Passed**: 4
- **Failed**: 0

## Telemetry Fields Confirmed

All 10 fields present in `row_data` (lines 358–368 of `m1_real_local_solve_benchmark.py`):

1. `parse_error_kind`
2. `parse_error_message`
3. `protocol_used`
4. `normalized`
5. `canonical_span_source`
6. `diff_repair_attempted`
7. `diff_repair_success`
8. `same_span_retry_count`
9. `failure_feedback_used`
10. `execution_path_modules`

## Statements

- **Telemetry only**: This change touches only test coverage. No runtime behavior changes.
- **No runtime repair**: No changes to LocalModelExecutor, protocol parser, candidate isolation, verifier, or execution rerouting.
- **No solved-rate improvement claimed**: This milestone stabilizes instrumentation fidelity; it does not improve solve rate.
