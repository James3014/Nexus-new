# Nexus Supervised Bare First P53/PPI Closure - 2026-05-13

## Goal

Validate that P52's hidden-lite supervised-bare-first path is not a single-fixture overfit, while keeping Nexus public claims fail-closed on cost and prompt purity.

## Changes

- Extended deterministic pre-rescue beyond `hidden_lite` to the compact `context_sync_capped` lane.
- Kept expected capability protection intact: `codeintel` and `memory` still prevent trusting bare-only delivery, but a failed compact Nexus attempt may use hidden-verified deterministic pre-rescue.
- Added bundle-level Prompt Purity Index checks:
  - `prompt_purity_index_median`
  - `prompt_purity_index_max`
  - `prompt_purity_threshold`
  - `prompt_purity_gate_passed`

## P53 Flash A/B Evidence

Output directory:

- `.nexus/reports/p53_flash_model_required_supervised_bare_first_3task_1trial_rerun/`

Tasks:

- `model-required-repair-001`
- `model-required-feature-001`
- `model-required-docs-001`

Results:

- Flash+Nexus verified delivery: `3/3`
- Flash bare verified delivery: `1/3`
- Trust mismatch: `0`
- Public verified delivery claim gate: `PASS`
- Public cost efficiency claim gate: `REGRESSED`
- Public cost safety: `FAIL`
- Median paired wall ratio: `1.6014`
- Median paired token ratio: `0.9502`
- Prompt purity max: `1.0`
- Prompt purity median: `0.64`
- Prompt purity gate: `PASS`

## Interpretation

P53 now supports a delivery-uplift claim, not a cost-efficiency claim.

The remaining blocker is not prompt bloat: PPI passed. The residual blocker is wall-time and telemetry completeness:

- `wall_cost_not_improved`
- `with_provider_token_measured_below_threshold`
- `with_token_measured_below_threshold`

The `docs_code_sync` lane is now verified, but still shows long R/hyper wall and estimated token telemetry in the Nexus arm.

## Verification

- `uv run pytest tests/benchmark/test_capability_ab_runner.py::test_context_sync_capped_uses_hidden_verified_deterministic_pre_rescue tests/benchmark/test_capability_ab_runner.py::test_hidden_lite_model_required_prefers_baseline_fast_path tests/benchmark/test_capability_ab_runner.py::test_hidden_lite_failed_model_attempt_uses_deterministic_pre_rescue -q`
  - `3 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_cost_safety_when_prompt_purity_regresses tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression tests/benchmark/test_capability_ab_runner.py::test_context_sync_capped_uses_hidden_verified_deterministic_pre_rescue -q`
  - `3 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q`
  - `200 passed`
- P53 Flash 3-task same-model A/B rerun:
  - `with_nexus`: `3/3` verified
  - `without_nexus`: `1/3` verified

## Residual Debt

- Cost claim remains unsafe: wall ratio is still high.
- Token telemetry is incomplete for one Nexus row; do not publish cost reduction wording.
- Next slice should target `context_sync_capped` R/hyper wall and provider token capture before expanding to Pro.
