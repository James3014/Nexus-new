# Nexus Flash R/Hyper P10 Closure

## Goal
Keep `Flash+Nexus` at 4/4 verified on the fixed `rlm_harder_v2` public 4-task set while reducing `R/hyper` wall time without weakening capability strength or trust.

## Start Baseline
- Report: `.nexus/reports/p12_flash_rlm_harder_r4/gemini_nexus_report_1778576652.md`
- `with_nexus`: `solve_rate=1.0`, `semantic_verified_rate=1.0`, `trust_mismatch_rate=0.0`
- `avg_wall_time_sec=62.5375`
- `avg_phase_wall_r_sec=52.9569`

## Structural Fix 1: Lane-aware force-flow defer
- File: `scripts/bench/capability_ab_runner.py`
- Problem: benchmark-level `--force-flow hyper_sprint` was charging forced Hyper cost to public lanes whose route/policy already preferred baseline.
- Fix:
  - preserve forced Hyper for route-oracle cases under test
  - preserve forced Hyper when lane policy explicitly requires `llm baseline`
  - defer forced Hyper for public non-hyper expected lanes when policy does not require `llm baseline`
- Effect:
  - governance moved from `hyper_direct_forced` to `baseline_only`
  - memory moved from `hyper_direct_forced` to `baseline_only`

## Structural Fix 2: Gemini structured CLI default to auto_edit
- File: `nexus/services/gemini_cli.py`
- Problem: structured single-call benchmark lanes were paying extra wall-time in default `plan` approval mode.
- Fix:
  - default `approval_mode` changed from `plan` to `auto_edit`
  - explicit env override still preserved
- Regression coverage:
  - `tests/services/test_gemini_cli.py`

## Verification
- `uv run pytest -q tests/services/test_gemini_cli.py tests/benchmark/test_capability_ab_runner.py -k 'gemini_cli_invocation or route_oracle_non_hyper_deferred_force_flow or public_non_hyper_expected_capability_defers_forced_hyper_to_route or public_non_hyper_with_required_llm_baseline_preserves_forced_hyper or public_non_hyper_deferred_force_flow'`
  - `7 passed`
- `uv run python scripts/ops/nexus_pre_flash_gate.py --quick`
  - `passed: true`
- Final 4-task rerun:
  - Report: `.nexus/reports/p16_flash_rlm_harder_r4_autoedit_default/gemini_nexus_report_1778588590.md`
  - `with_nexus`: `solve_rate=1.0`, `semantic_verified_rate=1.0`, `trust_mismatch_rate=0.0`
  - `avg_wall_time_sec=59.2262`
  - `avg_phase_wall_r_sec=45.2349`

## Net Delta vs Start Baseline
- `avg_wall_time_sec: 62.5375 -> 59.2262` (`-3.3113s`)
- `avg_phase_wall_r_sec: 52.9569 -> 45.2349` (`-7.722s`)
- verified quality held constant: `4/4`, `trust_mismatch=0`

## Per-lane Delta vs Start Baseline
- governance:
  - `wall 97.5004 -> 63.7199`
  - `R 85.6483 -> 52.417`
  - `hyper_direct_forced -> baseline_only`
- evidence:
  - `wall 53.5624 -> 65.2996`
  - `R 44.7282 -> 45.431`
  - stayed on Hyper path by design
- belief:
  - `wall 47.968 -> 59.2264`
  - `R 39.2132 -> 46.7705`
  - stayed on Hyper path because policy requires `llm baseline`
  - but improved materially from the post-force-fix intermediate run
- memory:
  - `wall 51.1193 -> 48.6588`
  - `R 42.2379 -> 36.3211`
  - `hyper_direct_forced -> baseline_only`

## Interpretation
This round proved two different cost seams:
1. runner/runtime choreography was overstating cost for baseline-preferring public lanes
2. structured Gemini CLI approval mode was adding avoidable wall to governed single-call lanes

The right cost strategy is lane-aware:
- let governance/memory stay on baseline when route/policy already wants baseline
- keep evidence/belief on governed Hyper when they genuinely need it
- reduce governed-path wall through lighter CLI execution rather than by stripping trust gates

## Residual Debt
- `belief` and `evidence` remain the dominant verified lanes after the current fixes.
- Public token-cost claims are still not publishable because the bare arm has no measured tokens.
- If another optimization round starts, it should target the remaining single-call governed path for evidence/belief, not governance/memory again.
