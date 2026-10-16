# Nexus R/Hyper Runner Overhead P22 Report

## Target

Make Flash+Nexus model-required public benchmark runs produce valid same-model evidence before continuing cost reduction:

- no `timeout_before_model_call` denominator loss;
- no local fallback owning final delivery on `model_required` tasks;
- clean provider token evidence;
- runner overhead separated from R/hyper phase work.

## Change

- Added a model-required gateway timeout policy in `scripts/bench/capability_ab_runner.py`.
- Preserved the normal short Flash gateway cap for non-model-required tasks.
- Raised model-required gateway timeout to fit inside the subprocess budget instead of forcing local fallback at 120s.
- Added regression tests for model-required and non-model-required timeout behavior.

## Verification

Unit and benchmark smoke:

```bash
uv run pytest tests/benchmark/test_capability_ab_runner.py -q
# 186 passed

uv run pytest \
  tests/benchmark/test_capability_ab_runner.py \
  tests/benchmark/test_gemini_nexus_report.py \
  tests/ops/test_codex_nexus_ab_smoke.py \
  tests/ops/test_nexus_pre_flash_gate.py -q
# 252 passed
```

Flash same-model 6-task model-required rerun:

```bash
NEXUS_CODEX_IGNORE_USER_CONFIG=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --max-tasks 6 \
  --without-mode gemini \
  --with-llm-mode all \
  --with-model-provider gemini \
  --gemini-model gemini-3-flash-preview \
  --with-nexus-runner subprocess \
  --enable-llm-self-heal \
  --timeout-sec 240 \
  --per-task-stop-loss-sec 300 \
  --stop-loss-sec 2400 \
  --total-timeout-sec 2400 \
  --output-dir .nexus/reports/p22_flash_model_required_6task_gateway_timeout_fix \
  --markdown-report auto
```

Key evidence from `.nexus/reports/p22_flash_model_required_6task_gateway_timeout_fix/evidence_bundle.json`:

- Flash+Nexus: `eligible_n=6`, `solve_rate=1.0`, `semantic_verified_rate=1.0`, `trust_mismatch_rate=0.0`.
- Flash bare: `eligible_n=6`, `solve_rate=1.0`, `semantic_verified_rate=1.0`, `trust_mismatch_rate=0.0`.
- Flash+Nexus model-required: `model_uplift_eligible_rate=1.0`, `model_uplift_blocked_by_local_delivery_n=0`.
- Flash+Nexus token evidence: `token_measured_rate=1.0`, `provider_token_measured_rate=1.0`, `clean_model_cost_evidence_rate=1.0`.
- Flash+Nexus runner overhead: `avg_runner_overhead_sec=0.5964`, `runner_overhead_polluted_n=0`.
- Flash+Nexus R/hyper phase: `avg_phase_wall_r_sec=60.7266`, `avg_r_phase_hyper_sprint_sec=60.7262`.
- Cost comparison: wall ratio `1.6206`, token ratio `1.0506`.
- Public claim gate remains `FAIL` only because `hidden_verifier_disabled`.

## Diagnosis

P21 stopped short because two unrelated issues were conflated:

- Benchmark contract issue: default `stop_loss_sec=600` exhausted during Nexus arm, so bare rows were marked `timeout_before_model_call`.
- Model-required timeout issue: Flash gateway timeout was capped at 120s, so three Nexus rows succeeded via local fallback and lost `model_uplift_eligible`.

P22 fixed those evidence-contract failures. The remaining bottleneck is now real and narrower: R/hyper phase work still dominates wall time even though runner overhead is cleanly below 1s.

## Residual Debt

- Public claim gate needs a hidden verifier enabled rerun before any public claim.
- R/hyper needs a second cost pass because Flash+Nexus is still `1.62x` wall over bare on the 6-task model-required smoke.
- The next pass should not further raise gateway timeouts; it should reduce R-phase orchestration and verification wall while preserving `model_uplift_eligible=1.0`.
