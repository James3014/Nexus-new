# Nexus Flash Cost Optimization (P6) - 2026-05-03

## Scope
- Model: `gemini-3-flash-preview`
- Tasks: `scripts/bench/public_benchmark_nexus_value_v1.json` (`max_tasks=6`)
- Hidden verifier: enabled
- A/B mode: same model, `with_nexus` vs `without_nexus`

## Baseline (frozen)
- Run: `.nexus/reports/bench_flash_v5_p14/capability_lift_r5b`
- with_nexus:
  - solve_rate: `1.0000`
  - semantic_verified_rate: `1.0000`
  - trust_mismatch_rate: `0.0000`
  - avg_wall_time_sec: `60.1919`

## Optimization implementation
1. `UltraReviewService` benchmark knobs:
   - `NEXUS_ULTRA_REUSE_WORKTREE=1` (reuse worktree in benchmark lane)
   - `NEXUS_ULTRA_SKIP_GHOST_REGRESSION=1` (lean lane only)
2. Added tests:
   - `test_ultra_review_can_reuse_worktree_in_benchmark_mode`
   - `test_ultra_review_can_skip_ghost_regression_via_env`
3. Validation test command:
   - `uv run pytest -q tests/engine/test_ultra_review_service.py -k "reuse_worktree or skip_ghost or empty_diff_fast_path"`

## Experimental runs

### A) Full governance optimized
- Run: `.nexus/reports/bench_flash_cost_opt_p6/full_governance_opt_r1`
- Config: `inprocess + reuse_worktree`, ghost regression kept
- with_nexus:
  - solve_rate: `1.0000`
  - semantic_verified_rate: `1.0000`
  - trust_mismatch_rate: `0.0000`
  - avg_wall_time_sec: `66.2917`
- Result vs baseline:
  - wall time change: `+10.13%` (slower)
  - quality unchanged

### B) Lean governance optimized
- Run: `.nexus/reports/bench_flash_cost_opt_p6/lean_governance_opt_r1`
- Config: `inprocess + reuse_worktree + skip_ghost_regression`
- with_nexus:
  - solve_rate: `1.0000`
  - semantic_verified_rate: `1.0000`
  - trust_mismatch_rate: `0.0000`
  - avg_wall_time_sec: `42.8234`
- Result vs baseline:
  - wall time change: `-28.86%` (faster)
  - quality unchanged

## P6 success verdict
- Criterion: with_nexus wall time reduction >= 20%, no quality regression.
- Verdict: **PASS** (using Lean governance lane)
  - Speed: `60.1919s -> 42.8234s` (`-28.86%`)
  - Solve/Semantic: `1.0 / 1.0` maintained
  - Trust mismatch: `0.0` maintained

## Notes
- Full governance lane did not reduce time; it remains valid as public trust-max profile.
- Lean governance lane is now validated as cost-optimized profile for repeated benchmark iterations.
- `without_nexus` in lean run had one infra parse error row (`eligible_n=5`), but with_nexus P6 gating metrics are complete and stable.
