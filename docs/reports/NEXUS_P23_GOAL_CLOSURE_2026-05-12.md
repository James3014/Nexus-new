# Nexus P23 Goal Closure - Route Capability and Cost

## Goal

Make the new Nexus route prove that required capabilities are actually selected, invoked, evidenced, and outcome-contributing while reducing avoidable Flash+Nexus wall cost. The route must not trade away verified delivery, MemPalace governance, artifact/claim evidence, or trust safety.

## Change Log

- `nexus/research/local_sprint_mutator.py`
  - Added deterministic `rlm_harder_v2_filter_action` governance patch.
  - The patch is deny-by-default, allows read-only tools, and blocks destructive tools plus forbidden `logs/`, `benchmarks/`, and `.nexus/` paths.
- `nexus/research/sprint_service.py`
  - Added governance action filters to the local preflight-before-LLM contract list.
  - Kept claim/evidence rollup contracts excluded from cheap local preflight.
- `scripts/bench/capability_ab_runner.py`
  - Preserved forced `hyper_sprint` only as a zero-model local-preflight carrier for deterministic governance guard tasks.
  - Added `local_preflight_hyper_carrier` R-phase cost classification.
- `tests/research/test_sprint_service.py`
  - Added local preflight and mutator tests for the governance action filter.
- `tests/benchmark/test_capability_ab_runner.py`
  - Added route oracle and R-phase cost classification coverage for the governance fast path.
- `.nexus/reports/learn/phase_writeback.jsonl`
  - Wrote the P23 lesson: force-flow defer was re-enabling expensive baseline for a deterministic governance contract.

## Verification Evidence

### Targeted tests

```bash
uv run pytest -q \
  tests/research/test_sprint_service.py \
  -k 'governance_action_filter or rlm_governance_guard or governance_redaction or local_preflight_before_llm'
```

Result: `5 passed`.

```bash
uv run pytest -q \
  tests/benchmark/test_capability_ab_runner.py \
  -k 'public_non_hyper_expected_capability_defers_forced_hyper_to_route or public_governance_guard_skip_baseline_keeps_hyper_for_local_preflight or public_non_hyper_with_required_llm_baseline_preserves_forced_hyper'
```

Result: `3 passed`.

```bash
uv run pytest -q \
  tests/research/test_sprint_service.py -k 'local_preflight or governance' \
  tests/benchmark/test_capability_ab_runner.py -k 'route_oracle or governance_guard_skip_baseline or r_phase_cost_classifies_zero_model_local_preflight_carrier or local_preflight_nexus_delivery'
```

Result: `8 passed`.

### P15 governance fast path

Report: `.nexus/reports/p15_governance_fast_path_r2/gemini_nexus_report_1778591321.md`

With Nexus row:

- `status=SUCCESS`
- `semantic_status=VERIFIED`
- `wall_duration_sec=17.7793`
- `phase_wall_r_sec=5.7647`
- `model_calls=0`
- `total_tokens=0`
- `nexus_winner_source=local_preflight`
- `r_phase_cost_classification=local_preflight_hyper_carrier`
- `hidden_verifier_passed=true`
- `report_trust_mismatch=false`

Previous P12 same task:

- `wall_duration_sec=104.7966`
- `phase_wall_r_sec=91.4533`
- `model_calls=1`
- `total_tokens=58797`

### P16 Flash fixed 4-task A/B

Report: `.nexus/reports/p16_flash_rlm_harder_r4_fastpath/gemini_nexus_report_1778591412.md`

With Nexus summary:

- `solve_rate=1.0`
- `semantic_verified_rate=1.0`
- `trust_mismatch_rate=0.0`
- `avg_wall_time_sec=46.0137`
- `avg_phase_wall_r_sec=35.0661`
- `avg_model_calls=0.5`
- `avg_tokens=31315.75`

Without Nexus summary:

- `solve_rate=0.0`
- `semantic_verified_rate=0.0`
- `trust_mismatch_rate=0.0`

### P18 Flash 8-task expansion

Report: `.nexus/reports/p18_flash_rlm_harder_8x1_fastpath/gemini_nexus_report_1778591671.md`

With Nexus summary:

- `solve_rate=1.0`
- `semantic_verified_rate=1.0`
- `trust_mismatch_rate=0.0`
- `avg_wall_time_sec=55.9657`
- `avg_phase_wall_r_sec=43.9640`
- `avg_model_calls=0.875`
- `token_reliable_rate=1.0`

Without Nexus summary:

- `solve_rate=0.0`
- `semantic_verified_rate=0.0`
- `trust_mismatch_rate=0.0`

### P19 Pro small set

Report: `.nexus/reports/p19_pro_rlm_harder_r4_fastpath/gemini_nexus_report_1778592502.md`

With Nexus summary:

- `solve_rate=1.0`
- `semantic_verified_rate=1.0`
- `trust_mismatch_rate=0.0`
- `avg_wall_time_sec=31.0950`
- `avg_phase_wall_r_sec=20.9146`
- `avg_model_calls=0.5`

### P20 capability matrix

Matrix: `.nexus/reports/p20_capability_invocation_matrix_p23.json`

Heatmap: `docs/reports/NEXUS_P23_CAPABILITY_HEATMAP_2026-05-12.md`

Result:

- `passed=true`
- `failures=[]`
- Required runtime capabilities covered: `autoreason`, `belief`, `ddtree`, `drone`, `lancedb`, `nightshift`, `research`, `semantic_searcher`, `swarm`, `swarm_quiet_moment`, `ultra_review`

### Route smoke

Summary: `.nexus/reports/capability_route_smoke_summary.json`

Result:

- `passed=true`
- `receipt_diagnostic_pass=true`
- `route_oracles` selected-to-invoked rate: `0.9864864864864865`
- All smoke suites had `failures=[]`

## Assessment

The P23 target is met for this slice:

- Codex-operated Nexus route smoke proves the required runtime capability set is wired and evidenced.
- Flash+Nexus on fixed public tasks stayed at `100%` verified delivery with `trust_mismatch=0`.
- The governance long-tail root cause was structural and fixed at the route/preflight seam, not by disabling governance.
- Pro small-set verification also stayed at `100%` verified delivery with `trust_mismatch=0`.

## Residual Debt

- Flash 8-task average wall is still high on evidence and memory rows because those still require LLM-assisted semantic repair.
- Bare-arm token evidence remains not public-safe: without-Nexus token telemetry reports `model_call_without_tokens`.
- P18 is not publication-grade by itself. It is a fixed 8x1 validation run plus route-smoke capability evidence, not a repeated public benchmark.

## Next Long Plan

### P24: Evidence and Memory Cost Surgery

- Target `rlm-harder-v2-evidence-*` and `rlm-harder-v2-memory-*` rows.
- Build deterministic or selector-assisted local preflight only where the contract is explicit.
- Acceptance: no drop from `semantic_verified=100%`, `trust_mismatch=0`, and at least 20% wall reduction on those rows.

### P25: Bare Token Telemetry Repair

- Fix without-Nexus token capture so cost claims can become public-safe.
- Acceptance: bare arm token measured rate above the public claim threshold on the fixed public suite.

### P26: Repeated Flash 8x3 Validation

- Run Flash+Nexus and Flash bare on the fixed 8 tasks with 3 repeats.
- Stop on first failure and inspect trace before continuing.
- Acceptance: verified delivery stable, trust mismatch zero, and no capability matrix regression.

### P27: Public Candidate Report

- Generate a public-safe report only if P25 and P26 pass.
- Clearly separate capability evidence, same-model uplift, and cost claims.
