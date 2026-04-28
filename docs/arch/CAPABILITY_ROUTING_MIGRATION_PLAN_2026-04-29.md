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

## 2026-04-29 P62 Learning Closure
- P62 Nexus-only full-capability smoke must use both `--timeout-sec` and
  `--per-task-stop-loss-sec`. The runner subprocess default can be 30s, which is
  too low once the planner selects heavier MSA capabilities.
- Capability coverage must distinguish `selected`, `invoked`, `evidence`,
  `gate`, and `outcome`. A selected capability is not public-safe until invoked
  evidence and gate evidence exist.
- Current P62 smoke showed CodeIntel, Hyper, Autoreason, and Ultra Review as
  public-safe. Swarm, Drone, and Nightshift were selected by planner signals but
  did not produce invoked/evidence/gate receipts, so they remain migration debt.
- DDTree was selected and gated only on the candidate-heavy row; public claims
  about DDTree must be scoped to eligible candidate-pool tasks.

## 2026-04-29 P63-P67 Foundation Update
- Added typed routing seams so future changes do not add more ad-hoc keyword
  branches:
  - `CapabilitySignalSet` normalizes task, route, CodeIntel, Memory/LanceDB, and
    skill candidate inputs.
  - `CapabilityConstraints` keeps MemPalace, Artifact, and Claim fail-closed
    constraints explicit.
  - `CapabilityExecutionPlan` and executor controls convert selected
    capabilities into execution-facing flags.
  - `CapabilityReceipt` and `SkillReceipt` define the selected/invoked/evidence/
    gate/outcome contract.
- `CapabilityRouter` is now a compatibility facade over the selector/planner
  path while preserving the legacy `capability_stack` schema.
- `build_route_executor_flags()` now derives Autoreason/DDTree controls from the
  selected plan instead of re-reading task keywords.
- Selected-only capabilities remain non-public-safe until a receipt proves
  invocation, evidence, and gate success.

## 2026-04-29 P68-P70 Receipt Report Update
- Benchmark coverage now prefers row-level `capability_receipts` /
  `capability_receipts_json` when present. Legacy inferred coverage remains only
  as a compatibility fallback for old reports.
- `research:auto-flow` usage traces now emit `capability_receipts` derived from
  the selected plan plus existing trace evidence.
- Autoreason, DDTree, Ultra Review, CodeIntel, Swarm, Drone, and Nightshift now
  have a shared selected/invoked/evidence/gate/outcome receipt projection.
- Selected-only MSA capabilities stay visible as selected but remain
  non-public-safe until executor evidence exists.

## 2026-04-29 P71-P73 Public Claim Gate Split
- Public benchmark reports now separate claim safety into four gates:
  performance, wearing, capability-specific, and cost.
- Capability-specific public claims require receipt-backed coverage
  (`source=capability_receipts`). Legacy inferred coverage can still be displayed,
  but it cannot pass the capability-specific public gate.
- Solve-rate improvement text remains governed by the performance/wearing public
  gate; capability value claims require the capability-specific gate.

## 2026-04-29 P74-P80 MSA Receipt Contract
- Swarm, Drone, and Nightshift now use the same receipt contract as CodeIntel,
  Autoreason, DDTree, and Ultra Review:
  - `selected`: planner chose the capability.
  - `invoked`: an execution trace proves it actually ran.
  - `evidence_present`: the executor produced a durable evidence reference.
  - `gate_passed`: the evidence passed its capability-specific acceptance check.
  - `failure_reason`: selected-only or partial execution remains visible and
    non-public-safe.
- Swarm evidence source is role finding / consensus evidence from candidate
  summaries. A selected Swarm capability without role findings is not claimable.
- Drone evidence source is delegated subtask artifacts or crystal count. A
  selected Drone capability without delegated artifacts is not claimable.
- Nightshift evidence source is report path plus recovered status. A
  recommended-but-not-invoked Nightshift path is explicitly marked as
  `recommended_without_invocation`.
- This keeps MSA honest during the migration: the router may select a capability
  aggressively, but public value claims require executor receipts.

## 2026-04-29 P81-P88 Benchmark Readiness Gate
- Gemini benchmarks must be run only after a Nexus-only routing smoke confirms:
  1. capability plan is emitted,
  2. capability receipts are emitted,
  3. selected/invoked/evidence/gate rates are visible,
  4. partial MSA capabilities have failure reasons,
  5. capability-specific public gate is receipt-backed.
- Trial/debug runs should use Nexus-only flows first. Gemini runs are reserved
  for evidence-grade comparison after the route and receipt contract are stable.
- If Autoreason or DDTree show no measurable execution contribution in
  Nexus-only smoke, improve executor evidence before spending Gemini quota.
- The target benchmark interpretation is:
  - performance claim: solve-rate / verified-delivery delta,
  - wearing claim: same model actually used Nexus context,
  - capability claim: receipt-backed capability contribution,
  - cost claim: wall time / token / model-call tradeoff.

## 2026-04-29 P89 Receipt Hygiene Lesson
- A Nexus-only smoke exposed that missing executor fields can accidentally look
  like evidence if `None` is stringified. Receipt refs must drop null/empty
  values before `evidence_present` is computed.
- `outcome_contributed` must mean the capability's own gate contributed to a
  verified outcome. A globally verified task must not make selected-only
  capabilities look contributory.

## Residual Debt
- Nightshift, Swarm, and Drone still need production-grade executor evidence
  before they can be counted as fully active capabilities.
- Planner is not yet the execution SSOT; it is the migration target.
- Benchmark/report layers consume `CapabilityReceipt` when available, but the
  old inference path remains for historical report compatibility.
- RLM still needs executor-level receipts before recursive loop claims can
  produce capability-specific public claims.
