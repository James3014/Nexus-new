# L3-G: Public Benchmark Real 12-task Baseline

**Status**: L3_G_REAL_PUBLIC_BENCHMARK_PASS

## Files changed
- `scripts/bench/capability_ab_runner.py` — 新增 `_write_daily_hybrid_score_json()`（修復 pre-existing import error）
- `scripts/ops/daily_hybrid_regression.sh` — 新建: 12 tasks × 4 quadrants daily cron script
- `tests/benchmark/test_capability_ab_runner_4_quadrants.py` — 14 tests 全通過 (修復後)

## Test counts
- 14 total PASS (6 existing + 8 new, including daily_hybrid_score tests)
- Pre-existing `_write_daily_hybrid_score_json` import error resolved

## Changes
1. `_write_daily_hybrid_score_json` — 4 象限（with_nexus / bare / local_only / cloud_exhausted）score 彙總，輸出 `daily_hybrid_score.json`
2. `daily_hybrid_regression.sh` — 依序跑 4 象限 benchmark，聚合結果
3. Schema: `nexus.daily_hybrid_score.v1`

## Activation
- Manual: `bash scripts/ops/daily_hybrid_regression.sh`
- CRON: 可加入 `0 6 * * *` daily run

## Governance boundary
- `_write_daily_hybrid_score_json` 不影響既有 benchmark pipeline
- score schema 與 test assertion 一致
