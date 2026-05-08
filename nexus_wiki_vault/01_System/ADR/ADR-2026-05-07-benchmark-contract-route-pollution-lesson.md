---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-07 Benchmark Contract Route Pollution Lesson

## Context

The always-on Gemini benchmark appends a `Nexus wearing contract` block to each task and loads task types as:

- `public_bugfix`
- `public_test_repair`
- `public_refactor`

At the same time, the benchmark enables:

- `--llm-candidate-cap 3`
- low initial confidence assumptions inside the route/runtime path

This combination caused hidden and repair tasks to be interpreted as high-ambiguity routes, which then auto-opened:

- `research`
- and, for repair, higher-cost governance lanes through routing tier escalation

## Finding

There were two coupled route pollution sources:

1. route pre-classification read the full task text instead of the task body, so benchmark contract suffixes could influence policy
2. fast-path rules matched local task labels like `bugfix` / `test_repair`, but the runtime benchmark path emitted `public_bugfix` / `public_test_repair`

That meant a local replay could look fixed while the real benchmark path still over-opened capability lanes.

## Decision

For always-on benchmark tasks:

1. strip the `Nexus wearing contract` suffix before route pre-classification
2. normalize `public_*` task types back to their base task family when evaluating:
   - hidden fast paths
   - bounded repair no-research paths
3. cap risk for benchmark hidden / bounded repair fast paths before routing tier escalation

## Consequence

This keeps:

- hidden tasks on the lighter lane
- bounded repair tasks on hyper/repair without unnecessary research
- governance tasks on the hardened lane

without weakening the core fail-closed gates.
