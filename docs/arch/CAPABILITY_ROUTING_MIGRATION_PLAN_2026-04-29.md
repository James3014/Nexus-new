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

## 2026-04-29 P90-P97 Routing Health Result
- P37 Nexus-only routing health ran 12 cross-module hard tasks with no Gemini:
  - with Nexus: solve rate 100%, semantic verified 100%, trust mismatch 0%.
  - service control: solve rate 100%, semantic verified 0%, trust mismatch 100%.
  - average wall time: Nexus 20.44s, service control 18.40s.
- Receipt-backed capability coverage:
  - CodeIntel: 12/12 selected, invoked, evidence, gate, public-safe.
  - Autoreason: 12/12 selected, invoked, evidence, gate, public-safe.
  - DDTree: 2/12 selected and public-safe, scoped to eligible candidate-pool rows.
  - Swarm: 4 selected, 0 invoked; all remain `selected_without_invocation`.
  - Drone: 5 selected, 0 invoked; all remain `selected_without_invocation`.
  - Nightshift: 5 selected, 0 invoked; all remain `selected_without_invocation`.
  - Ultra Review: 12 selected, 0 invoked because dry gate was not enabled in this
    routing-health command.
- Interpretation:
  - Nexus routing/reporting is now honest enough for benchmark preflight.
  - Public claims may use CodeIntel, Autoreason, and eligible DDTree evidence.
  - Public claims must not say Swarm, Drone, Nightshift, or Ultra Review improved
    the result until executor receipts exist.

## 2026-04-29 P98-P103 Ultra Review Dry Gate Result
- P38 initially exposed a runner wiring bug: `--enable-ultra-review-dry-gate`
  was only propagated to subprocess runs when LLM mode was enabled. No-LLM
  routing health therefore kept Ultra Review at `feature_flag_disabled`.
- The runner now passes `NEXUS_ULTRA_REVIEW_DRY_GATE=1` for subprocess Nexus
  treatment rows even when `--with-llm-mode off`.
- Verification smoke used 3 no-Gemini cross-module rows:
  - with Nexus: solve rate 100%, semantic verified 100%, trust mismatch 0%.
  - Ultra Review receipts: 3/3 selected, invoked, evidence, gate, public-safe.
  - average Nexus wall time: 22.63s.
- P39-P41 status:
  - Swarm/Drone/Nightshift still require production executor receipts.
  - The current benchmark path must keep them selected-only until a real
    `role_findings`, `subtask_artifact`, or `nightshift_report` receipt exists.
- P43 status:
  - Public reports already require `source=capability_receipts` for
    capability-specific claims.
  - Selected-only Swarm/Drone/Nightshift cannot pass the capability public gate.

## 2026-04-29 P104-P113 Adapter Refactor Result
- Receipt construction moved behind `capability_receipt_adapters.py`.
  `capability_receipts.py` is now a dispatcher instead of a growing capability
  branch table.
- Behavior-preserving checks passed for CodeIntel, Autoreason, DDTree, Ultra
  Review, Swarm, Drone, and Nightshift receipts.
- P49 no-Gemini routing health after the adapter refactor:
  - with Nexus: solve rate 100%, semantic verified 100%, trust mismatch 0%.
  - service control: solve rate 100%, semantic verified 0%, trust mismatch 100%.
  - public-safe receipts: CodeIntel 12/12, Autoreason 12/12, Ultra Review 12/12,
    DDTree 2/12 eligible rows.
  - selected-only receipts: Swarm 4, Drone 5, Nightshift 5.
- P53 report hardening:
  - Capability matrix now shows `Source` and `Failure reasons`.
  - Capability-specific public gate evaluates public capability nodes only:
    CodeIntel, Autoreason, DDTree, Ultra Review, Swarm, Drone, Nightshift.
  - Internal governance/routing nodes remain visible in the matrix but do not
    fail capability-specific public claims.
- Routing accuracy interpretation:
  - The router is accurate for selecting CodeIntel, Autoreason, Ultra Review,
    and eligible DDTree in the current benchmark path.
  - Swarm/Drone/Nightshift recommendations are plausible but not execution-
    accurate yet; they remain `selected_without_invocation` until executor
    receipts are connected.

## 2026-04-29 P7-P10 Route Decision Benchmark Readiness
- Benchmark rows now carry `route_decision` diagnostics from the same
  `CapabilityPlanner` path used by `research:auto-flow`. This makes public
  reports able to show selected, required, conditional, pending, forbidden, and
  pillar-active routing evidence instead of only legacy preset names.
- Added a capability coverage gap report so every registered capability is
  either ruled, reserved, or executor-pending. P8 caught that this check must be
  automated: a capability can otherwise exist in the registry without a routing
  migration status.
- P9 Nexus-only route diagnostics covered three lanes:
  - high-risk ability work selected CodeIntel, Research, Hyper, Ultra Review,
    Autoreason, DDTree, and MSA capabilities with Swarm/Drone/Nightshift marked
    pending.
  - governance/public-claim work selected evidence, MemPalace, Artifact, Claim,
    Research, Hyper, Autoreason, and learning gates.
  - low-risk documentation work stayed on baseline/direct mode while preserving
    mandatory delivery, MemPalace, Artifact, and Claim gates.
- P10 Gemini 3 Flash public benchmark preflight passed with hidden verifier,
  evidence bundle, and same-model lock enabled. The only warning was dirty
  worktree state, so formal Gemini runs must happen after commit or in a clean
  worktree.
- Changed-only L2 selected benchmark ops loop tests for this edit set. The
  integration smoke started a nested benchmark subprocess and was stopped after
  becoming quiet; use focused unit tests plus an explicit benchmark smoke for
  this path instead of letting changed-only own long benchmark execution.

## 2026-04-29 P12 Receipt Source Lesson
- Direct Codex-with-Nexus runs bypass the CLI/service auto-flow receipt path, so
  they must build `capability_receipts` explicitly before report extraction.
  Otherwise public reports fall back to legacy inferred coverage and fail the
  capability-specific public gate with `receipt_source_missing`.
- Prompt-delivered executor flags are not the same as executor evidence.
  Autoreason, DDTree, and Ultra Review may be selected by the route decision,
  but public capability claims still require winner/judge evidence, real
  candidate pruning evidence, or Ultra Review report evidence.
- DDTree receipts must not treat missing candidate counts as invocation. A
  pruning receipt is invoked only when `candidate_count > max_candidates > 0`,
  and public-safe only when saved-step evidence exists.

## 2026-04-29 P54-P58 Pending Executor Result
- Planner now exposes `pending_capabilities` for beta collaboration abilities
  that can be recommended but do not yet have production executor receipts in
  the benchmark path: Swarm, Drone, and Nightshift.
- Receipt/report behavior:
  - Pending executor capabilities remain visible in the capability plan.
  - They are emitted as `selected=false` with `failure_reason=pending_executor`
    until real executor evidence is present.
  - This prevents selected-only recommendations from inflating capability
    coverage or public capability claims.
- P55-P57 executor check:
  - Swarm has existing role-finding/consensus plumbing through hyper sprint
    candidate summaries, but no standalone public-safe executor report.
  - Drone has crystal artifacts under `.nexus/reports/drones/`, but needs a
    stable subtask receipt schema before it can be claimed as production active.
  - Nightshift has a direct runner/report path, but no-Gemini benchmark fixtures
    cannot trigger a true Nightshift recovery; they can only test field plumbing.
- P58 no-Gemini routing health ran 12 cross-module hard tasks:
  - with Nexus: solve rate 100%, semantic verified 100%, trust mismatch 0%.
  - service control: solve rate 100%, semantic verified 0%, trust mismatch 100%.
  - average wall time: Nexus 41.19s, service control 25.01s.
  - public-safe receipts: CodeIntel 12/12, Autoreason 12/12, Ultra Review 12/12,
    DDTree 2/12 eligible rows.
  - pending executor receipts: Swarm 4, Drone 5, Nightshift 5.
- Interpretation:
  - The new router is now more honest: it can recommend collaboration/escalation
    abilities without letting them masquerade as executed capabilities.
  - The route is public-safe for CodeIntel, Autoreason, eligible DDTree, and
    Ultra Review in this no-Gemini preflight.
  - Swarm/Drone/Nightshift must remain pending until P59-P61 connects stable
    executor evidence.

## 2026-04-29 P59-P61 Receipt Schema Result
- Swarm/Drone/Nightshift now have stable receipt payload schemas inside
  `nexus_usage_trace.capabilities`:
  - `swarm_report`: `nexus_swarm_receipt_v1`, derived from hyper sprint
    candidate summaries with evidence refs and consensus.
  - `drone_report`: `nexus_drone_receipt_v1`, derived from drone crystal paths
    with artifact count and artifact paths.
  - `nightshift_report`: `nexus_nightshift_receipt_v1`, separating recommended,
    invoked, recovered, report path, and failure reason.
- Receipt adapters now prefer these structured report payloads while preserving
  legacy fields for compatibility.
- Benchmark rows expose audit fields for public report diagnostics:
  - `capability_swarm_report_schema_version`
  - `capability_swarm_consensus`
  - `capability_drone_report_schema_version`
  - `capability_drone_artifact_path`
  - `capability_nightshift_report_schema_version`
  - `capability_nightshift_failure_reason`
- This is not a full production executor rollout yet. It makes the evidence
  contract stable so P62 can safely connect true executor reports without
  another report-format rewrite.

## 2026-04-29 P16-P19 Cost and Truthfulness Lesson
- Forced `hyper_sprint` benchmark rows must not pay for a baseline probe first.
  The route can still use verification-only rescue for cross-module tasks, but
  the forced path should be a direct hyper execution path.
- `NEXUS_LLM_CANDIDATE_CAP` is a hard benchmark budget. Planner-selected DDTree
  may remain enabled, but it must not silently raise the LLM candidate count
  above the cap.
- Gemini/Nexus benchmark runs now default LLM self-heal to off. Extra repair
  calls are useful for product quality experiments, but public A/B comparisons
  must opt in explicitly with `--enable-llm-self-heal`.
- Public capability claims must be receipt-backed:
  - Autoreason disabled/prompt-only payloads are not invoked evidence.
  - DDTree selected candidate IDs are diagnostics unless `actual_saved_steps>0`.
  - Ultra Review cannot contribute to a verified outcome without report
    evidence.
  - Legacy inferred coverage for receipt-required capabilities is marked
    `legacy_untrusted`, so it cannot pass the capability-specific public gate.

## 2026-04-29 P22-P24 Direct Codex Receipt Lesson
- Direct Codex-with-Nexus is a prompt/context wearing path, not the same as
  running every Nexus executor. Prompt-delivered executor flags must not become
  invocation receipts.
- In the direct Codex path:
  - Autoreason is `PROMPT_ONLY` unless a real judge result with winner/evidence
    exists.
  - DDTree remains diagnostic unless a real pruning executor reports
    `actual_saved_steps>0`.
  - Ultra Review remains not invoked unless a dry/live review report path exists.
- Public reports must prefer `capability_receipts` over legacy booleans. Legacy
  fields like `ultra_review_invoked=true` cannot override an incomplete receipt.
- This keeps Codex self-benchmark useful for route/value tuning while preventing
  capability-specific public claims from overstating which Nexus abilities
  actually executed.

## 2026-04-29 P25-P39 Benchmark Readiness Gate Lesson
- Public Gemini benchmarks must not start just because a task manifest and model
  lock are valid. They also need Nexus capability readiness:
  - core capability registry nodes are present,
  - the Nexus arm uses the subprocess `research:auto-flow` path,
  - Autoreason and DDTree executor flags are enabled,
  - `llm_candidate_cap>=3` so DDTree can actually prune,
  - Ultra Review dry gate is enabled for high-risk rows.
- Direct Codex remains useful for self-benchmarking route value, but external
  model claims should use the subprocess Nexus path so executor receipts can be
  produced by the actual Nexus services.
- Added preflight capability readiness so Gemini runs can fail before spending
  quota when the planned comparison would only produce selected/prompt-only
  capability evidence.

## 2026-04-29 P40-P41 Local Executor Smoke Lesson
- Failure lesson:
  - The benchmark runner originally passed Autoreason/DDTree executor flags only
    when `with_llm_mode` enabled a model call. That blocked local-only P40
    validation from proving real executor receipts before Gemini spending.
  - P41 route smoke showed another important distinction: `auto` routing can
    correctly keep easy/medium tasks in light baseline lanes, so selected
    Autoreason/DDTree capabilities may remain non-invoked there. Executor proof
    needs a forced/high-risk hyper lane, while route-tier smoke needs `auto`.
- Fix:
  - `NEXUS_AUTOREASON_EXECUTOR`, `NEXUS_DDTREE_EXECUTOR`, and
    `NEXUS_LLM_CANDIDATE_CAP` are now passed to the Nexus subprocess even when
    the treatment arm is local-only.
- Evidence:
  - P40 forced-hyper local smoke produced public-safe receipts for CodeIntel,
    Autoreason, DDTree, and Ultra Review without calling Gemini.
  - P41 auto route smoke produced both light and full tiers without calling
    Gemini, but also exposed that local-only subprocess overhead is still about
    75-78 seconds per row while phase timings account for only about 8-11
    seconds.

## 2026-04-30 P42-P43 Nexus-Only Timing Lesson
- Failure lesson:
  - Single-arm route tuning is useful before spending Gemini quota, but it must
    be labeled as `nexus_only` and must fail the public A/B claim gate. A run
    without a bare/control arm can prove Nexus route receipts and wall-time
    behavior, but it cannot prove uplift.
  - The first P43 smoke showed `with_nexus` average wall time around 69.39s
    while measured phase time was only around 7.49s. Without child timing
    breakdowns, that gap could be misattributed to Gemini, routing quality, or
    executor logic.
- Fix:
  - Added benchmark `--nexus-only` for route/timing smoke. It skips the bare
    arm, records `nexus_only=true`, and marks evidence bundles as
    `single_arm_run` so public claims stay blocked.
  - Added service-level `timing.breakdown_sec` for target IO, CodeIntel, and
    context packing, then surfaced those fields in benchmark rows.
- Evidence:
  - P43 local smoke executed 3 Nexus rows, 0 bare rows, solved 3/3, and
    correctly failed comparable public A/B gating as a single-arm run.
  - Targeted timing/gate tests and the route/executor slice passed with
    `175 passed`.
- Next:
  - Re-run a 1-task Nexus-only timing probe with the new breakdown before any
    Gemini run. If CodeIntel or another phase-adjacent step dominates the gap,
    optimize that path first; Gemini benchmarks should start only after the
    Nexus route overhead is understood.

## 2026-04-30 P42b CodeIntel Scan Cost Lesson
- Failure lesson:
  - The timing probe showed CodeIntel dominated local-only Nexus wall time:
    `timing_codeintel_sec` was about 60.55s on a single easy fixture. The
    graph builder used `Path.rglob("*.py")`, which filtered ignored paths only
    after traversal, so ignored worktree/cache directories were still walked.
  - Import matching also scanned the full module set per import. That was less
    severe than directory traversal, but it made the graph builder less
    scalable as Nexus grows.
- Fix:
  - Replaced recursive globbing with pruned `os.walk` traversal so ignored
    directories are not entered.
  - Added indexed module matching for imports while preserving existing
    deepest-match behavior.
- Evidence:
  - Direct CodeIntel scan on this repo dropped to about 2.46s for 1454 nodes.
  - The same 1-task Nexus-only benchmark probe dropped from 68.33s wall /
    60.55s CodeIntel to 11.92s wall / 3.92s CodeIntel.
- Next:
  - Flash/Pro benchmark runs may proceed only after route smoke stays under the
    stop-loss threshold. If larger tasks still show CodeIntel as dominant, add
    cached graph reuse before expanding to full public-candidate runs.

## 2026-04-30 P44 Flash Smoke Route Lesson
- Failure lesson:
  - A Flash smoke exposed an old benchmark shortcut: `with_llm_mode=all`
    silently forced `--force-flow hyper_sprint` when no explicit flow was set.
    That makes the test measure a legacy preset instead of the new capability
    router's decision.
  - Easy/medium tasks whose route recommendation was `baseline` were therefore
    upgraded to hyper, increasing wall time and hiding whether the intelligent
    route was actually correct.
- Fix:
  - Removed the implicit `with_llm_mode=all -> hyper_sprint` override. The
    runner now preserves auto routing unless a caller explicitly passes
    `--force-flow`.
- Evidence:
  - The regression test now asserts that LLM-enabled Nexus runs keep
    `--llm-mode` but do not add `--force-flow` when no force flow is requested.
- Next:
  - Re-run Flash smoke before P45. Public benchmark expansion is blocked until
    row-level evidence shows the selected flow matches the route decision and
    Nexus delivery remains valid.

## 2026-04-30 P44b Nexus-Wearing Baseline Lesson
- Failure lesson:
  - Preserving auto routing fixed the old hyper preset problem, but it exposed
    a second benchmark contract issue: baseline lanes could solve locally with
    `model_calls=0`, making the run fast but invalid for a "Gemini wearing
    Nexus" comparison.
  - LLM baseline fallback originally dropped metadata when Gemini returned a
    structurally invalid patch. That hid real model invocation and made rows
    look like Nexus had not called Gemini.
- Fix:
  - Benchmark LLM treatment runs now pass `--llm-baseline` while still
    preserving auto route selection.
  - Baseline generation now preserves LLM metadata on fallback, including
    model calls, model name, token status, and gateway category.
  - MemPalace is marked active for LLM baseline paths, so five-pillar
    observation does not depend on Hyper-only learning trace.
- Evidence:
  - Targeted tests pass and the route/app/codeintel slice passed with
    `166 passed`.
  - Flash smoke remains blocked for public expansion because medium/hard rows
    revealed baseline LLM quality and timeout issues. That is a capability
    problem to fix, not infra evidence to hide.
- Next:
  - Add a conservative escalation rule: when an LLM baseline attempt fails
    tests or times out on medium/hard tasks, re-plan into Hyper/Autoreason
    within the same Nexus run. Do not globally force Hyper for all LLM tasks.

## 2026-04-30 P44c Baseline Failure Replan Lesson
- Failure lesson:
  - Letting baseline use Gemini fixed the wearing contract, but medium rows
    showed a new quality gap: an LLM baseline patch can be syntactically
    delivered and still fail tests. Treating that as final loses Nexus's
    self-healing value.
- Fix:
  - When auto routing selects baseline, LLM baseline was attempted, and tests
    fail, Nexus now replans to Hyper/Autoreason in the same run. Explicit
    `--force-flow baseline` remains respected.
- Evidence:
  - Added a regression test where Gemini baseline returns a bad patch, tests
    fail, and Nexus escalates to Hyper to produce a verified patch.
- Next:
  - Re-run Flash smoke with lower gateway timeout and verify medium/hard rows
    become eligible capability outcomes rather than delivery-invalid records.

## Residual Debt
- Nightshift, Swarm, and Drone still need production-grade executor evidence
  before they can be counted as fully active capabilities.
- Planner is not yet the execution SSOT; it is the migration target.
- Benchmark/report layers consume `CapabilityReceipt` when available, but the
  old inference path remains for historical report compatibility.
- RLM still needs executor-level receipts before recursive loop claims can
  produce capability-specific public claims.

## 2026-04-29 P2 RouteDecision Adapter Lesson
- Failure lesson:
  - Do not expose full capability state by adding new fields to the legacy
    `capability_stack` facade. That stack is a compatibility output for old
    execution/report paths; adding full composition there risks benchmark drift
    and downstream schema surprise.
  - Full required/conditional/optional/pending/forbidden state belongs in the
    `RouteDecision` contract, produced from `CapabilityPlan` by an adapter.
- Fix:
  - Added `route_decision_adapter.build_route_decision(...)`.
  - It converts `CapabilityPlan` plus executor controls into
    `RouteDecision(schema_version=nexus_route_decision_v1)`.
  - Legacy `CapabilityRouter` keeps its old compact output.
- Next:
  - Wire route decision reports as a parallel diagnostic artifact first.
  - Only after reports/gates consume `RouteDecision` should execution migrate
    away from the compact legacy `capability_stack`.

## 2026-04-29 P3-P6 Route Diagnostic Lesson
- Failure lesson:
  - New planner rules must define shared text state before capability branches.
    Adding `research_control_plane` before `task_lower` existed caused a broad
    `UnboundLocalError` across planner and CLI route tests.
  - Changed-only surfaced two unrelated unstable tests: acceptance cold-start
    wrote fixtures in the isolated cwd while the CLI read `repo_root`, and learn
    refresh due-date fixtures crossed the 2026-04-29 calendar boundary.
- Fix:
  - Added opt-in `research:route --route-decision-report` diagnostic output.
  - Added `pillar_signals` summary to `RouteDecision.signal_snapshot`.
  - Added planner rules for `repair_loop`, `acceptance_check`,
    `forecast_gate`, `xray`, and `research_control_plane`.
  - Kept `learn_scheduler` and `autonomic_router` reserved until scheduler
    freshness signals and planner-SSOT migration are clearer.
