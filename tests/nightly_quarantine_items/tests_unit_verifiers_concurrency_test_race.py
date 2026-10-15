"""Nightly quarantine entry: tests/unit/verifiers/concurrency/test_race.py (#1923). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/verifiers/concurrency/test_race.py",
    "disposition": "quarantine",
    "issue": "#1923",
    "cause": "red by design: test_race.py is the repair-benchmark verifier for the intentionally broken BuggyIdempotentExecutor (76af3d5b5); used by scripts/bench/m1_real_local_solve_benchmark.py and tests/benchmark/test_local_model_executor_planner_path.py; the real invariant is covered by FixedIdempotentExecutor in test_concurrency_batch_b02.py; not a product bug",
    "tests": ("TestBatchB02RaceFixed::test_idempotent_executor_green_stress",),
}
