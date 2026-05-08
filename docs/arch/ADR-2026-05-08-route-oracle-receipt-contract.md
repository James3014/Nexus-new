# ADR-2026-05-08: Route Oracle Receipt Contract Must Override Cost Penalties

## Context

Route receipt smoke exposed three classes of failures that were easy to misread as model or benchmark failures:

- The runtime candidate factory replan path called `merge_runtime_learning_policy(repo_root)` without carrying `repo_root` into the helper.
- Route oracle expected receipt text was embedded as a bullet line, but the parser only handled a narrower format.
- Runtime learning and route-cost policy could demote explicitly required route-oracle capabilities such as `lancedb`, `semantic_searcher`, and `swarm_quiet_moment` before receipt generation.

In all failing rows, the task solved and verified successfully, but the expected capability was not public-safe because no receipt was emitted.

## Decision

Explicit `Nexus route oracle contract` expected capabilities are a diagnostic contract, not a normal optimization hint.

The planner must keep these expected capabilities selected even when learning policy or route-cost policy would otherwise penalize them. Cost tuning may still optimize normal route selection, but it must not erase a capability required by a route oracle receipt check.

## Consequences

- Receipt smoke failures now represent real runtime receipt gaps instead of planner demotion artifacts.
- Cost optimization remains valid for ordinary benchmark tasks.
- Future route-cost work should distinguish diagnostic/oracle contracts from production cost hints before applying penalties.

## Lesson

When a benchmark is measuring whether a capability can be invoked and evidenced, the route planner must treat the expected capability as fail-closed evidence scope. Otherwise the optimizer can falsely improve cost by removing the very thing being tested.
