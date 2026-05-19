# Nexus Optimization Plan: Context, Learning, Data, Harness

Status: `PLAN_READY`
Date: `2026-05-19`
Source docs:
- `docs/plans/CONTEXT_ENGINEERING_SYNC.md`
- `docs/plans/NEXUS_LEARNING_SYNC_MASTER.md`
- `docs/plans/DATA_ENGINEERING_BOOK_SYNC.md`
- `docs/plans/HARNESS_100_SYNC.md`

## 0. Single Exit

This plan is complete when Nexus has a small, testable optimization path that:

- keeps context assembly, retrieval, learning writeback, route planning, skill-fit, and public benchmark gates as separate seams;
- reduces repeated context/index/route work without weakening verified capability coverage;
- turns every optimization claim into a receipt-backed measurement;
- preserves public-promotion boundaries: internal SF, route, and harness evidence cannot directly become public claims.

Non-goals:

- no big-bang ContextHub rewrite;
- no `.specify` initialization while the worktree is dirty;
- no runtime skill default changes without a separate SF apply gate;
- no public benchmark unlock from internal smoke or single-arm evidence.
- no route/context/harness optimization bypasses AutonomicRouter hardening, CompletionEnvelope closeout, HallucinationGuard, Mutation Assurance, or BDD harness preflight gates.

## 1. Clean Code / Linus Framing

Engineering rules for all task cards:

- prefer one deep seam over many shallow helper modules;
- isolate policy, data collection, and claim decisions;
- make bad states impossible or fail-closed rather than patching symptoms;
- add adapters only after there are at least two callers or two implementations;
- keep row-level evidence as the source of truth, not markdown summaries;
- validate each slice with focused tests before expanding scope.

Deletion test:

- if deleting a module only moves the same conditionals into callers, it is not deep enough;
- if deleting a module would scatter budget, receipt, retry, or claim rules across several files, the module is earning its keep.

## 2. Current Nexus Seams

Observed implementation surface:

- context / memory: `nexus/core/context_hub.py`, `nexus/core/context_compactor.py`, `nexus/core/memory_coordinator.py`, `nexus/services/memory_repository.py`, `nexus/services/memory_indexer.py`;
- route / planning: `nexus/engine/capability_planner.py`, `nexus/app/research_flow_service.py`, `nexus/engine/harness_route_policy.py`, `nexus/engine/route_tier_policy.py`;
- skill-fit: `nexus/learning/skill_fit_ablation.py`, `nexus/learning/skill_fit_ablation_core.py`, `nexus/learning/skill_discovery_lane.py`, `nexus/learning/skill_catalog.py`;
- benchmark / evidence: `scripts/bench/capability_ab_runner.py`, `scripts/bench/route_execution_policy.py`, `scripts/bench/taskset_contract.py`, `scripts/bench/public_lane_contract.py`;
- learning data: `nexus/research/learn/*`, `scripts/ops/build_autodata_manifest_from_benchmark.py`, `scripts/bench/export_benchmark_learning_ledgers.py`;
- delivery gates: `nexus/delivery/gate.py`, `nexus/delivery/evidence_verifier.py`, `nexus/delivery/report_claims.py`.

Primary friction:

- context budgeting, retrieval, and compaction are not yet a single audited context contract;
- route planning and benchmark runner both know about capability evidence and cost gates;
- learning data artifacts are rich but not normalized into a stable data-quality flywheel;
- skill-fit discovery, runtime apply, and public benchmark are now better separated, but need an ongoing intake/replace lifecycle;
- generated reports make the workspace noisy, so evidence retention needs lifecycle automation.

## 3. Milestone Roadmap

### M0: Optimization Contract Freeze

Goal: define the evidence and claim boundary before editing runtime code.

Task cards:

- `OPT-M0-A`: write a compact optimization contract covering context, learning, harness, SF, and benchmark boundaries.
- `OPT-M0-B`: add an artifact naming/retention rule for generated optimization reports.
- `OPT-M0-C`: add a plan-readiness checklist: dirty worktree, public-claim gate, SF apply gate, provider-token gate.

Exit:

- one plan file and one future implementation checklist;
- no runtime behavior changed.

Validation:

- markdown exists;
- paths referenced are under `docs/`, `scripts/ops/`, `nexus/`, or test paths.

### G0: Existing Hard Gate Compatibility

Goal: prove the optimization lane stays compatible with Nexus hard gates before deeper route/context/harness changes.

Task cards:

- `OPT-G0-A`: add a hardened-router compatibility check for route DAG artifacts, including `NEXUS_ROUTING_V4_HARDENED`, MFP threshold metadata, and router acceptance status.
- `OPT-G0-B`: add CompletionEnvelope awareness to claim/evidence closeout read models through `completion_envelope_ref` or explicit `completion_status`.
- `OPT-G0-C`: add HallucinationGuard forecast fields to context assembly receipts so source drops cannot create silent evidence gaps.
- `OPT-G0-D`: add a mutation assurance pregate for high-risk or public-claim-affecting optimization changes.
- `OPT-G0-E`: add BDD harness preflight sensor consumption before route DAG acceptance.
- `OPT-G0-F`: add a capability-contract rescue guard so `required` protected capabilities cannot receive pre-model deterministic rescue nodes.
- `OPT-G0-G`: add a skill-tier quarantine guard before context assembly or runtime/public route tests can consume skill content.
- `OPT-G0-H`: add a research supply gap guard that blocks live benchmark escalation unless using diagnostic-only local mock receipts.
- `OPT-G0-I`: add an AutonomicRouter-forward DAG guard that serializes forced-swarm nodes before static parallel planning.

Exit:

- every route/context/harness optimization artifact can state whether it is compatible with existing hard gates;
- no G0 check unlocks runtime default apply or public benchmark claims.

Validation:

- focused tests for hardened-router/MFP metadata, completion envelope requirement, hallucination-risk blockers, mutation assurance requirement, and BDD preflight escalation.

Stop conditions:

- route DAG output assumes planner intent is enough to pass hardened routing;
- closeout/read-model output omits CompletionEnvelope state;
- context slimming drops claim/evidence sources without replacement evidence refs;
- high-risk changes skip deterministic mutation assurance;
- BDD-required tasks proceed without `bdd_acceptance_skill`.
- required protected capabilities receive pre-model rescue fallbacks;
- quarantined or uncurated skills enter prompt/runtime/public context;
- live 7R-style benchmark is requested while research supply gap is unresolved;
- static DAG parallelism ignores an AutonomicRouter forced-swarm pre-route.

### M1: Context Assembly Contract

Goal: make ContextHub assembly budgeted, dependency-injected, and auditable.

Task cards:

- `OPT-M1-A`: introduce a `ContextAssemblyContract` module that owns L0/L1/history/research/code budget allocation.
- `OPT-M1-B`: make `ContextHub` consume the contract through constructor injection and `strict_deps=True`.
- `OPT-M1-C`: emit a context budget receipt with estimated tokens, selected sources, dropped sources, and reason codes.
- `OPT-M1-D`: annotate dropped sources with HallucinationGuard evidence-gap risk and replacement evidence refs.
- `OPT-M1-E`: validate skill tier/source before assembling skill-derived prompt context; candidate/quarantine/vendor/worktree skills must be blocked unless explicitly diagnostic-only.

Exit:

- context budget decisions are local to one module;
- callers do not reimplement token allocation.

Validation:

- focused tests for token budget allocation, over-budget fail-closed, and L0/L1 preservation.

Stop conditions:

- any change that makes prompt construction less traceable;
- any budget overflow that silently truncates core boundaries.
- any source drop that can remove claim or verification evidence without a fail-closed reason.
- any quarantine-tier skill content entering prompt context without a diagnostic-only boundary.

### M2: Skeleton-First CodeIntel

Goal: reduce full-file reads and route more changes through code skeleton and symbol lookup.

Task cards:

- `OPT-M2-A`: define `CodeSkeletonProvider` interface for Python/JS signatures, docstrings, and line ranges.
- `OPT-M2-B`: add `lookup_implementation(symbol_name)` with exact line-span output.
- `OPT-M2-C`: add a harness sensor warning for large direct file reads without prior skeleton read.
- `OPT-M2-D`: record blast-radius candidates as `depends_on` / `implements` / `relates_to` edges.

Exit:

- codeintel can supply skeleton-first context for route planning and repair tasks;
- large reads become observable, not silently normal.

Validation:

- tests for skeleton extraction, symbol lookup, and safe fallback when tree parsing fails.

Stop conditions:

- blocking normal small-file reads;
- introducing regex-only parsing as the primary implementation.

### M3: Incremental Hybrid Retrieval

Goal: make memory/LanceDB indexing incremental and retrieval quality measurable.

Task cards:

- `OPT-M3-A`: define `HybridRetrievalQuery` and result schema for BM25 + dense vector fusion.
- `OPT-M3-B`: add Merkle-style file/chunk hash tracking around the current index update path.
- `OPT-M3-C`: record retrieval receipts: query, source, score components, selected/not-selected reason.
- `OPT-M3-D`: add semantic dedup metrics for learning and research source refresh.

Exit:

- index refresh can skip unchanged files;
- retrieval quality can be audited per task.

Validation:

- indexer test proving unchanged chunks are not reprocessed;
- retrieval test proving exact symbol names and semantic intent both rank.

Stop conditions:

- full-index rebuild on every refresh;
- hidden reranking rules without score receipts.

### M4: Learning Data Flywheel

Goal: normalize evidence bundles into reusable data for learning, meta-opt, and regression guards.

Task cards:

- `OPT-M4-A`: define an `EvidenceDatasetRecord` for prompt hash, route, capability stack, phase wall, tokens, gates, and outcome.
- `OPT-M4-B`: export benchmark / SF / delivery receipts into a stable data manifest.
- `OPT-M4-C`: add PRM-style phase metrics for S/P/X/D/R/A/C cost and failure causes.
- `OPT-M4-D`: separate data quality gates from model/provider performance gates.

Exit:

- learning data can answer: what worked, what was costly, what evidence was missing, what should be retried.

Validation:

- manifest builder test;
- sample evidence bundle converts into one deterministic dataset record.

Stop conditions:

- training or promotion wording from incomplete evidence;
- mixing provider-token failure with skill-effect failure.

### M5: Harness Route DAG

Goal: make route planning explicit about dependencies, parallelizable work, retries, and reviewer gates.

Task cards:

- `OPT-M5-A`: extend capability plan nodes with `dependencies`, `parallelizable_with`, `required_receipts`, and `retry_policy`.
- `OPT-M5-B`: keep Orchestrator / Agent-Extending / External layers separate in plan output.
- `OPT-M5-C`: require `judge_panel` / `ultra_review` consensus for L3 swarm-deep or high-risk delivery.
- `OPT-M5-D`: make `semantic_failure_sensor` emit bounded retry/fallback decisions instead of vague rerun advice.
- `OPT-M5-E`: require hardened-router/MFP compatibility metadata for route DAG acceptance.
- `OPT-M5-F`: consume BDD harness preflight output before accepting DAGs for tasks with Given-When-Then or business acceptance intent.
- `OPT-M5-G`: read the capability activation contract before adding fallback nodes; `required` protected paths must not contain pre-model deterministic rescue.
- `OPT-M5-H`: call AutonomicRouter pre-route before static DAG construction; forced-swarm nodes must be isolated as serial execution slots.

Exit:

- route plans can be inspected as DAGs;
- no single drone/swarm output can bypass claim and delivery gates.

Validation:

- capability planner tests for DAG ordering and parallel compatibility;
- harness policy tests for retry/fallback hard stops.

Stop conditions:

- putting external tool invocation inside route policy logic;
- unbounded retries without budget safety floor.
- route DAGs that bypass hardened routing or BDD preflight requirements.
- local rescue branches on required protected capability paths;
- forced-swarm route outcomes planned as parallel standard nodes.

### M6: Claim/Evidence Gate Consolidation

Goal: unify delivery, artifact, claim, cost, and public-promotion readiness without collapsing their meanings.

Task cards:

- `OPT-M6-A`: define one read model for delivery/artifact/claim gate status.
- `OPT-M6-B`: ensure public claim gates consume evidence bundles, not ad hoc summary fields.
- `OPT-M6-C`: add claim-boundary fields to every optimization report: internal-only, SF-only, public-ready, or observation-only.
- `OPT-M6-D`: include CompletionEnvelope state in closeout read models.
- `OPT-M6-E`: require mutation assurance summary for high-risk or public-claim-affecting changes.

Exit:

- reports can say exactly which claim is allowed and which is blocked.

Validation:

- tests for missing evidence path, single-arm run, provider-token missing, and hidden verifier missing.

Stop conditions:

- using internal smoke as public benchmark evidence;
- promoting a row with missing provider-token measurement.
- closeout promotion without completion envelope status;
- high-risk or public-claim-affecting change without mutation assurance.

### M7: Skill-Fit Lifecycle Hardening

Goal: make new skill intake, comparison, replacement, and runtime apply a repeatable pipeline.

Task cards:

- `OPT-M7-A`: formalize candidate source classes: curated, external reference, generated candidate, vendor, archive, quarantine.
- `OPT-M7-B`: keep discovery matrix generation separate from runtime apply.
- `OPT-M7-C`: require current-best and challenger receipt-clean PASS in the same provider-cleanliness window before replacement.
- `OPT-M7-D`: write replacement ledger entries with `NO_REPLACEMENT` when provider/session blocks live evidence.
- `OPT-M7-E`: add a research supply-gap diagnostic mock receipt seam for local preflight only; it must not unlock live benchmark or public claim gates.

Exit:

- new skills can be compared without making runtime policy dirty;
- replacement decisions are evidence-backed and reversible.

Validation:

- focused tests for source class blocking;
- targeted Flash+Nexus comparison only after preflight and provider-cleanliness check.

Stop conditions:

- metadata-only winner replacing a current skill;
- external GitHub skill becoming runtime default without apply gate.
- research mock receipts being counted as live skill effectiveness or public benchmark readiness.

### M8: Workspace Evidence Hygiene

Goal: keep generated evidence useful without permanently dirtying the worktree.

Task cards:

- `OPT-M8-A`: classify generated reports into keep, archive, transient, and tracked-source.
- `OPT-M8-B`: keep tracked reports in place; archive only untracked generated evidence.
- `OPT-M8-C`: add a cleanup dry-run that prints deletions/moves before applying.
- `OPT-M8-D`: teach SF/benchmark scripts to emit reports into per-run subdirectories when possible.

Exit:

- repeated SF and benchmark runs do not leave ambiguous untracked sprawl.

Validation:

- dry-run retention plan;
- no tracked docs removed by cleanup.

Stop conditions:

- deleting tracked report history;
- moving evidence that is referenced by a current catalog or ledger.

## 4. Recommended Execution Order

1. `M0` first: freeze claim boundaries and retention rules.
2. `G0` second: bind the plan to existing hard gates before deeper architecture work.
3. `M8` third: reduce workspace noise before deeper work.
4. `M4` fourth: normalize evidence data so later optimization has a clean denominator.
5. `M1 + M2` next: context budget and skeleton-first codeintel.
6. `M3` after `M2`: hybrid retrieval depends on stable chunk/symbol identity.
7. `M5 + M6` after evidence schema stabilizes and G0 compatibility passes: route DAG and gates consume the same receipts.
8. `M7` continuously: skill-fit intake/replacement should use the same evidence and claim boundaries.

## 5. Implementation Slices

Slice size rule:

- maximum 3 production files + matching tests per implementation pass;
- one contract or one adapter per pass;
- every pass must leave a runnable test seam.

Suggested first four implementation slices:

1. `Hard Gate Compatibility`
   - Files: contracts or ops hooks under `nexus/` and `scripts/ops/`, tests in `tests/contracts/` or `tests/ops/`.
   - Purpose: make hardened router, completion, hallucination, mutation, and BDD prerequisites machine-checkable.

2. `EvidenceDatasetRecord`
   - Files: `nexus/learning/*` or `scripts/ops/build_autodata_manifest_from_benchmark.py`, tests in `tests/ops/`.
   - Purpose: normalize benchmark/SF evidence into a typed manifest.

3. `ContextAssemblyContract`
   - Files: `nexus/core/context_hub.py`, new contract module, tests in `tests/core/`.
   - Purpose: isolate budget and L0/L1 preservation.

4. `CodeSkeletonProvider`
   - Files: `nexus/services/codeintel/context_service.py`, tests in `tests/nexus/codeintel/`.
   - Purpose: skeleton-first and symbol lookup.

5. `Skill Replacement Cleanliness Gate`
   - Files: `nexus/learning/skill_fit_closure.py` or `skill_catalog.py`, tests in `tests/learning/`.
   - Purpose: require same-window receipt-clean current/challenger evidence.

## 6. Verification Matrix

Minimum verification before claiming progress:

- context slice: `uv run pytest tests/core/test_context_hub_strict_deps.py`
- codeintel slice: `uv run pytest tests/nexus/codeintel/test_context_service.py`
- route slice: `uv run pytest tests/engine/test_capability_planner.py tests/engine/test_harness_route_policy.py`
- hard-gate compatibility slice: `uv run pytest tests/engine/test_v4_routing_hardening_mvp.py tests/engine/test_completion_contract.py tests/core/test_hallucination_guard.py tests/engine/test_mutation_assurance.py tests/engine/test_harness_sensors.py -q`
- evidence slice: `uv run pytest tests/ops/test_build_autodata_manifest_from_benchmark.py tests/benchmark/test_capability_ab_runner.py -q`
- skill-fit slice: `uv run pytest tests/learning/test_skill_catalog.py tests/learning/test_skill_fit_closure.py tests/ops/test_evaluate_github_skill_challengers.py`

Public benchmark remains blocked unless the public promotion bridge and evidence bundle gates both pass.

## 7. Residual Risks

- Current worktree is dirty with many SF/report artifacts; do not initialize Spec Kit or apply large refactors until retention is settled.
- Some source docs are aspirational specs; each item must be grounded in current repo seams before implementation.
- Provider/session token cleanliness can block live Flash evidence; replacement decisions must hold rather than infer.
- Context and retrieval changes can accidentally weaken capability coverage; use capability receipts and route-funnel metrics as guardrails.

## 8. Next Task Cards

### OPT-NEXT-1: Evidence Retention Dry Run

Goal: classify current generated reports and preserve referenced catalogs/ledgers.

Exit:

- retention plan with keep/archive/transient categories;
- no file move yet.

### OPT-G0-A: Hardened Router Compatibility

Goal: make route DAG and route/context freeze artifacts declare hardened-router readiness.

Exit:

- check output includes hardened flag, MFP threshold values, and router acceptance status;
- failed router compatibility blocks M5 route DAG acceptance only, not planning docs.

### OPT-G0-B: Completion Envelope Closeout

Goal: prevent claim/evidence read models from becoming closeout proxies without completion envelope state.

Exit:

- read model includes `completion_envelope_ref` or a fail-closed `completion_status`;
- closeout promotion remains blocked when the envelope is missing.

### OPT-G0-C: Hallucination Guard Forecast

Goal: make context source drops visible to hallucination scoring before runtime audit.

Exit:

- dropped source entries include risk class and replacement evidence refs when relevant;
- evidence-gap risk returns a blocker before closeout.

### OPT-G0-D: Mutation Assurance Pregate

Goal: require deterministic mutant evidence for high-risk or public-claim-affecting optimization changes.

Exit:

- mutation assurance summary is attached or explicitly not required;
- required assurance must kill at least one deterministic mutant.

### OPT-G0-E: BDD Harness Sensor Pregate

Goal: ensure route DAGs consume BDD preflight for business acceptance tasks.

Exit:

- Given-When-Then/business acceptance tasks require `bdd_acceptance_skill`;
- missing BDD skill returns a preflight blocker.

### OPT-G0-F: Capability Contract Rescue Guard

Goal: prevent M5 fallback planning from putting local deterministic rescue on required protected capability paths.

Exit:

- DAG nodes declare `capability_contract_type`;
- pre-model rescue is allowed only for explicitly `cost_capped` paths and remains blocked for `required` paths.

### OPT-G0-G: Skill Tier Quarantine Guard

Goal: prevent context assembly and public/runtime routes from consuming uncurated or quarantined skill content.

Exit:

- skill-derived context records include source class/tier status;
- candidate, auto-generated, vendor, archive, and worktree-copy skills are blocked unless diagnostic-only.

### OPT-G0-H: Research Supply Gap Guard

Goal: keep local optimization preflight moving without pretending research supply gaps are solved.

Exit:

- supply-gap state blocks live benchmark escalation;
- optional local mock receipts are labeled diagnostic-only and cannot count toward promotion.

### OPT-G0-I: AutonomicRouter-Forward DAG Guard

Goal: make M5 static DAG construction respect runtime forced-swarm decisions.

Exit:

- route DAG builder records pre-route mode;
- forced-swarm nodes are serialized and cannot be scheduled as parallel standard nodes.

### OPT-NEXT-2: Evidence Dataset Contract

Goal: convert one evidence bundle into a normalized data record.

Exit:

- schema + focused test;
- route/capability/phase/token/gate fields retained.

### OPT-NEXT-3: Context Budget Contract

Goal: implement the smallest `ContextAssemblyContract` around existing ContextHub behavior.

Exit:

- L0/L1 preserved;
- over-budget context fails closed with a reason code.

### OPT-NEXT-4: Route DAG Pregate

Goal: expose dependencies and retry policy from capability planning without changing runtime dispatch yet.

Exit:

- plan readout includes dependencies, parallelizable work, required receipts, and fallback policy.

### OPT-NEXT-5: SF Replacement Cleanliness Gate

Goal: prevent replacement from provider-blocked challenger runs.

Exit:

- current-best and challenger must both be receipt-clean PASS in the same provider-cleanliness window.
