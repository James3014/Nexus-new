# Nexus Capability Invocation + Cost Guard P30

## Goal

Ensure the new route calls required capabilities without leaving any expected capability unused, then reduce benchmark cost pollution without weakening receipt/evidence gates.

## P21-P30 Result

- Capability invocation gate: PASS.
- Full deterministic route smoke: PASS.
- Flash cost guard: PARTIAL PASS.
- Pro hidden-retry cost guard: PASS.
- Final model solve gate: NOT CLOSED. The remaining failures are patch-quality/model-output issues, not missing capability wiring.

## Implemented Changes

1. Added `expected_capability_invocation_coverage` to benchmark rows.
   - Purpose: separate selected/invoked/evidence from public-safe outcome.
2. Added `NEXUS_CAPABILITY_RECEIPT_FIRST=1` receipt-first probe mode.
   - Purpose: prove executor/receipt seam before expensive model solve.
3. Protected expected capability oracle tasks from cost policy pruning.
   - Preserves candidate count for `autoreason` / `ddtree`.
   - Disables `supervised_bare_first` for expected capability oracle rows because bare cannot invoke Nexus capabilities.
   - Does not force `--llm-baseline`; candidate factory is preserved without reopening unnecessary model baseline calls.
4. Added `NEXUS_BENCH_DISABLE_HIDDEN_RETRY=1`.
   - Purpose: route/receipt oracle benchmarks can fail closed without spending hidden retry budget.
5. Added split cost fields for supervised bare rescue.
   - `nexus_subprocess_tokens`
   - `nexus_subprocess_model_calls`
   - `combined_tokens`
   - `combined_model_calls`

## Benchmark Evidence

### Flash+Nexus `route-oracle-autoreason-001`

| Run | Invocation | Public-safe | Solve | Tokens | Calls | R phase | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| P20 baseline | PASS | FAIL | FAIL | 202027 | 4 | 154.7367s | included failed supervised bare-first + Nexus rescue |
| P30 v3 | PASS | FAIL | FAIL | 147382 | 3 | 148.1589s | supervised bare disabled |
| P30 v4 | PASS | FAIL | FAIL | 148495 | 3 | 134.0146s | supervised bare disabled, llm baseline not forced |

Flash cost delta:

- Calls: `4 -> 3`
- Tokens: `202027 -> 148495` (~26.5% lower)
- R phase: `154.7367s -> 134.0146s` (~13.4% lower)
- Remaining cost source: `run_hyper_sprint()` model candidate/self-heal path.

Evidence:

- `.nexus/reports/p20_flash_receipt_first_autoreason_240s/with_nexus_1778389718.jsonl`
- `.nexus/reports/p30_flash_receipt_first_autoreason_v3/with_nexus_1778420823.jsonl`
- `.nexus/reports/p30_flash_receipt_first_autoreason_v4/with_nexus_1778421560.jsonl`

### Pro+Nexus `route-oracle-autoreason-001`

| Run | Invocation | Public-safe | Solve | Tokens | Calls | Hidden retry | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| P20 baseline | PASS | PASS | FAIL | 85695 | 2 | 156.1815s | retry attempted after hidden verifier failure |
| P30 no-retry | PASS | PASS | FAIL | 44862 | 1 | 0.0s | fail-closed without retry |

Pro cost delta:

- Calls: `2 -> 1`
- Tokens: `85695 -> 44862` (~47.7% lower)
- Hidden retry: `156.1815s -> 0.0s`

Evidence:

- `.nexus/reports/p20_pro_receipt_first_autoreason/with_nexus_1778389228.jsonl`
- `.nexus/reports/p30_pro_receipt_first_autoreason_no_retry/with_nexus_1778421046.jsonl`

## Root Cause Findings

### Flash

Primary cost source is not missing route wiring.

- `R phase` is dominated by `run_hyper_sprint()`.
- P20 token total was polluted by failed supervised bare-first tokens.
- After disabling supervised bare for capability oracle tasks, calls dropped from 4 to 3.

### Pro

Primary failure is patch quality.

- `autoreason` was selected/invoked and public-safe.
- Hidden verifier rejected the patch because it selected a candidate with missing evidence / failed status.
- The next repair should improve candidate-selection logic or the model prompt, not route selection.

## Full Route Smoke

Command:

```bash
uv run python scripts/ops/capability_route_smoke.py
```

Result: PASS.

Summary: `.nexus/reports/capability_route_smoke_summary.json`

Coverage:

- `route_oracles`: 8/8 expected capabilities public-safe.
- `codeintel_hyper`: 4/4 public-safe.
- `core_governance_gates`: 3/3 public-safe.
- `belief_gate`: 1/1 public-safe.
- `runtime_receipt_oracles`: 2/2 public-safe.

Route quality from latest full smoke:

- `route_oracles`: selected->invoked `0.9848`, invoked->evidence `1.0`, evidence->outcome `1.0`, unnecessary selected `0.0152`.
- Other suites: selected->invoked `1.0`, invoked->evidence `1.0`, evidence->outcome `1.0`, unnecessary selected `0.0`.

## Verification Commands

```bash
uv run pytest -q \
  tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_preserves_expected_autoreason_over_cost_cap \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_retry_can_be_disabled_for_receipt_oracle \
  tests/benchmark/test_capability_ab_runner.py::test_supervised_bare_failure_on_lite_route_skips_second_strict_model_call \
  tests/benchmark/test_capability_ab_runner.py::test_expected_capability_invocation_coverage_tracks_call_without_outcome
```

Result: `4 passed`.

```bash
uv run pytest -q \
  tests/engine/test_capability_wiring_audit.py \
  tests/engine/test_capability_receipt_adapters.py \
  tests/engine/test_capability_routing_contracts.py \
  tests/engine/test_capability_planner.py
```

Result: `102 passed`.

```bash
uv run python scripts/ops/capability_route_smoke.py --print-only
uv run python scripts/ops/capability_route_smoke.py
```

Result: both PASS.

## Residual Debt

1. Flash still costs too much for route-oracle model solve. Remaining work is inside `run_hyper_sprint()` LLM candidate/self-heal path.
2. Pro still fails hidden semantic verification. Remaining work is candidate-selection logic/prompt quality, not capability invocation.
3. Do not make a public improvement claim from this run. It is a route/receipt/cost diagnostic, not same-model public A/B proof.
