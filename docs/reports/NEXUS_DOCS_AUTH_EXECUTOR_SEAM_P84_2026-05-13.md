# Nexus P84 Docs Auth and Executor Seam Report

Date: 2026-05-13

## Goal

Continue toward the current cost-reliability target:

- keep model-required docs tasks from silently ending with zero model participation;
- make Gemini auth prompts fail fast instead of burning wall time;
- expose R/hyper executor and gateway/provider timing so the next wall-time cut is evidence-driven.

This slice does not claim the final wall-time target is complete.

## Context+ Result

Topology finding:

- `NEXUS_FORCE_INPLACE_EXECUTOR=1` was already wired in benchmark subprocess paths.
- The missing piece was not another env flag; it was evidence that the runtime actually selected `inplace` and where the R/hyper wall time went.

Hotspots:

- `scripts/bench/capability_ab_runner.py`: model-required direct route could return `model_calls=0` and stop at `hyper_admission_reason=no_model_call`.
- `scripts/bench/capability_ab_runner.py`: direct Gemini auth prompt waited until timeout.
- `nexus/research/sprint_service.py`: executor selection and gateway timing were not surfaced through `SprintResult`.

## Acceptance Gate Result

Verdict: RETURN

Reason:

- unit/regression tests pass;
- docs lane now falls back from no-model direct route to model-owned baseline;
- auth prompt now fails fast in benchmark runner;
- executor and provider timing fields are now available;
- live docs sample still has incomplete public evidence because expected capability receipts are missing and provider token evidence is not measured.

## Code Changes

- `nexus/research/sprint_service.py`
  - adds `executor_selected`, `executor_forced_inplace`, `executor_init_sec`;
  - writes executor selection into `learning_trace["executor"]`;
  - propagates gateway timing fields from LLM candidate metadata into `SprintResult`.

- `scripts/bench/capability_ab_runner.py`
  - aborts subprocesses early when Gemini auth confirmation prompt is detected;
  - classifies non-zero Gemini auth prompt exits as `auth_confirmation_required`;
  - surfaces `executor_selected`, `executor_forced_inplace`, `executor_init_sec` in benchmark rows;
  - adds model-required fallback: if direct route with `skip_llm_baseline` returns `model_calls=0`, rerun once with `--llm-baseline --llm-baseline-required`.

- `tests/research/test_sprint_service.py`
  - verifies forced in-place executor telemetry and gateway provider wait passthrough.

- `tests/benchmark/test_capability_ab_runner.py`
  - verifies auth prompt early abort;
  - verifies row executor/gateway timing fields;
  - verifies model-required direct route no-model-call fallback.

## Verification

Targeted:

```bash
uv run pytest \
  tests/research/test_sprint_service.py::test_llm_mode_can_force_inplace_executor \
  tests/benchmark/test_capability_ab_runner.py::test_extract_record_maps_semantic_fields \
  tests/benchmark/test_capability_ab_runner.py::test_process_group_aborts_gemini_auth_prompt_before_timeout \
  tests/benchmark/test_capability_ab_runner.py::test_direct_gemini_auth_confirmation_timeout_is_classified \
  tests/benchmark/test_capability_ab_runner.py::test_model_required_direct_route_falls_back_to_model_baseline_when_no_model_call -q
```

Result: 5 passed.

Broader:

```bash
uv run pytest \
  tests/research/test_sprint_service.py \
  tests/benchmark/test_capability_ab_runner.py \
  tests/services/test_gemini_cli.py \
  tests/benchmark/test_gemini_nexus_report.py -q
```

Result: 297 passed.

Live docs sample:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 .venv/bin/python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-docs-001 \
  --output-dir .nexus/reports/p84_docs_auth_model_fallback_1trial \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 1 \
  --timeout-sec 240 \
  --total-timeout-sec 600 \
  --stop-loss-sec 600 \
  --per-task-stop-loss-sec 300 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Observed:

- with Nexus wall: 3.0825 sec;
- with Nexus status: `SUCCESS` / `VERIFIED`;
- with Nexus `model_required_direct_fallback_used`: true;
- with Nexus `model_calls`: 1;
- with Nexus `run_eligible`: false;
- with Nexus invalid reason: `nexus_delivery_invalid`;
- bare wall: 1.7296 sec;
- bare invalid reason: `auth_failed`.

## Residual Debt

- Expected docs capability receipts remain missing: `codeintel`, `memory`, `delivery_gate`.
- The live docs fallback path still has `total_tokens=0`, so it is not cost-evidence eligible.
- The next slice must wire receipt evidence and provider token telemetry for the fallback row before expanding to 3-task x3.

