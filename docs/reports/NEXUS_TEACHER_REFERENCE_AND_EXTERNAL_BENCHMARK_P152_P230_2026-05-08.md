# Nexus Teacher Reference and External Benchmark P152-P230

## Final Goal

Use `GPT-5.5 direct` as the teacher reference for Nexus cost/quality tuning, while keeping public claims honest:

- Gemini 3 Flash / Gemini 3.1 Pro use same-model bare vs Nexus A/B for uplift claims.
- GPT-5.5 direct is a teacher/reference baseline, not a same-model uplift arm.
- SWE-bench Verified is an external benchmark wiring lane until official harness results exist.

## What Changed

- `teacher_student_gap_matrix.py` now supports `--teacher-arm without_nexus`, so a GPT-5.5 direct row can be used as the primary teacher denominator.
- `swe_bench_harness.py` now reads local `scripts/bench/swe-bench-verified.json`, selects a fixed subset, emits `without_nexus` and `with_nexus` prediction files, writes metadata, and makes the official SWE-bench harness opt-in.
- SWE-bench Phase 7 wiring now prefers easy Verified tasks first, so initial smoke is a wiring check rather than an accidental long-horizon benchmark.

## Verification

```bash
uv run pytest -q \
  tests/benchmark/test_teacher_student_gap_matrix.py \
  tests/benchmark/test_swe_bench_harness.py \
  tests/ops/test_codex_nexus_ab_smoke.py \
  tests/benchmark/test_public_credibility_phase_plan.py
```

Result: `16 passed`.

```bash
uv run python scripts/bench/swe_bench_harness.py \
  --max-tasks 5 \
  --output-dir .nexus/reports/phase7_swe_bench_wiring \
  --metadata-output .nexus/reports/phase7_swe_bench_wiring/swe_bench_metadata.json \
  --model gpt-5.5-direct-reference
```

Result: metadata and two 5-row prediction files were generated with the same denominator.

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_CODEX_MODEL_NAME=gpt-5.5 \
NEXUS_DIRECT_CODEX_MODEL=gpt-5.5 \
NEXUS_RLM_REPAIR_LOOP=1 \
NEXUS_DIRECT_CODEX_TIMEOUT_SEC=180 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=240 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_rlm_harder_v2.json \
  --output-dir .nexus/reports/phase152_codex55_teacher_preflight \
  --max-tasks 4 --repeat-trials 1 --timeout-sec 300 \
  --total-timeout-sec 3600 --stop-loss-sec 3600 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter all \
  --task-id-filter rlm-harder-v2-governance-001,rlm-harder-v2-evidence-001,rlm-harder-v2-belief-001,rlm-harder-v2-memory-001 \
  --force-flow hyper_sprint --with-nexus-runner subprocess --with-llm-mode all \
  --with-model-provider codex --without-mode codex \
  --enable-autoreason-executor --enable-ddtree-executor --enable-ultra-review-dry-gate \
  --llm-candidate-cap 3 --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log --preflight-only
```

Result: preflight `PASS`; `same_model=true`; `hidden_verifier_mode=true`.

## Public Claim Boundary

- GPT-5.5 direct can be used as teacher reference for gap analysis.
- GPT-5.5 direct must not be described as a same-model uplift comparison against Gemini+Nexus.
- SWE-bench Verified output remains wiring-only until `--run-official-harness` produces official results.
- Codex provider warning `direct_codex_provider_is_prompt_wearing_only_for_external_model_claims` means this route is useful for local teacher/reference diagnosis, not an external official Codex benchmark claim.

## Failure Lesson

The original gap matrix made `teacher_run/with_nexus` the primary teacher arm, which did not match the stated target of `GPT-5.5 direct`. The durable fix is an explicit teacher-arm selector rather than renaming files to fake direct rows as `with_nexus`.
