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
- `OPT-G0-J`: add an AST freshness guard so skeleton-first blast-radius edges cannot be consumed after symbol drift.
- `OPT-G0-K`: add a retry pollution guard that separates happy-path phase tokens from failed retry tokens before PRM export.
- `OPT-G0-L`: add a memory sanitizer guard for SQLite/markdown observations before any memory writeback.
- `OPT-G0-M`: add a worktree/spec-kit hygiene guard that blocks Spec Kit init or broad report generation in dirty worktrees unless outputs are isolated.
- `OPT-G0-N`: add a rationale preservation guard so skeleton-first CodeIntel keeps WHY/docstring rationale and filters autogenerated boilerplate.
- `OPT-G0-O`: add an evidence union-merge guard for append-only evidence ledgers/graphs with hard size/node caps and post-merge schema validation.
- `OPT-G0-P`: add a packed-context exfiltration guard for secret scans, remote config trust, and output self-exclusion before context/evidence packing.
- `OPT-G0-Q`: add an evidence seal guard so claim/read-model consumers cannot read unsealed, hash-invalid, or partial telemetry bundles.
- `OPT-G0-R`: add a network fetch guard for research/source refresh paths, including SSRF, DNS/redirect revalidation, and private-network target rejection.
- `OPT-G0-S`: add an entity graph integrity guard for namespace collisions and dangling graph/evidence edges.
- `OPT-G0-T`: add a dedup/entropy precision guard so short-token fuzzy matches and low-information labels cannot collapse distinct skills, entities, or evidence rows.

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
- skeleton-first blast-radius edges are consumed after code edits without a fresh AST graph receipt;
- PRM/evidence export mixes successful phase tokens with polluted retry tokens;
- memory writeback stores `<private>` or credential-like text;
- Spec Kit init or broad evidence generation proceeds in a dirty worktree without a transient output root.
- skeleton-first context omits rationale for design-sensitive symbols or imports autogenerated migration/stub rationale as signal.
- evidence ledger/graph merge automation lacks hard caps, schema validation, or append-only/commutative scope.
- packed context includes suspicious file/git diff/git log content or trusts remote repository config by default.
- claim/read-model code consumes unsealed evidence, hash-invalid evidence, or telemetry still being written.
- remote fetch planning lacks private-network rejection or redirect/DNS revalidation.
- graph/evidence records cross project namespaces or contain source/target references that no longer exist.
- dedup logic merges short or low-entropy labels without a precision receipt.

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
- `OPT-M2-E`: emit AST graph freshness receipts after code edits and block stale blast-radius edges.
- `OPT-M2-F`: preserve design rationale by extracting docstrings and `NOTE`/`WHY`/`RATIONALE`/`IMPORTANT` comments as rationale context anchored to the owning symbol.
- `OPT-M2-G`: filter autogenerated rationale from migrations, protobuf/gRPC/OpenAPI stubs, and other generated boilerplate; rationale nodes are context, not callable symbols.
- `OPT-M2-H`: add fault-tolerant AST snapshot fallback so unparsable hot files keep last-known-good symbol context instead of triggering full-file/OOM fallback.

Exit:

- codeintel can supply skeleton-first context for route planning and repair tasks;
- large reads become observable, not silently normal.

Validation:

- tests for skeleton extraction, symbol lookup, and safe fallback when tree parsing fails.
- implemented: `nexus/services/codeintel/skeleton_provider.py` covers exact spans, rationale preservation, autogenerated filtering, and last-known-good AST fallback; `nexus/services/codeintel/skeleton_context_adapter.py` exposes the bounded runtime context adapter.

Stop conditions:

- blocking normal small-file reads;
- introducing regex-only parsing as the primary implementation.
- using session-start skeleton edges after PostToolUse code mutations without a freshness receipt.
- dropping rationale from design-sensitive symbols or resolving rationale nodes as implementation call targets.
- treating generated migration/stub docstrings as architectural rationale.
- syntax-noise or empty AST output clears the current symbol snapshot without a last-known-good fallback.

### M3: Incremental Hybrid Retrieval

Goal: make memory/LanceDB indexing incremental and retrieval quality measurable.

Task cards:

- `OPT-M3-A`: define `HybridRetrievalQuery` and result schema for BM25 + dense vector fusion.
- `OPT-M3-B`: add Merkle-style file/chunk hash tracking around the current index update path.
- `OPT-M3-C`: record retrieval receipts: query, source, score components, selected/not-selected reason.
- `OPT-M3-D`: add semantic dedup metrics for learning and research source refresh.
- `OPT-M3-E`: sanitize memory/findings writeback for `<private>` tags and credential-like values before SQLite or markdown persistence.
- `OPT-M3-F`: add WAL/write-queue/Jittered Backoff requirements before concurrent SQLite or vector-index write paths are optimized.
- `OPT-M3-G`: require dedup/entropy precision receipts for any semantic merge that affects skills, evidence records, or graph entities.

Exit:

- index refresh can skip unchanged files;
- retrieval quality can be audited per task.

Validation:

- indexer test proving unchanged chunks are not reprocessed;
- retrieval test proving exact symbol names and semantic intent both rank.
- implemented: `nexus/contracts/retrieval_receipt.py` records retrieval scoring receipts; `nexus/contracts/hybrid_retrieval.py` adds BM25/dense fusion with chunk-hash and snapshot blockers.

Stop conditions:

- full-index rebuild on every refresh;
- hidden reranking rules without score receipts.
- memory writeback without sanitizer status in evidence records.

### M4: Learning Data Flywheel

Goal: normalize evidence bundles into reusable data for learning, meta-opt, and regression guards.

Task cards:

- `OPT-M4-A`: define an `EvidenceDatasetRecord` for prompt hash, route, capability stack, phase wall, tokens, gates, and outcome.
- `OPT-M4-B`: export benchmark / SF / delivery receipts into a stable data manifest.
- `OPT-M4-C`: add PRM-style phase metrics for S/P/X/D/R/A/C cost and failure causes.
- `OPT-M4-D`: separate data quality gates from model/provider performance gates.
- `OPT-M4-E`: attach phase token sentinel fields and isolate polluted retry ledgers from happy-path PRM records.

Exit:

- learning data can answer: what worked, what was costly, what evidence was missing, what should be retried.

Validation:

- manifest builder test;
- sample evidence bundle converts into one deterministic dataset record.

Stop conditions:

- training or promotion wording from incomplete evidence;
- mixing provider-token failure with skill-effect failure.
- exporting retry-contaminated traces as successful process-reward examples.

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
- `OPT-M6-F`: require sealed evidence and hash-valid evidence before claim/read-model consumers can produce a PASS verdict.

Exit:

- reports can say exactly which claim is allowed and which is blocked.

Validation:

- tests for missing evidence path, single-arm run, provider-token missing, and hidden verifier missing.

Stop conditions:

- using internal smoke as public benchmark evidence;
- promoting a row with missing provider-token measurement.
- closeout promotion without completion envelope status;
- high-risk or public-claim-affecting change without mutation assurance.
- reading unsealed, hash-invalid, partial, or still-being-written telemetry as claim evidence.

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
- implemented: `nexus/contracts/sf_replacement.py` now separates cleanliness decisions from explicit runtime apply plans; public benchmark unlock remains blocked.

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
- `OPT-M8-E`: block Spec Kit init and broad report generation in dirty worktrees unless outputs are explicitly routed to a transient receipt root.
- `OPT-M8-F`: for append-only evidence ledgers/graphs, use union-merge only with explicit file scope, hard caps, and post-merge schema validation.
- `OPT-M8-G`: validate reference-project mining with layout probes before fixed-path scans; package-only references must scan their actual implementation root.

Exit:

- repeated SF and benchmark runs do not leave ambiguous untracked sprawl.

Validation:

- dry-run retention plan;
- implemented: `nexus/contracts/evidence_retention.py` classifies report retention, and `scripts/ops/report_output.py` can route outputs into per-run report directories.
- no tracked docs removed by cleanup.

Stop conditions:

- deleting tracked report history;
- moving evidence that is referenced by a current catalog or ledger.
- generating broad artifacts into `docs/` while code changes are still uncommitted.
- auto-resolving arbitrary JSON conflicts without append-only semantics, hard caps, and schema validation.
- assuming a reference project has `src/`, `dist/`, or root `README.md` before probing its real layout.

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
   - Purpose: make hardened router, completion, hallucination, mutation, BDD, evidence sealing, network fetch, entity graph, and dedup precision prerequisites machine-checkable.

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

### OPT-G0-J: AST Freshness Guard

Goal: prevent skeleton-first CodeIntel from using stale call graph edges after code edits.

Exit:

- changed-symbol tasks carry an AST freshness receipt;
- stale or missing graph freshness blocks blast-radius edge consumption.

### OPT-G0-K: Retry Pollution Guard

Goal: prevent PRM/evidence records from rewarding failed retry trajectories.

Exit:

- phase token sentinel status is PASS or NOT_APPLICABLE;
- retry-polluted tokens are isolated from happy-path process records.

### OPT-G0-L: Memory Sanitizer Guard

Goal: prevent private or credential-like text from entering SQLite/markdown memory seams.

Exit:

- memory sanitizer status is PASS or NOT_APPLICABLE;
- private leak detection blocks memory/evidence export.

### OPT-G0-M: Worktree/SpecKit Hygiene Guard

Goal: prevent dirty worktree state from mixing code changes, Spec Kit init, and broad report sprawl.

Exit:

- Spec Kit init is blocked in dirty worktrees;
- broad generated-output runs must declare a transient output root.

### OPT-G0-N: Rationale Preservation Guard

Goal: prevent skeleton-first optimization from removing design intent.

Exit:

- design-sensitive symbols can carry rationale context alongside signature and line-span receipts;
- autogenerated migration/stub rationale is filtered before context assembly;
- rationale context is never resolved as a callable implementation node.

### OPT-G0-O: Evidence Union-Merge Guard

Goal: make multi-agent evidence ledgers mergeable without accepting poisoned or oversized artifacts.

Exit:

- union-merge is allowed only for explicit append-only or commutative evidence graph/ledger formats;
- merge drivers enforce hard size/node/record caps and fail closed on parse or schema errors;
- post-merge schema validation is recorded before the merged evidence can feed a claim gate.

### OPT-G0-P: Packed Context Exfiltration Guard

Goal: keep repository/context packs from leaking secrets or trusting unreviewed remote configuration.

Exit:

- packed-context exports run a secret scan over files and included git diff/log content;
- suspicious diff/log content is blocked from evidence exports, not merely warned;
- remote repository config is ignored unless an explicit trust receipt is present;
- generated pack output excludes itself from subsequent collection.

### OPT-G0-Q: Evidence Seal Guard

Goal: prevent claim and read-model paths from consuming unsealed, hash-invalid, or partial telemetry.

Exit:

- evidence seal status and evidence hash status are PASS before claim consumers can emit PASS;
- partial telemetry or still-being-written bundles force RETURN;
- sealed evidence carries a stable pointer back to the source bundle and verification command.

### OPT-G0-R: Network Fetch Guard

Goal: prevent research/source refresh and remote context loading from SSRF, DNS TOCTOU, and redirect bypass.

Exit:

- remote fetch planning rejects private, loopback, link-local, and metadata-network targets;
- DNS and redirect targets are revalidated at fetch time;
- network guard status is recorded before fetched content can enter evidence or context seams.

### OPT-G0-S: Entity Graph Integrity Guard

Goal: prevent cross-project entity collisions and dangling graph/evidence references.

Exit:

- graph entities include project namespace and source snapshot identity;
- source and target references resolve before graph/evidence records can feed route or claim gates;
- dangling edges force RETURN rather than being silently dropped.

### OPT-G0-T: Dedup/Entropy Precision Guard

Goal: prevent short-token fuzzy merges or low-information labels from collapsing distinct skills, evidence rows, or graph entities.

Exit:

- semantic dedup that affects skills/evidence/entities carries a precision receipt;
- low-entropy or short-label merges are blocked unless a deterministic namespace key disambiguates them;
- merge decisions remain reversible through the artifact index and source snapshot.

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

### Failure Lesson: Patch Context Drift During Refactor Slices

Lesson:

- When extracting a seam from a large module, inspect the exact local import block and method body before applying a wide patch.
- Treat patch context mismatch as a process failure, not a runtime behavior failure.
- Prevention rule: keep extraction patches narrow and rerun the focused regression before committing the slice.

### Failure Lesson: Freshness-Sensitive Fixtures

Lesson:

- Tests for freshness-gated learning inputs must not hard-code dates that drift past the production retention window.
- Treat stale fixture failures as test-data drift, not as a reason to weaken freshness filtering.
- Prevention rule: use current UTC timestamps for positive freshness fixtures and explicit old timestamps only in rejection tests.

### Failure Lesson: Benchmark Test Path Drift

Lesson:

- Public benchmark regression tests live under `tests/benchmark/`, not `tests/bench/`.
- Treat a missing test path as command drift, not as evidence about benchmark readiness.
- Prevention rule: locate benchmark test modules with `rg` before composing aggregate regression commands.

### Failure Lesson: Public Ready Seal Ordering

Lesson:

- `PUBLIC_READY` evidence records validate seal and hash status during record construction, before manifest-level sealing can run.
- Treat `public_ready_requires_evidence_hash` or `public_ready_requires_evidence_seal` from benchmark JSONL export as evidence-pipeline ordering drift, not as benchmark delivery failure.
- Prevention rule: pre-seal benchmark rows before creating `EvidenceDatasetRecord` whenever the export claim class is `PUBLIC_READY`.

### Failure Lesson: Public Benchmark Environment Drift

Lesson:

- Public benchmark preflight depends on explicit model and hidden-verifier environment variables, even when the CLI flags are otherwise unchanged.
- Treat `nexus_model_env_missing`, `direct_model_env_missing`, or `sentinel_hidden_verifier_disabled` as command environment drift, not route or taskset readiness failure.
- Prevention rule: keep public benchmark smoke, preflight, and full-run commands in one reusable invocation template that always exports `NEXUS_VALUE_HIDDEN_VERIFIER`, `NEXUS_GEMINI_MODEL_NAME`, and `NEXUS_DIRECT_GEMINI_MODEL`.

### Failure Lesson: Focused Test Node Drift

Lesson:

- Long-lived test modules can rename focused test nodes while preserving the same assertion block.
- Treat `not found: ...::test_name` as focused command drift, not as evidence that the behavior lacks coverage.
- Prevention rule: locate the current focused node with `rg` before adding it to a multi-target regression command.

### Failure Lesson: Boundary Gate Normalization Drift

Lesson:

- Boundary gates must preserve unsafe caller intent long enough for blockers to see it.
- Treat normalized-away `runtime_update_allowed` or `public_benchmark_allowed` inputs as gate implementation drift, not as a safe default.
- Prevention rule: read raw boundary-crossing fields into blockers before emitting sanitized claim-boundary defaults, and include both underscore and hyphen path variants for forbidden path probes.

### Failure Lesson: Forced Hyper Probe Drift

Lesson:

- `force_flow=hyper_sprint` still needs the baseline probe when dynamic timeout sizing depends on probe elapsed time and baseline fast-path probing is disabled.
- Treat `effective_stage1_timeout_sec` staying at the static default as execution-profile drift, not as a reason to weaken the timeout test.
- Prevention rule: preserve baseline probe collection for forced Hyper runs only when the dynamic-timeout contract needs it; otherwise keep forced Hyper as direct execution.

### Failure Lesson: Archived Skill Status Path Drift

Lesson:

- Skill catalog policy checks must tolerate the canonical status report moving into the report archive, but must not synthesize or copy a replacement report.
- Treat `FileNotFoundError` for `docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json` as report-retention path drift, not as permission to weaken mount-tier validation.
- Prevention rule: resolve the default status report through an explicit archive fallback and keep the emitted `status_report` pointing at the actual source consumed.

### Failure Lesson: Full Wiki Audit Scope Drift

Lesson:

- Full wiki governance audit currently includes legacy and archive pages with pre-existing page-contract debt unrelated to route/context code slices.
- Treat a full-linter failure on untouched legacy pages as release-scope drift, not as evidence that the changed route/context artifacts are unsafe.
- Prevention rule: use strict changed-scope wiki governance for small production slices, and keep full wiki remediation as a separate archive hygiene campaign.

### Failure Lesson: Wiki Page Contract Tier Drift

Lesson:

- Wiki linting needs a machine-level distinction between active governance pages and retained legacy/report/archive pages.
- Treat old ADR lessons, imported reports, and archive-source pages as managed soft-contract debt unless they are touched in the current change scope.
- Prevention rule: hard-fail active governance pages, but emit `Soft Contract` warnings for explicitly classified legacy/report/archive pages so full CI remains release-usable without hiding remediation debt.

### Failure Lesson: Percent Ratio Policy Drift

Lesson:

- CI policy thresholds must store pass rates as ratios even when legacy governance YAML uses percent-style values.
- Treat a displayed requirement like `8000.00%` as policy-unit drift, not as a real quality target.
- Prevention rule: normalize pass-rate gate inputs above `1.0` by dividing by 100 before comparing them with report ratios.

### Failure Lesson: Wiki Eval Enforcement Level Drift

Lesson:

- `--wiki-eval-enforce-level warn` must emit quality debt without blocking the full CI release gate.
- Treat eval pass-rate misses under the default warn mode as governance follow-up debt, not as an immediate release blocker.
- Prevention rule: keep `strict` as the only blocking wiki eval enforcement mode; default CI should surface the warning while preserving deterministic downstream regression checks.

### Failure Lesson: Contract Default Normalization Drift

Lesson:

- Contract validators must distinguish a missing optional field from an explicitly blank malformed field before applying defaults.
- Treat a test that mutates a serialized contract payload to `""` as a validator-hardening signal, not as proof the runtime object constructor is wrong.
- Prevention rule: apply defaults at construction boundaries, but validate serialized payloads from their raw keys when a field is intended to be fail-closed.

### Failure Lesson: CI Transient Artifact Cleanup Drift

Lesson:

- Full `ci_gate.py` can PASS while tracked generated report/state files remain dirty, forcing every follow-up slice to spend manual cleanup effort before continuing.
- Treat `.nexus` learning closure output, `.nexusknowledge` crystallization output, and root wiki audit reports as known tracked transient CI artifacts unless a specific retention manifest pins them.
- Prevention rule: the CI success closeout restores only known tracked transient artifact paths; untracked generated files remain explicit retention operations and are never silently deleted.

### Failure Lesson: Monkeypatch Evidence Parser Drift

Lesson:

- Patching an evidence parser in a broad CI test module can mask or perturb the real parser behavior for later assertions in the same module.
- Treat parser stubs as a last resort when the test can cheaply emit a real fixture file.
- Prevention rule: changed-only CI tests should write a minimal JUnit fixture and exercise `_extract_junit_target_durations` directly instead of monkeypatching the parser seam.
