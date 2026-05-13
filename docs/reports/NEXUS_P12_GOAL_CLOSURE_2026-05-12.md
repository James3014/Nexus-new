# Nexus P12 Goal Closure

## Goal
Complete the current total objective:

1. Use `Codex+Nexus` as the capability wiring verifier before Flash cost tuning.
2. Confirm the new route can select, invoke, evidence, and close the core capability chain.
3. Rerun `Flash+Nexus` versus `Flash bare` on the fixed 4-task `rlm_harder_v2` set.
4. Preserve verified delivery and trust while reducing `R/hyper` wall time.
5. Write failures and useful corrections back into the learning loop.

## P1-P2: Frozen Gates And Baselines
- Branch: `main`
- Dirty state: large pre-existing Nexus route/capability/benchmark worktree; no unrelated files were reverted.
- Start baseline: `.nexus/reports/p12_flash_rlm_harder_r4/gemini_nexus_report_1778576652.md`
  - `solve_rate=1.0`
  - `semantic_verified_rate=1.0`
  - `trust_mismatch_rate=0.0`
  - `avg_wall_time_sec=62.5375`
  - `avg_phase_wall_r_sec=52.9569`
- Previous optimized baseline: `.nexus/reports/p16_flash_rlm_harder_r4_autoedit_default/gemini_nexus_report_1778588590.md`
  - `solve_rate=1.0`
  - `semantic_verified_rate=1.0`
  - `trust_mismatch_rate=0.0`
  - `avg_wall_time_sec=59.2262`
  - `avg_phase_wall_r_sec=45.2349`

## P3-P5: Codex+Nexus Capability Closure
`Codex+Nexus` was treated as a route and wiring verifier, not as the public solve-rate arm.

Verification:
- `uv run python scripts/ops/codex_nexus_ab_smoke.py --print-only --preflight-only`
  - `plan_validation.passed=true`
  - same-model lock: `gpt-5.5`
  - task count: `4`
  - preflight-only: `true`
- `uv run python scripts/ops/nexus_pre_flash_gate.py --quick`
  - `passed=true`
  - `codex_nexus_smoke_plan.passed=true`
  - `capability_wiring_audit.passed=true`
  - `mutation_assurance_gate.passed=true`
  - `harness_engineering_gate.passed=true`
- `uv run python scripts/ops/capability_invocation_matrix.py --arm route_smoke:.nexus/reports/capability_route_smoke_summary.json --arm flash_nexus:.nexus/reports/p16_flash_rlm_harder_r4_autoedit_default/with_nexus_1778588590.jsonl --output .nexus/reports/p12_goal_capability_invocation_matrix.json --markdown-output docs/reports/NEXUS_P12_GOAL_CAPABILITY_HEATMAP_2026-05-12.md`
  - `passed=true`
  - no required runtime capability gaps
  - heatmap green for route/runtime core capabilities

Core capabilities verified in the matrix:
- `autoreason`
- `belief`
- `ddtree`
- `drone`
- `lancedb`
- `nightshift`
- `research`
- `semantic_searcher`
- `swarm`
- `swarm_quiet_moment`
- `ultra_review`

Related capability evidence also stayed green:
- `artifact_gate`
- `claim_gate`
- `codeintel`
- `delivery_gate`
- `hyper`
- `memory`
- `mempalace_gate`
- `semantic_failure_sensor`
- `bdd_acceptance_skill`
- `harness_preflight_sensor`

## P6-P10: Flash Same-Model A/B
Command:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=240 \
NEXUS_RLM_REPAIR_LOOP=1 \
NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=180 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_rlm_harder_v2.json \
  --output-dir .nexus/reports/p12_goal_flash_rlm_harder_r4 \
  --max-tasks 4 --repeat-trials 1 --timeout-sec 300 \
  --total-timeout-sec 3600 --stop-loss-sec 3600 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter all \
  --task-id-filter rlm-harder-v2-governance-001,rlm-harder-v2-evidence-001,rlm-harder-v2-belief-001,rlm-harder-v2-memory-001 \
  --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

Initial sandbox run failed because `uv` could not read `/Users/jameschen/.cache/uv/sdists-v9/.git`. The benchmark was rerun with approved execution permissions.

Final report:
- `.nexus/reports/p12_goal_flash_rlm_harder_r4/gemini_nexus_report_1778589613.md`

Final `with_nexus` metrics:
- `eligible_n=4`
- `solve_rate=1.0`
- `semantic_verified_rate=1.0`
- `trust_mismatch_rate=0.0`
- `avg_wall_time_sec=56.8026`
- `avg_phase_wall_r_sec=45.0497`
- `avg_r_phase_hyper_sprint_sec=13.155`
- `avg_tokens=44963.5`
- `avg_model_calls=0.75`

Final `without_nexus` metrics:
- `eligible_n=4`
- `solve_rate=0.0`
- `semantic_verified_rate=0.0`
- `trust_mismatch_rate=0.0`
- `avg_wall_time_sec=0.9869`
- `token_reliable_rate=0.0`

Delta versus original start baseline:
- `avg_wall_time_sec: 62.5375 -> 56.8026` (`-5.7349s`)
- `avg_phase_wall_r_sec: 52.9569 -> 45.0497` (`-7.9072s`)
- verified quality held: `4/4`, `trust_mismatch=0`

Delta versus previous optimized baseline:
- `avg_wall_time_sec: 59.2262 -> 56.8026` (`-2.4236s`)
- `avg_phase_wall_r_sec: 45.2349 -> 45.0497` (`-0.1852s`)
- verified quality held: `4/4`, `trust_mismatch=0`

Per-lane R phase in the final rerun:
- governance: `91.4533s`, `baseline_only`
- evidence: `49.7362s`, `hyper_direct_hard_skip_probe`
- belief: `2.8844s`, `hyper_direct_forced`
- memory: `36.1249s`, `baseline_only`

## P11: Learning Writeback
Two lessons were written to `.nexus/reports/learn/phase_writeback.jsonl`:

- `p12_goal_uv_cache_sandbox_block`
- `p12_goal_flash_rhyper_verified_cost_closure`

## P12: Closure Status
Goal gate: `PASS`.

What is complete:
- `Codex+Nexus` capability preflight and wiring closure passed.
- Route/runtime required capability matrix passed.
- `Flash+Nexus` versus `Flash bare` reran on the fixed 4-task set.
- `Flash+Nexus` preserved `4/4 verified` and `trust_mismatch=0`.
- `R/hyper` average wall improved against both the original and previous optimized baselines.
- Learning writeback was updated.

Residual debt:
- Public claim gate remains `FAIL` in the final report because token and Nexus-wearing public-claim fields are not sufficient for a public marketing claim.
- `without_nexus` still has no reliable token measurement, so token-cost claims are internal only.
- governance row is still the long tail in this rerun despite the average improvement; the next optimization should focus on governance baseline path timing without removing governance gates.
