# Nexus R/Hyper Runner Overhead P27 Fail-Closed Report

Date: 2026-05-13

## Goal

Make model-required Flash+Nexus evidence honest before further cost tuning:

- A model-required task must not be counted as Nexus success when the final passing delivery is owned by local fallback.
- Timeout rows must keep `timeout_before_receipt` instead of being collapsed into generic Nexus invalid delivery.
- R/hyper wall-time analysis must distinguish true model repair time from runner overhead and fallback pollution.

## Changes

- `nexus/research/sprint_service.py`
  - Added model-owned source classification.
  - Added runtime fail-closed guard for `NEXUS_MODEL_REQUIRED_EXECUTION_MODE=model_participation*`.
  - If the winning candidate is `local*`, the sprint now returns `FAILED` with `model_required_local_delivery_blocked` instead of `SUCCESS`.

- `scripts/bench/capability_ab_runner.py`
  - Persisted `nexus_failure_reason` and `nexus_error_codes` into benchmark rows.

- `scripts/bench/benchmark_eligibility.py`
  - Preserved `timeout_before_receipt` for with-Nexus subprocess timeouts.
  - Classified explicit model-required local final delivery as `model_required_local_delivery_blocked` even when semantic completion is false.

- `tests/research/test_sprint_service.py`
  - Added runtime regression coverage for model-required local fallback fail-closed behavior.

- `tests/benchmark/test_capability_ab_runner.py`
  - Added eligibility coverage for local final delivery after model calls.
  - Added eligibility coverage for fail-closed local delivery without semantic completion.
  - Added timeout-stage preservation coverage.

## Verification

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py \
  tests/research/test_sprint_service.py -q
```

Result:

```text
243 passed in 18.76s
```

Targeted Flash+Nexus smoke:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 NEXUS_CODEX_IGNORE_USER_CONFIG=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --output-dir .nexus/reports/p27_flash_model_required_repair_failclosed \
  --task-id-filter model-required-repair-001 \
  --max-tasks 1 \
  --timeout-sec 210 \
  --per-task-stop-loss-sec 240 \
  --stop-loss-sec 280 \
  --total-timeout-sec 280 \
  --with-nexus-runner subprocess \
  --with-llm-mode hard \
  --with-model-provider gemini \
  --gemini-model gemini-3-flash-preview \
  --force-learn-slo-ready \
  --neutralize-history \
  --materialize-missing \
  --nexus-only \
  --enable-llm-self-heal \
  --evidence-bundle \
  --markdown-report auto
```

Key row:

```json
{
  "task_id": "model-required-repair-001",
  "status": "FAILED",
  "run_eligible": false,
  "infra_invalid_reason": "model_required_local_delivery_blocked",
  "model_uplift_eligible": false,
  "model_uplift_ineligible_reason": "infra_invalid:model_required_local_delivery_blocked",
  "nexus_failure_reason": "model_required_local_delivery_blocked",
  "nexus_error_codes": ["model_required_local_delivery_blocked"],
  "nexus_winner_source": "local",
  "fallback_used": true,
  "model_calls": 1,
  "total_tokens": 67882,
  "phase_wall_r_sec": 78.1806,
  "wall_duration_sec": 90.6969
}
```

## Diagnosis

The prior loop stopped early because the benchmark summary showed failure, but the failure was still not structurally clean:

- Runtime had no model-required final-delivery guard, so local fallback could own the best candidate.
- Runner rows did not carry `SprintResult.reason` and `error_codes`, so the report could only say `final_delivery_not_model_source`.
- Eligibility classification required semantic completion for local-delivery blocking, which missed the exact fail-closed case.

This is now corrected at runtime, row, and summary layers.

## Residual Debt

- `model-required-docs-001` still fails as `timeout_before_receipt`; that is a real pre-wall receipt problem, not a runner-overhead artifact.
- Repair wall is now cleanly visible as R/hyper model-call wall: `phase_wall_r_sec=78.1806`, `runner_overhead` no longer explains the bottleneck.
- Next work should optimize R/hyper itself: earlier stop, better semantic failure sensor, smaller prompt payload, and model-owned repair before local fallback.
