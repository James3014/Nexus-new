# Nexus Feature Reflex P74 Flash 3-Task x3 Closure

## Goal

Make Gemini 3 Flash wearing Nexus preserve verified delivery and trust safety on fixed public model-required repair/feature/docs tasks while eliminating the R/hyper wall-time long tail. Do not expand to Pro or public cost-efficiency claims until Flash evidence is public-safe.

## Context+ Topology

The previous hot path was R/hyper: feature/evidence-standard rows opened `hyper_sprint` even when a supervised bare-first or feature-reflex path could satisfy the task with Artifact/Claim/Delivery governance plus GWT and hidden-verifier evidence.

P74/P74b shows that this route hot path is now suppressed for the 3-task slice:

- `avg_phase_wall_r_sec_with`: 0.0
- `avg_r_phase_hyper_sprint_sec_with`: 0.0
- `retry_cost_share_wall`: 0.0
- `retry_cost_share_tokens`: 0.0
- `avg_model_calls_with`: 1.0
- `avg_model_calls_without`: 1.0

The new hot spot is not R/hyper. It is token telemetry public-safety for `context_sync_capped` docs rows where Gemini stats are classified as cumulative outliers.

## P74b Evidence

Command:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-repair-001,model-required-feature-001,model-required-docs-001 \
  --output-dir .nexus/reports/p74b_flash_model_required_feature_reflex_3task_3trial \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 3 \
  --timeout-sec 240 \
  --total-timeout-sec 2700 \
  --stop-loss-sec 2700 \
  --per-task-stop-loss-sec 300 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Result:

- with Nexus: 9/9 eligible verified delivery, semantic verified rate 1.0.
- bare: 9/9 eligible, semantic verified rate 0.3333.
- trust mismatch: 0.0 on both arms.
- delivery claim gate: PASS.
- public claim gate: FAIL.
- public cost claim gate: FAIL.
- public cost efficiency claim gate: REGRESSED.
- allowed public wording: `verified_delivery_uplift`.

Cost and telemetry:

- with Nexus avg wall: 72.5761s.
- bare avg wall: 65.9788s.
- wall ratio: 1.1x.
- median paired wall ratio: 1.5441x.
- with Nexus avg tokens: 50401.6667.
- bare avg tokens: 63882.7778.
- token ratio: 0.789x.
- with Nexus token measured rate: 0.7778.
- with Nexus provider token measured rate: 0.7778.

The cost-safety failure is caused by two `model-required-docs-001` Nexus rows:

- `runtime_classification`: `nexus_supervised_bare_first`
- `route_cost_policy_lane`: `context_sync_capped`
- `gateway_token_source`: `estimated_from_stats_outlier`
- `token_capture_status`: `estimated`
- `phase_wall_r_sec`: null
- `r_phase_hyper_sprint_sec`: null
- hidden verifier: passed

## Acceptance Evidence Gate

Verdict: RETURN for final public cost-efficiency target, PASS for the narrower R/hyper suppression slice.

Reasons:

- PASS: verified delivery uplift exists under same-model lock.
- PASS: trust mismatch remains 0.
- PASS: R/hyper long-tail is removed for this 3-task x3 Flash slice.
- RETURN: public cost-safety gate cannot pass while provider token measured rate is 0.7778.
- RETURN: cost-efficiency remains REGRESSED because wall is still not improved versus bare.

## Failure Lesson

Do not keep tuning R/hyper for this slice after `phase_wall_r_sec=0` and `r_phase_hyper_sprint_sec=0`. The next blocker is the token telemetry seam for supervised bare-first/context-sync docs rows: `_apply_direct_gemini_stats_outlier_policy` and `BattlesuitGateway.ask_structured` downgrade suspected cumulative Gemini stats to estimated tokens, which is safe for anti-fraud accounting but prevents public cost-safety claims.

The next optimization must distinguish true cumulative stats outliers from valid low-payload provider usage, while preserving fail-closed behavior. Do not mark outlier-derived tokens as measured unless the raw provider source is provably request-local.

## Next Long Plan

Final target: Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus approaches GPT-5.5 direct verified delivery on fixed public tasks, with trust mismatch 0 and public-safe evidence. Current local target: Flash 3-task x3 must keep delivery PASS, R/hyper 0, and recover public cost-safety telemetry before any Pro expansion.

P75. Add raw provider telemetry fields for stats outliers: `raw_provider_total_tokens`, `raw_provider_token_source`, `gateway_token_outlier_reason`, and `provider_stats_cumulative_suspected` must survive into benchmark rows and evidence bundles.

P76. Split provider token verdicts: keep `token_capture_status=estimated` for suspected cumulative stats, but expose `token_accounting_failure_class=provider_stats_outlier` so reports do not confuse route cost with telemetry uncertainty.

P77. Add tests for `_apply_direct_gemini_stats_outlier_policy` proving both cases: obvious cumulative stats remain estimated; request-local small direct Gemini stats stay measured when source metadata supports it.

P78. Add gateway parity tests for `BattlesuitGateway.ask_structured` so gateway and benchmark runner classify stats outliers identically.

P79. Extend markdown and evidence bundle wording: delivery PASS with cost-safety FAIL must say telemetry blocker, not route/hyper blocker.

P80. Rerun Flash 3-task x3. Required to proceed: delivery PASS, trust mismatch 0, avg R/hyper 0, and no ambiguous telemetry reason. If cost-safety still FAIL, stop and inspect row-level outlier fields before any further benchmark.

P81. If telemetry becomes measured/public-safe but wall still regresses, split provider latency into prompt build, model call, verifier, and subprocess wait. Optimize wall only after token accounting is trustworthy.

P82. Run Pro x1 only after P80/P81 pass for Flash. Do not use Pro to hide Flash telemetry defects.

P83. Produce consolidated public-claim posture report with delivery, cost safety, and cost efficiency separated.

P84. Write learning closure and training-export eligibility only for rows with evidence bundle, same-model before/after, hidden verifier, and public-safe cost telemetry.
