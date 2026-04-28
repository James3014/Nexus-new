# Capability Routing Migration Plan

## Status
Accepted

## Date
2026-04-29

## Context
Nexus is moving from preset routing toward a constrained capability space. The old
`CapabilityRouter` still feeds execution-facing fields such as `capability_stack`,
while the newer `CapabilityPlanner` models the full DAG: CodeIntel, Research,
Hyper, Nightshift, Swarm, Drone, Ultra Review, Autoreason, DDTree, and the
MemPalace, Artifact, and Claim gates.

During the migration, the main risk is semantic drift: the planner may select a
capability that the old router does not expose to execution, or an executor may
depend on manual environment flags instead of route decisions.

## Decision
Use `CapabilityPlanner` as the target SSOT for capability composition, but migrate
incrementally.

1. Short term: keep `CapabilityRouter` as a compatibility adapter, but make its
   activation semantics match the planner.
2. Medium term: route decisions must drive executor controls directly. Autoreason
   and DDTree are the first connected controls.
3. Long term: collapse `CapabilityRouter` into a thin wrapper over
   `CapabilityPlanner`, then remove duplicated activation logic.

## Migration Stages

### P0 Compatibility Alignment
- Keep existing `capability_stack` output stable.
- Mirror planner semantics for repair, governance, evidence, and trust signals.
- Add tests that compare expected capability activation across router, planner,
  and executor flags.

### P1 Executor Control
- Route decisions set `SprintConfig.enable_autoreason_executor`,
  `SprintConfig.enable_ddtree_executor`, and `SprintConfig.ddtree_max_candidates`.
- DDTree must have a real candidate pool when enabled; safe mode cannot stop at
  the first passing candidate before pruning is possible.
- Trace must prove effect with `eligible`, `selected_candidate_ids`, and
  `actual_saved_steps`.

### P2 Evidence Gate Integration
- Capabilities only count as active when their evidence outputs are present.
- Ultra Review must be recommended by the same governance/evidence signals used
  by the planner.
- CodeIntel scan and impact reports should be required for code-change gate pass.

### P3 Planner SSOT
- `CapabilityRouter.route()` becomes a compatibility facade over
  `CapabilityPlanner.plan()`.
- Duplicated keyword rules are removed from the old router.
- Benchmarks report planner selected capabilities as the primary routing result.

### P4 Removal
- Remove direct use of old router internals after reports and gates consume
  planner output.
- Keep a schema compatibility shim only if old reports still need
  `capability_stack`.

## Acceptance
- Nexus-only benchmark can run 12/12 with `semantic_verified_rate=1.0`.
- At least one candidate-heavy repair task shows DDTree `eligible=true` and
  `actual_saved_steps>0`.
- Governance and trust tasks recommend Ultra Review without manual flags.
- Gemini benchmark is only run after Nexus-only routing health passes.

## Residual Debt
- Nightshift, Swarm, and Drone still need production-grade executor evidence
  before they can be counted as fully active capabilities.
- Planner is not yet the execution SSOT; it is the migration target.
