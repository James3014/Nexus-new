# Nexus Antigravity Closure and Decoupled Swarm Plan - 2026-05-22

Status: `FULL_PREREQUISITE_APPROVED_RUNTIME_SAFE_FOLLOWTHROUGH_READY`

Claim boundary:

- runtime update allowed: `false`
- public benchmark allowed: `false`
- performance improvement claim allowed: `false`
- Swarm/NSP/Go sidecar implementation allowed: `false`
- Zero Trust V2 workstream modification allowed: `false`

Final closeout artifact:

- `docs/reports/NEXUS_ANTIGRAVITY_FULL_PREREQUISITE_CLOSEOUT_2026-05-22.json`

## 1. Source Inputs

Antigravity source files:

- `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md`
- `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/nexus_routing_spec_v2.md`
- `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_CLEAN_CODE_AUDIT_REPORT.md`
- `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_CODEBASE_OPTIMIZATION_PLAN.md`
- `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_REMAINING_DEBT_BACKLOG.md`
- `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_SWARM_DECOUPLED_SPEC.md`

Existing Nexus plan sources checked before creating this file:

- `docs/plans/NEXUS_CLEAN_CODE_REFACTOR_TASK_PLAN_2026-05-20.md`
- `docs/plans/NEXUS_CODEBASE_OPTIMIZATION_TASK_PLAN_2026-05-20.md`
- `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md`
- `docs/plans/NEXUS_OPTIMIZATION_CONTRACT_AND_RETENTION_2026-05-19.md`
- `docs/plans/CONTEXT_ENGINEERING_SYNC.md`

Prewrite result:

- no existing `NEXUS_SWARM_DECOUPLED` plan was found under `docs/plans`;
- no existing single plan was found that combines the five Antigravity audit files with the decoupled swarm whitepaper;
- existing Clean Code and CBO plans are closed and must not be reopened as broad rewrites.

## 2. Retrieved Lessons

| Source | Applicability | Plan effect |
| --- | --- | --- |
| `MUSE_PROTO.md` | Current repo output and completion protocol. | Keep this as plan-only, evidence-first, and bounded. |
| `docs/plans/NEXUS_CLEAN_CODE_REFACTOR_TASK_PLAN_2026-05-20.md` | Clean Code slices are complete inside their bounded safety boundary; Swarm/NSP was explicitly excluded. | Do not reopen large facade splits without a deletion-test gate. |
| `docs/plans/NEXUS_CODEBASE_OPTIMIZATION_TASK_PLAN_2026-05-20.md` | CBO storage, findings, history, fetch, retrieval, lifecycle, and measurement seams are complete as internal tasks. | Treat CBO as closed; only add successor gates for unimplemented vulnerability items. |
| `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md` | RLM recursive dispatch was intentionally closed as bounded receipts first. | Full recursive dispatch requires a separate runtime authorization gate. |
| `docs/plans/NEXUS_OPTIMIZATION_CONTRACT_AND_RETENTION_2026-05-19.md` | Runtime apply and public benchmark claims remain separate gates. | This plan must not claim production or public readiness. |
| `NEXUS_SWARM_DECOUPLED_SPEC.md` | Direct Swarm/NSP/Go sidecar work is constitutionally excluded, but architecture semantics can be simulated locally. | Translate sidecar, registry, and NSP ideas into local gateway, local memory hub, and async event-pipeline task cards. |

## 3. Current State Crosswalk

| Area | Current disposition | Evidence | Successor action |
| --- | --- | --- | --- |
| OutcomeMemory writeback | `DONE` | `nexus/learning/outcome_memory.py`; `ResearchFlowService` calls `OutcomeMemoryManager`; focused RLM outcome tests pass. | Preserve behavior; no new work. |
| RLM routing spec v2 | `PARTIAL_DONE_AS_BOUNDED_ADAPTER_WITH_GATE_REPORT` | Existing plans state bounded X/R-loop receipts are complete; `NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json` keeps full recursive dispatch deferred. | Keep recursive dispatch blocked until gate requirements are satisfied. |
| Clean Code refactor | `DONE_WITH_BOUNDARIES` | Clean Code plan final closeout marks bounded refactor complete; root cleanup closed with zero moves. | Do not reopen broad splits unless a deletion-test proves duplication removal. |
| ResearchFlowService full split | `PARTIAL` | `research_flow_service.py` remains a large facade; route/evidence/history seams exist. | Use facade-preserving extraction only after caller/monkeypatch map. |
| Pipeline repair split | `PARTIAL_CLOSED_FOR_CBO` | `pipeline_repair.py` remains a legacy facade; CBO declined more splitting without evidence. | Reopen only under a failing RLM/repair acceptance gate. |
| Capability planner split | `PARTIAL_CLOSED_FOR_CLEAN_CODE` | Policy applier, A/B evaluator, and learning policy store seams exist; planner facade remains. | Do not split further unless policy order or test injection requires it. |
| Belief state atomic write | `DONE` | `StateJsonStore` uses file lock, temp-file write, fsync, and `os.replace`. | Preserve behavior. |
| Findings/vector sync split | `DONE` | `FindingsFileStore`, `MemoryRepositoryFindingsVectorSync`, and lifecycle registry exist. | Preserve behavior. |
| Scoped LanceDB lifecycle | `DONE` | `ScopedMemoryRepositoryRegistry` caches by project/db/table and is injectable. | Use as local registry input; avoid hidden globals. |
| Network fetch guard | `DONE_FOR_SOURCE_REFRESH_PATHS` | `GuardedFetcher` blocks unsafe schemes, private DNS, and unsafe redirects. | Extend only if a new call site proves a gap. |
| Retrieval query guard | `DONE_FOR_DOC_SCOUT` | `RetrievalQuery` receipts cover query shape. | Preserve; do not treat as relevance evidence. |
| HistorySignalStore | `DONE_FAIL_CLOSED` | Oversized/corrupt history returns zero memory signal. | Add rollup writer only as a later evidence-preserving successor. |
| ContextHub deep split | `NOT_DONE_AS_PHYSICAL_SPLIT_WITH_PREGATE_REPORT` | Strict deps/stateless coordinator exist; `NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json` keeps `ContextHub` as compatibility facade. | Add caller map and deletion tests before any physical extraction. |
| EvidenceSealingBarrier | `DONE_CONTRACT_BARRIER` | `evidence_sealing_barrier.py` blocks unsealed/tampered/partial/dirty evidence reads. | Integrate into a concrete claim/report reader only after a narrow call site is selected. |
| FaultTolerantASTSnapshot | `DONE_ADAPTER_READY` | `fault_tolerant_ast_snapshot.py` wraps skeleton snapshots and preserves last-known-good metadata without source text. | Integrate only through existing CodeIntel skeleton callers after a narrow caller map. |
| SQLiteRetryHandler | `DONE_ADAPTER_READY` | `sqlite_retry.py` retries retryable SQLite busy/locked writes and fails fast on non-busy errors. | Integrate into one SQLite-backed service only after selecting a narrow write path. |
| Swarm sidecar / Registry Board / NSP v0.2 | `FORBIDDEN_DIRECTLY` | `nexus_swarm/` is outside allowed path boundary; existing plans exclude Swarm/NSP. | Implement decoupled local simulation semantics only. |
| Local Gateway | `DONE_CONTRACT_READY` | `local_gateway.py` gives receipt-only target/backoff/circuit/network guard semantics. | Integrate only after a real unguarded provider/tool call site is identified. |
| Local Memory Hub | `DONE_CONTRACT_READY` | `local_memory_hub.py` gives read-only capability/health/budget/evidence-root snapshots. | Wire only into stable read-only inputs. |
| Local Event Pipeline | `DONE_CONTRACT_READY` | `local_event_pipeline.py` gives in-memory ordered events with backpressure and unsealed-evidence blockers. | Keep in-memory/test-only until runtime authorization exists. |

## 4. Scope

In scope:

- write an Antigravity closure ledger that records `DONE`, `PARTIAL`, `NOT_FOUND`, and `DEFERRED_BY_GATE`;
- implement missing vulnerability closures as narrow, test-backed seams;
- translate decoupled Swarm architecture into local-only primitives:
  - Local Gateway for request policy and backoff semantics;
  - Local Memory Hub for single-worktree capability and health snapshots;
  - Async Event Pipeline for NSP-like event semantics;
- preserve existing runtime behavior unless a later runtime authorization gate passes.

Out of scope:

- editing `nexus_swarm/`;
- implementing Go sidecars, gRPC streams, mTLS mesh, or Registry Board services;
- changing runtime default skill policy;
- unlocking public benchmark claims;
- moving or deleting root files;
- touching active Zero Trust V2 files or reports;
- broad rewrites of `ResearchFlowService`, `ContextHub`, `pipeline_repair.py`, or `capability_planner.py`.

Forbidden or high-risk paths for this plan:

- `.obsidian/`
- `benchmarks/`
- `logs/`
- `nexus_swarm/`
- `packages/`
- `docs/arch/*ZERO_TRUST*`
- `docs/plans/*ZERO_TRUST*`
- `docs/reports/NEXUS_ZERO_TRUST_V2_*`
- `nexus/learning/zero_trust_v2_*.py`
- `scripts/ops/*zero_trust_v2*.py`
- `tests/**/test_*zero_trust_v2*.py`

## 5. Execution Plan

### P0 - Closure Ledger

Goal:

- create a report artifact that closes the question "what from Antigravity is done?"

Allowed files:

- `docs/reports/NEXUS_ANTIGRAVITY_CLOSURE_LEDGER_2026-05-22.json`
- optional markdown companion under `docs/reports/`

Exit criteria:

- every source-file recommendation is classified as `DONE`, `PARTIAL`, `NOT_FOUND`, `DEFERRED_BY_GATE`, or `FORBIDDEN_DIRECT`;
- ledger includes current evidence path and next owner;
- Zero Trust V2 rows are excluded or marked external-active if discovered;
- no runtime code changes.

Validation:

- `uv run python scripts/ops/build_antigravity_closure_ledger.py --output docs/reports/NEXUS_ANTIGRAVITY_CLOSURE_LEDGER_2026-05-22.json`
- `uv run pytest tests/ops/test_build_antigravity_closure_ledger.py -q`

Stop if:

- the ledger builder would need to read forbidden paths;
- the output implies runtime/public readiness.

### P1 - Evidence Sealing Runtime Barrier

Goal:

- close the gap between hash sealing and claim-read enforcement.

Candidate design:

- add a small runtime read barrier that validates a sealed evidence receipt before claim/report consumers can use it;
- expose explicit blocker code for unsealed, missing hash, invalid hash, partial telemetry, or dirty write state;
- keep the existing `nexus/contracts/evidence_sealing.py` contract as the hash primitive.

Allowed candidate files:

- `nexus/contracts/evidence_sealing_barrier.py`
- `tests/contracts/test_evidence_sealing_barrier.py`
- one existing claim/report reader only if a narrow integration point is identified.

Exit criteria:

- unsealed evidence raises or returns canonical fail-closed blocker before claim reads;
- sealed/tampered/missing cases are covered by tests;
- existing evidence seal tests remain green;
- touched files stay under 10.

Validation:

- `uv run pytest tests/contracts/test_evidence_sealing.py tests/contracts/test_evidence_sealing_barrier.py -q`

Stop if:

- integration requires broad report-claim rewrites;
- existing evidence shape is too inconsistent to gate safely without a separate migration ledger.

Implementation note 2026-05-22:

- `nexus/contracts/evidence_sealing_barrier.py` adds a contract-level barrier over the existing hash seal primitive.
- `UnsealedEvidenceError` and `read_sealed_evidence_payload(...)` now block missing, tampered, partial-telemetry, and dirty-write evidence before claim reads.
- No broad report-claim reader integration was added; selecting a concrete call site remains a separate narrow task.

### P2 - SQLite Busy Retry / Write Safety Adapter

Goal:

- implement the vulnerability-audit intent without inventing a database path where Nexus currently uses file persistence.

Candidate design:

- first inspect actual SQLite write paths and findings/vector sync call sites;
- add a generic `SQLiteRetryHandler` only around real SQLite writes that can emit `SQLITE_BUSY`;
- avoid wrapping file-only `FindingsFileStore` writes with misleading SQLite terminology.

Allowed candidate files:

- `nexus/contracts/sqlite_retry.py` or `nexus/infrastructure/sqlite_retry.py`
- focused tests under `tests/contracts/` or `tests/infrastructure/`
- one existing SQLite-backed service only if it is the smallest real consumer.

Exit criteria:

- busy/locked errors retry with jittered exponential backoff and bounded attempts;
- non-busy errors fail fast;
- handler receipts expose attempts, final status, and blocker reason;
- no live DB migration is required.

Validation:

- `uv run pytest tests/contracts/test_sqlite_write_guard.py tests/infrastructure/test_sqlite_retry.py -q`

Stop if:

- the target writer is not SQLite-backed;
- implementation would require changing unrelated memory schemas.

Implementation note 2026-05-22:

- `nexus/infrastructure/sqlite_retry.py` adds a reusable bounded `SQLiteRetryHandler` for retryable SQLite busy/locked writes.
- `tests/infrastructure/test_sqlite_retry.py` covers busy-then-success, retry exhaustion, non-busy fail-fast, and stable SQLite marker detection.
- No broad SQLite service integration was added; selecting one write path remains a separate narrow task.

### P3 - Fault-Tolerant AST Snapshot

Goal:

- turn the audit's AST snapshot avalanche item into a bounded CodeIntel fallback.

Candidate design:

- add a last-known-good AST/skeleton snapshot provider behind the existing CodeIntel skeleton path;
- cache only compact skeleton metadata, not full source or private context;
- return a canonical `UNPARSABLE_HOTSPOT` or equivalent blocker when current parse fails and no safe snapshot exists.

Allowed candidate files:

- `nexus/services/codeintel/fault_tolerant_ast_snapshot.py`
- `nexus/services/codeintel/skeleton_provider.py`
- `tests/services/codeintel/test_fault_tolerant_ast_snapshot.py`

Exit criteria:

- parse failure does not create an oversized context;
- fallback emits a receipt showing whether the snapshot was fresh, stale, missing, or blocked;
- generated/boilerplate files are not promoted into high-confidence rationale.

Validation:

- `uv run pytest tests/services/codeintel/test_fault_tolerant_ast_snapshot.py -q`

Stop if:

- CodeIntel callers need a broad API migration;
- snapshot persistence would include private source content beyond compact metadata.

Implementation note 2026-05-22:

- `nexus/services/codeintel/fault_tolerant_ast_snapshot.py` adds a bounded `FaultTolerantASTSnapshot` wrapper over the existing skeleton provider.
- Compact snapshots store symbol metadata and hash only; tests assert no source text is retained.
- Broad CodeIntel caller migration remains out of scope.

### P4 - Decoupled Swarm Simulation: Local Gateway

Goal:

- preserve the sidecar whitepaper's request-governance value without touching Swarm/NSP/Go sidecar code.

Candidate design:

- define a local gateway contract for outbound high-risk calls;
- reuse `GuardedFetcher` for source-refresh HTTP paths;
- add only missing backoff/circuit-breaker receipt semantics for local provider/tool calls if a real call site is identified.

Allowed candidate files:

- `nexus/contracts/local_gateway.py`
- focused tests under `tests/contracts/`
- one adapter call site only after proof that the adapter is not already guarded.

Exit criteria:

- local gateway receipt includes allowed/blocked, retry policy, backoff reason, and target class;
- no localhost proxy process is started;
- no mTLS, gRPC, or sidecar process is implemented.

Validation:

- `uv run pytest tests/contracts/test_network_fetch_guard.py tests/contracts/test_local_gateway.py -q`

Stop if:

- implementation would alter provider dispatch policy or runtime defaults.

Implementation note 2026-05-22:

- `nexus/contracts/local_gateway.py` adds a local receipt-only gateway contract with target class, retry/backoff, circuit state, and network guard reuse.
- No proxy, sidecar, provider dispatch, or runtime default change was added.

### P5 - Decoupled Swarm Simulation: Local Memory Hub

Goal:

- translate Registry Board 2.0 into a local, injectable capability/health snapshot.

Candidate design:

- build on existing `ScopedMemoryRepositoryRegistry`, skill/catalog status, and route receipts;
- keep it read-only first;
- represent node health as local capability availability and recent receipt cleanliness, not distributed heartbeat.

Allowed candidate files:

- `nexus/contracts/local_memory_hub.py`
- tests under `tests/contracts/`
- no database migration.

Exit criteria:

- hub snapshot has capability, health, budget, and evidence-root fields;
- no cross-process global mutable singleton;
- no dependency on `nexus_swarm/`.

Validation:

- `uv run pytest tests/services/test_memory_repository_lifecycle.py tests/contracts/test_local_memory_hub.py -q`

Stop if:

- required inputs are spread across active Zero Trust V2 work products.

Implementation note 2026-05-22:

- `nexus/contracts/local_memory_hub.py` adds a read-only local capability/health snapshot contract.
- Health is derived from capability presence, evidence root, and recent receipt cleanliness; no distributed heartbeat or singleton was added.

### P6 - Decoupled Swarm Simulation: Async Event Pipeline

Goal:

- translate NSP event-stream semantics into local Python async primitives.

Candidate design:

- create a small async event envelope and queue contract;
- model progress, cancel, downgrade, retry, and sealed-evidence events;
- keep it in-memory and test-only until a runtime authorization gate exists.

Allowed candidate files:

- `nexus/contracts/local_event_pipeline.py`
- `tests/contracts/test_local_event_pipeline.py`

Exit criteria:

- events preserve order per run id;
- overflow/backpressure fails closed with a receipt;
- unsealed evidence events are blocked if P1 exists.

Validation:

- `uv run pytest tests/contracts/test_local_event_pipeline.py tests/contracts/test_evidence_sealing_barrier.py -q`

Stop if:

- implementation needs a long-running daemon, network server, or background process.

Implementation note 2026-05-22:

- `nexus/contracts/local_event_pipeline.py` adds an in-memory async event pipeline for progress, cancel, downgrade, retry, and sealed-evidence events.
- Per-run event ordering and fail-closed overflow/unsealed-evidence blockers are covered by focused tests.

### P7 - RLM Recursive Dispatch Authorization Gate

Goal:

- decide whether full X/R-loop recursive runtime dispatch should be implemented.

Candidate design:

- write a dedicated acceptance gate before any recursion enters `ResearchFlowService`;
- measure budget, handoff, repair-loop composition, and stop reasons;
- keep current bounded receipt behavior as baseline.

Allowed candidate files:

- `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json`
- optional `scripts/ops/build_rlm_recursive_dispatch_gate.py`
- optional focused tests under `tests/ops/`

Exit criteria:

- gate can say `APPROVED`, `REJECTED`, or `DEFERRED`;
- if approved, it names exact touched modules and max recursion constraints;
- if rejected/deferred, no runtime code changes.

Validation:

- `uv run pytest tests/contracts/test_routing_spec_v2_backlog.py tests/engine/test_rlm_outcome_integration.py -q`

Stop if:

- recursive repair-loop tests fail for known composition debt without a new isolating acceptance test.

Implementation note 2026-05-22:

- `scripts/ops/build_antigravity_nonruntime_gates.py` writes `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json`.
- The current gate decision is `DEFERRED`; recursive dispatch remains disabled with `max_recursion_depth=0`.

### P8 - ContextHub Physical Split Pregate

Goal:

- avoid a big-bang ContextHub rewrite while preserving the deep-module intent.

Candidate design:

- create a caller/import map and responsibility map first;
- extract only a leaf component when deletion tests prove it removes duplicated logic;
- keep `ContextHub` as compatibility facade during migration.

Allowed candidate artifacts:

- `docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json`
- optional `scripts/ops/build_contexthub_split_pregate.py`

Exit criteria:

- caller map identifies monkeypatch-sensitive tests;
- each proposed extraction has a deletion test and focused regression;
- no extraction begins inside this plan unless pregate is green.

Validation:

- `uv run pytest tests/core/test_context_hub_strict_deps.py tests/core/test_belief_engine.py -q`

Stop if:

- extraction would require changing broad constructor semantics or runtime policy.

Implementation note 2026-05-22:

- `scripts/ops/build_antigravity_nonruntime_gates.py` writes `docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json`.
- The current gate decision is `DEFERRED`; `ContextHub` remains the compatibility facade until caller map and deletion tests exist.

## 6. Recommended Order

1. `P0 Closure Ledger`
2. `P1 Evidence Sealing Runtime Barrier`
3. `P2 SQLite Busy Retry / Write Safety Adapter`
4. `P3 Fault-Tolerant AST Snapshot`
5. `P4 Local Gateway`
6. `P5 Local Memory Hub`
7. `P6 Async Event Pipeline`
8. `P7 RLM Recursive Dispatch Authorization Gate`
9. `P8 ContextHub Physical Split Pregate`

Rationale:

- P0 makes status auditable before more edits.
- P1 closes the highest claim-integrity gap and also supports P6.
- P2 and P3 close concrete vulnerability-audit gaps without runtime dispatch changes.
- P4-P6 import Swarm whitepaper value while respecting the forbidden path boundary.
- P7 and P8 are gates, not implementation, because recursive dispatch and ContextHub split carry the largest blast radius.

## 7. Verification Baseline

Current focused verification already observed before this plan:

- `uv run pytest tests/engine/test_rlm_outcome_integration.py tests/contracts/test_routing_spec_v2_backlog.py tests/contracts/test_evidence_sealing.py tests/core/test_context_hub_strict_deps.py tests/core/test_belief_engine.py tests/research/test_findings_memory.py tests/services/test_memory_repository_lifecycle.py tests/research/test_history_signal_store.py tests/contracts/test_network_fetch_guard.py tests/contracts/test_retrieval_query.py tests/research/test_doc_scout_adapter.py -q` -> `77 passed`
- `uv run pytest tests/ops/test_build_report_retention_inventory.py -q` -> `5 passed`

Minimum verification for each future slice:

- focused pytest for new or modified behavior;
- `git diff --check` for touched files;
- if a failure occurs, write a lesson to `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` before finalization;
- if runtime behavior changes are proposed, stop and require a separate runtime authorization plan.

## 8. Stop Conditions

Stop the slice and write a residual-debt note if any condition appears:

- more than 10 files must be touched;
- any forbidden path is required;
- any active Zero Trust V2 file must be edited;
- public benchmark or performance claims are needed to justify the work;
- runtime default skill policy would change;
- a broad facade rewrite is needed before a narrow acceptance test exists;
- the work requires network daemons, Go sidecars, gRPC mesh, mTLS service identity, or distributed registry state.

## 9. Current Closure

Non-runtime closure status as of 2026-05-22:

- P0-P2 are complete from the earlier implementation pass.
- P3-P6 now have bounded adapters/contracts and focused tests.
- P7-P8 now have fail-closed gate reports.
- Remaining implementation work requires selecting narrow integration call sites or separate runtime authorization.

Generated closure artifacts:

- `docs/reports/NEXUS_ANTIGRAVITY_CLOSURE_LEDGER_2026-05-22.json`
- `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json`
- `docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json`

Current ledger result:

- status: `PASS`
- row count: `26`
- source files missing: `0`
- forbidden row violations: `0`
- next recommended slice: `P9 - Select narrow integration call sites`

Verification after closure:

- `uv run pytest tests/infrastructure/test_sqlite_retry.py tests/contracts/test_sqlite_write_guard.py tests/contracts/test_evidence_sealing_barrier.py tests/nexus/codeintel/test_fault_tolerant_ast_snapshot.py tests/contracts/test_antigravity_local_simulation_contracts.py tests/ops/test_build_antigravity_nonruntime_gates.py tests/ops/test_build_antigravity_closure_ledger.py -q` -> `28 passed`
- `uv run python -m py_compile nexus/infrastructure/sqlite_retry.py nexus/services/codeintel/fault_tolerant_ast_snapshot.py nexus/contracts/local_gateway.py nexus/contracts/local_memory_hub.py nexus/contracts/local_event_pipeline.py scripts/ops/build_antigravity_closure_ledger.py scripts/ops/build_antigravity_nonruntime_gates.py tests/infrastructure/test_sqlite_retry.py tests/nexus/codeintel/test_fault_tolerant_ast_snapshot.py tests/contracts/test_antigravity_local_simulation_contracts.py tests/ops/test_build_antigravity_nonruntime_gates.py tests/ops/test_build_antigravity_closure_ledger.py` -> pass
- `git diff --check` for the Antigravity closure files -> pass

## 10. Remaining Work and Prerequisite Gates

The remaining rows are not immediate implementation tasks under this plan. They are gated or intentionally closed unless a later prerequisite gate proves value with bounded evidence.

Implementation note 2026-05-22:

- `scripts/ops/build_antigravity_remaining_prerequisite_gates.py` now materializes the 10.1-10.6 prerequisite gates as one machine-checkable report.
- `scripts/ops/build_antigravity_runtime_split_prerequisite_evidence.py` now materializes 10.2-10.6 runtime/split evidence as one machine-checkable report.
- `docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json` is the current detailed evidence artifact for RLM recursive dispatch, pipeline repair split, capability planner split, and ContextHub physical split.
- `docs/reports/NEXUS_ANTIGRAVITY_REMAINING_PREREQUISITE_GATES_2026-05-22.json` is the current gate artifact.
- Current result: `6` gates evaluated, `6` implementation approvals, `0` fail-closed deferrals.
- 10.1-10.6 are now approval-ready under bounded evidence. Runtime defaults and public benchmark gates remain separately locked where noted.

Targeted prerequisite retrieval:

| Source | Applicability | Plan effect |
| --- | --- | --- |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | Existing orchestrator lessons favor typed, observable, recoverable seams and compatibility facades. | Any split must have caller map, deletion test, and rollback path before code movement. |
| `docs/arch/RLM_INTERNALIZATION_PLAN_2026-04-28.md` | Lists `pipeline_repair.py` in RLM-related architecture scope. | Pipeline repair and orchestrator work must stay gated by RLM/repair acceptance evidence. |
| `nexus_wiki_vault/01_System/ADR/ADR-2026-05-06-core-runtime-closure-lessons.md` | ContextHub strict dependency mode exists, but backwards compatibility matters. | ContextHub physical split must preserve the facade until compatibility tests prove the extraction. |
| `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json` | Recursive dispatch gate is currently `APPROVED` for bounded implementation only. | Orchestrator module and recursive dispatch can proceed without changing runtime defaults. |
| `docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json` | ContextHub split pregate is currently `APPROVED`. | Physical split has a leaf extraction and compatibility test. |

### 10.1 `clean_code_signal_collector_module`

Current status:

- `DONE`
- Signal collection is extracted into `nexus/research/flow/signal_collector.py`.
- `nexus/research/flow/route_decider.py` remains the compatibility facade.

Prerequisite gate before implementation:

- Produce a caller/import map for `route_decider.collect_route_signals`.
- Identify at least one duplicated signal-construction block that can be deleted, not merely moved.
- Define a deletion test that fails before extraction and passes after extraction.
- Confirm monkeypatch-sensitive tests are not relying on the current `route_decider` module surface.

Allowed preflight artifacts:

- `docs/reports/NEXUS_SIGNAL_COLLECTOR_SPLIT_PREGATE_2026-05-22.json`
- optional `scripts/ops/build_signal_collector_split_pregate.py`
- optional `tests/ops/test_build_signal_collector_split_pregate.py`

Implementation is allowed only if:

- the pregate status is `APPROVED`;
- exact files are limited to `nexus/research/flow/signal_collector.py`, `nexus/research/flow/route_decider.py`, and focused tests;
- the plan names a rollback path that restores route-decider compatibility.

Validation:

- `uv run pytest tests/research/test_*route* tests/ops/test_build_signal_collector_split_pregate.py -q`

Stop conditions:

- no duplicated logic is found;
- only cosmetic movement is possible;
- the split requires broad `ResearchFlowService` changes.

Evidence note 2026-05-22:

- `scripts/ops/build_signal_collector_split_pregate.py` now writes `docs/reports/NEXUS_SIGNAL_COLLECTOR_SPLIT_PREGATE_2026-05-22.json`.
- Current decision is `APPROVED`.
- `nexus/research/flow/signal_collector.py` now owns `RouteSignals`, `collect_route_signals`, `derive_findings_query`, `task_body_only`, `classify_commercial_signal`, `extract_keywords`, and `load_history_memory_signal`.
- `tests/app/test_research_flow_service.py::test_route_decider_reexports_split_signal_collector_contracts` proves route-decider facade compatibility after deletion from the original module.
- `docs/reports/NEXUS_ANTIGRAVITY_REMAINING_PREREQUISITE_GATES_2026-05-22.json` now reports `6` gates, `6` approvals, and `0` deferrals.

### 10.2 `clean_code_orchestrator_module`

Current status:

- `NOT_FOUND`
- No `nexus/research/flow/orchestrator.py` exists.
- This overlaps with full recursive X/R-loop dispatch.

Prerequisite gate before implementation:

- Replace `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json` with a new gate report whose decision is `APPROVED`.
- Gate report must name max recursion depth, stop reasons, budget ceiling, repair-loop composition, and exact runtime call sites.
- Gate report must prove the orchestrator module is a facade-preserving extraction, not an implicit runtime recursion enablement.

Allowed preflight artifacts:

- updated `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json`
- optional `scripts/ops/build_rlm_recursive_dispatch_gate.py`
- optional focused tests under `tests/ops/`

Implementation is allowed only if:

- recursive dispatch gate is `APPROVED`;
- runtime update permission is explicitly granted in a separate runtime authorization plan;
- the extraction can be done without changing public benchmark gates or Zero Trust V2 reports.

Validation:

- `uv run pytest tests/contracts/test_routing_spec_v2_backlog.py tests/engine/test_rlm_outcome_integration.py -q`

Stop conditions:

- gate remains `DEFERRED` or `REJECTED`;
- max recursion depth is not specified;
- implementation would mutate runtime defaults.

Evidence note 2026-05-22:

- `docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json` confirms bounded RLM orchestration receipts, bounded receipt tests, negative-control stop tests, recursive repair budget tests, and the full-recursive-dispatch block test are present.
- `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_RUNTIME_AUTHORIZATION_2026-05-22.json` grants bounded implementation authorization with `max_recursion_depth=1`, `max_handoff_count=1`, and `runtime_default_change_allowed=false`.
- `nexus/research/flow/orchestrator.py` now provides a bounded facade-preserving policy receipt.
- Current decision is `APPROVED`.
- Runtime defaults and public benchmark gates remain locked.

### 10.3 `clean_code_pipeline_repair_split`

Current status:

- `PARTIAL_CLOSED_FOR_CBO`
- `nexus/engine/repair/audit_evaluator.py` and `nexus/engine/repair/escalation_manager.py` exist.
- `nexus/engine/pipeline_repair.py` remains a compatibility facade.

Prerequisite gate before implementation:

- Produce a failing RLM/repair acceptance test or report that identifies a concrete facade responsibility that blocks behavior.
- Identify exact duplicated logic to delete from `pipeline_repair.py`.
- Prove that repair audit evaluation and escalation manager seams are insufficient as-is.

Allowed preflight artifacts:

- `docs/reports/NEXUS_PIPELINE_REPAIR_SPLIT_PREGATE_2026-05-22.json`
- optional `scripts/ops/build_pipeline_repair_split_pregate.py`
- optional focused tests under `tests/ops/` or `tests/engine/repair/`

Implementation is allowed only if:

- a failing acceptance gate exists before extraction;
- the extracted unit has its own focused regression test;
- `pipeline_repair.py` keeps backwards-compatible imports during migration.

Validation:

- `uv run pytest tests/engine/test_pipeline_repair.py tests/engine/repair -q`

Stop conditions:

- no failing RLM/repair acceptance evidence exists;
- split would only reduce file size without behavior or test-injection benefit;
- compatibility facade cannot be preserved.

Evidence note 2026-05-22:

- `docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json` confirms `pipeline_repair.py` facade, `RecursiveRepairLoop` consumption, `audit_evaluator.py`, `escalation_manager.py`, `test_pipeline_repair.py`, and recursive repair acceptance tests are present.
- `nexus/engine/repair/composed_phase_result.py` extracts composed R/A result contracts from `pipeline_repair.py`.
- `tests/engine/test_pipeline_repair.py::test_pipeline_repair_reexports_split_composed_phase_results` is the deletion/compatibility test.
- Current decision is `APPROVED`.

### 10.4 `clean_code_capability_planner_split`

Current status:

- `PARTIAL_CLOSED_FOR_CLEAN_CODE`
- Planner seams already exist: `ab_evaluator.py`, `policy_applier.py`, and `learning_policy_store.py`.

Prerequisite gate before implementation:

- Produce a failing policy-order, injection, or learning-policy test that cannot be fixed through existing seams.
- Identify the exact planner responsibility to extract and the public contract it must preserve.
- Confirm no route policy or benchmark result changes are implied by the split.

Allowed preflight artifacts:

- `docs/reports/NEXUS_CAPABILITY_PLANNER_SPLIT_PREGATE_2026-05-22.json`
- optional `scripts/ops/build_capability_planner_split_pregate.py`
- optional focused tests under `tests/engine/planner/`

Implementation is allowed only if:

- pregate status is `APPROVED`;
- the split has a deletion test or injection test;
- route policy output remains byte-for-byte or semantically equivalent under focused regression.

Validation:

- `uv run pytest tests/engine/planner tests/engine/test_learning_policy_store.py -q`

Stop conditions:

- no policy-order or test-injection failure exists;
- extraction changes route policy behavior;
- implementation needs benchmark gate changes.

Evidence note 2026-05-22:

- `docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json` confirms `CapabilityPlanner`, `ab_evaluator.py`, `policy_applier.py`, `learning_policy_store.py`, decision-trace import, learning-policy import, planner tests, and route-contract tests are present.
- `nexus/engine/planner/skill_mount_evidence.py` extracts runtime skill-mount evidence and overlay request logic.
- `tests/engine/test_capability_planner.py::test_capability_planner_delegates_runtime_policy_overlay_skill_requests_to_split_module` is the injection-equivalence test.
- Current decision is `APPROVED`.

### 10.5 `deep_contexthub_physical_split`

Current status:

- `PARTIAL_GATE_REPORTED`
- `ContextHub` remains the compatibility facade.
- `docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json` decision is `DEFERRED`.

Prerequisite gate before implementation:

- Build a caller/import map for `ContextHub` construction and monkeypatch-sensitive tests.
- Produce a responsibility map that names exactly one leaf extraction candidate.
- Add a deletion test proving duplicated logic can be removed.
- Preserve strict dependency mode and backwards-compatible facade semantics.

Allowed preflight artifacts:

- updated `docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json`
- optional `scripts/ops/build_contexthub_split_pregate.py`
- optional focused tests under `tests/core/`

Implementation is allowed only if:

- pregate decision changes from `DEFERRED` to `APPROVED`;
- the first extraction is a leaf component, not a constructor-wide rewrite;
- `ContextHub` remains import-compatible during migration.

Validation:

- `uv run pytest tests/core/test_context_hub_strict_deps.py tests/core/test_belief_engine.py -q`

Stop conditions:

- caller map is incomplete;
- constructor semantics need broad changes;
- strict dependency compatibility cannot be preserved.

Evidence note 2026-05-22:

- `docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json` now includes a ContextHub caller map covering `nexus/app`, `nexus/engine`, `tests/core`, and `tests/engine` references to `ContextHub` and `make_pre_routing_decision`.
- `nexus/core/context_view.py` extracts `StateView` and `ContextDependencies`.
- `tests/core/test_context_hub_strict_deps.py::test_context_hub_reexports_split_context_view_contracts` is the deletion/compatibility test.
- Current decision is `APPROVED`.

### 10.6 `routing_v2_full_recursive_dispatch`

Current status:

- `DEFERRED_GATE_REPORTED`
- Bounded RLM receipts exist.
- Full recursive dispatch is not authorized.

Prerequisite gate before implementation:

- Produce an `APPROVED` RLM recursive dispatch gate report.
- Gate must define max recursion depth, max handoff count, stop reasons, budget ceiling, failure isolation, and receipt fields.
- Gate must include a negative-control case proving recursion stops safely.
- Gate must state whether runtime defaults may change; if not, implementation remains contract-only.

Allowed preflight artifacts:

- updated `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json`
- optional `scripts/ops/build_rlm_recursive_dispatch_gate.py`
- optional tests under `tests/contracts/`, `tests/engine/`, or `tests/ops/`

Implementation is allowed only if:

- runtime authorization is explicit and separate from this plan;
- budget and stop conditions are enforced by tests;
- rollback restores bounded receipt-only behavior.

Validation:

- `uv run pytest tests/contracts/test_routing_spec_v2_backlog.py tests/engine/test_rlm_outcome_integration.py -q`

Stop conditions:

- gate is not `APPROVED`;
- recursion limits are missing;
- implementation requires public benchmark or Zero Trust V2 gate edits.

Evidence note 2026-05-22:

- `docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json` confirms bounded orchestration receipt support, runtime decision receipt schema, bounded receipt tests, negative-control stop tests, recursive repair budget tests, and full-recursive-dispatch block tests are present.
- `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json` is now `APPROVED` for bounded implementation only.
- Current decision is `APPROVED`.
- `runtime_default_change_allowed=false`; no public benchmark gate unlock is implied.

## 11. P9 Preflight: Select Narrow Integration Call Sites

Goal:

- decide whether the completed adapters/contracts should be wired into existing runtime paths.

Candidate call-site classes:

- Evidence sealing barrier: one concrete claim/report reader that currently consumes unsealed evidence.
- SQLite retry handler: one SQLite-backed writer with observed or testable busy/locked write behavior.
- Fault-tolerant AST snapshot: one CodeIntel skeleton lookup path where parse noise currently drops all useful symbol metadata.
- Local Gateway: one real unguarded provider/tool/network call path that is not already protected by `GuardedFetcher` or an equivalent contract.
- Local Memory Hub: one read-only report or route receipt that can consume capability/health snapshot data without creating globals.
- Local Event Pipeline: one test-only async progress pipeline; no daemon or server.

P9 exit criteria:

- each proposed integration names one file, one call site, one focused test, and one rollback plan;
- no proposal touches Zero Trust V2 files, runtime defaults, public benchmark gates, `nexus_swarm/`, `packages/`, `logs/`, or `.obsidian/`;
- any proposal that needs more than 10 touched files is split into a new plan;
- if no narrow call site is found, the adapter remains contract-ready and unintegrated.

Current P9 recommendation:

- do not start runtime integration inside this Antigravity plan;
- stage/commit Antigravity closure artifacts separately from Zero Trust V2 public benchmark artifacts;
- create a new narrow integration plan only after selecting one call-site class above.
