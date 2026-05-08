# ADR-2026-05-08: Route Cost Measurement Lessons

## Status

Accepted

## Context

P86 route-cost tuning exposed two measurement traps while comparing Gemini Flash bare versus Gemini Flash wearing Nexus:

- Route smoke reported `research_route` as selected-not-invoked even though it is a planning diagnostic receipt, not an actionable runtime executor.
- Subprocess benchmark rows can include large wrapper overhead; one replay showed about 181 seconds wall time while the Nexus CLI reported about 3.5 seconds.
- In-process benchmark rows removed wrapper overhead, but the hidden-verifier retry path was accidentally subprocess-only. That made cost-clean runs understate Nexus rescue ability when a hidden contract failure required bounded self-heal.

## Decision

- Route smoke over-selection hotspots must use the same actionable receipt policy as the report engine.
- Benchmark rows must mark `runner_overhead_polluted` when wrapper overhead dominates measured wall time.
- Route cost optimizer promotion must hold polluted rows instead of drafting promoted policy from contaminated cost evidence.
- Cost tuning should use in-process or otherwise uncontaminated rows when judging actual Nexus route/runtime cost.
- Hidden-verifier retry must work in both subprocess and in-process runner modes; changing measurement transport must not disable the repair loop being measured.

## Lessons

- A selected-only diagnostic receipt is not route waste unless the receipt is actionable.
- Forced local Hyper runs prove Nexus internal rescue value, but they do not prove model-uplift cost because they can use zero model calls.
- Flash wearing Nexus must be judged on same-model runs where the treatment arm actually calls the model and the runner overhead is not polluted.
- A cost policy artifact is only safe when its source rows are verified and uncontaminated; polluted rows are diagnosis inputs, not promotion inputs.
- A verified in-process retry row proves Nexus can rescue a hidden verifier failure, but if it is solved by local preflight or has missing provider token evidence, it must remain hold-only and cannot be promoted as public model-cost improvement.

## Verification

- `tests/ops/test_capability_route_smoke.py` covers actionable-only over-selection hotspots.
- `tests/benchmark/test_capability_ab_runner.py` covers polluted subprocess overhead detection.
- `tests/benchmark/test_route_cost_optimizer.py` covers polluted row hold behavior and cost truth table output.
