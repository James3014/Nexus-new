# ADR-2026-05-08: Route Cost Measurement Lessons

## Status

Accepted

## Context

P86 route-cost tuning exposed two measurement traps while comparing Gemini Flash bare versus Gemini Flash wearing Nexus:

- Route smoke reported `research_route` as selected-not-invoked even though it is a planning diagnostic receipt, not an actionable runtime executor.
- Subprocess benchmark rows can include large wrapper overhead; one replay showed about 181 seconds wall time while the Nexus CLI reported about 3.5 seconds.

## Decision

- Route smoke over-selection hotspots must use the same actionable receipt policy as the report engine.
- Benchmark rows must mark `runner_overhead_polluted` when wrapper overhead dominates measured wall time.
- Cost tuning should use in-process or otherwise uncontaminated rows when judging actual Nexus route/runtime cost.

## Lessons

- A selected-only diagnostic receipt is not route waste unless the receipt is actionable.
- Forced local Hyper runs prove Nexus internal rescue value, but they do not prove model-uplift cost because they can use zero model calls.
- Flash wearing Nexus must be judged on same-model runs where the treatment arm actually calls the model and the runner overhead is not polluted.

## Verification

- `tests/ops/test_capability_route_smoke.py` covers actionable-only over-selection hotspots.
- `tests/benchmark/test_capability_ab_runner.py` covers polluted subprocess overhead detection.
