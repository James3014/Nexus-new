# Nexus Route Cost P75 Launch Readiness

## Task

Bring the route-cost tuning loop to P75 with model-free preflight seams, same-model Flash/Pro evidence, and a launch readiness gate for the current public RLM harder benchmark slice.

## Result

P75 is launch-ready for the current fixed public task slice with one warning:

- Flash 8x2: PASS, same-model, Nexus verified 16/16 vs bare 11/16, trust mismatch 0.
- Pro 8x1: PASS, same-model, Nexus verified 8/8 vs bare 5/8, trust mismatch 0.
- Launch readiness gate: PASS.
- Warning: Pro wall cost ratio is 1.8078, slightly over the 1.8 launch target, while token ratio remains 1.1285.

## Engineering Changes

- Extracted shared cost evidence classification into `scripts/bench/cost_evidence_classifier.py`.
- Extracted benchmark eligibility classification into `scripts/bench/benchmark_eligibility.py`.
- Added route decision simulator and launch readiness gate in `scripts/bench/route_decision_simulator.py`.
- Added fixture-specific belief budget policy: `feature:rlm-belief-budget-hard-neutral-hardened-capped`.
- Added regression coverage in `tests/benchmark/test_route_decision_simulator.py`.

## Benchmark Evidence

| Run | Model | Nexus verified | Bare verified | Trust mismatch | Wall ratio | Median wall ratio | Token ratio | Gate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `.nexus/reports/flash_8x2_p72_policy_preflight` | Gemini 3 Flash | 16/16 | 11/16 | 0 | 1.6048 | 1.0480 | 1.1098 | PASS |
| `.nexus/reports/pro_8x1_p73_policy_preflight` | Gemini 3.1 Pro | 8/8 | 5/8 | 0 | 1.8078 | 1.2959 | 1.1285 | PASS |

## Gate Evidence

- `uv run pytest -q tests/benchmark/test_route_decision_simulator.py tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_route_cost_optimizer.py`: 165 passed.
- `uv run pytest -q tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_route_cost_optimizer.py tests/benchmark/test_route_decision_simulator.py tests/app/test_research_flow_service.py tests/engine/test_capability_receipt_adapters.py tests/nexus/codeintel/test_dci_locator.py`: 270 passed.
- `uv run python scripts/ops/nexus_pre_flash_gate.py --quick`: passed true.
- `.nexus/reports/p74_launch_readiness_gate.json`: passed true, 2 bundles checked, 1 warning.

## Residual Debt

- Pro wall ratio is just above target at 1.8078; it is not a gate failure because verified lift and token discipline are preserved, but it should be the next optimization target.
- Evidence-001 sometimes falls back from supervised bare to Nexus rescue; this is safe but costs an extra model call when bare fails.
- Belief budget is still the dominant wall-time hot spot even after removing the redundant failed baseline path.
