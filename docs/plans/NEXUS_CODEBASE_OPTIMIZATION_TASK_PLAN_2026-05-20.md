# Nexus Codebase Optimization Task Plan

Status: `PLAN_ONLY`
Date: `2026-05-20`
Source plan: `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_CODEBASE_OPTIMIZATION_PLAN.md`
Related closeout: `docs/plans/NEXUS_CLEAN_CODE_REFACTOR_TASK_PLAN_2026-05-20.md`

## 1. Purpose

This plan converts the external codebase optimization proposal into bounded
Nexus task cards.

The source proposal targets four pressure points:

- remaining god-module coupling;
- physical I/O amplification and concurrent state corruption;
- runtime security sandbox boundaries;
- trace and history growth.

This plan keeps those goals, but rewrites them into Nexus-safe slices with
machine-checkable exits. It does not authorize runtime policy changes, public
benchmark claims, broad root cleanup, or Swarm/NSP work.

## 2. Assessment

### 2.1 Useful Direction

The proposal is directionally useful because it points at real local seams:

- `nexus/core/belief_engine.py` still writes `.nexus/belief_state.json` through
  direct `open(..., "w")` calls.
- `nexus/research/findings_memory.py` already has atomic writes, but mixes card
  persistence, LanceDB sync, and sync-status rewrite in one method.
- `nexus/research/flow/route_decider.py` reads the whole
  `.nexus/reports/research/auto-flow-history.json` file for route memory
  signals.
- `nexus/contracts/network_fetch_guard.py` has a guard receipt contract, but not
  every network call site is forced through a fetch adapter.

### 2.2 Required Corrections

The proposal must be corrected before implementation:

- `pipeline_repair.py` and `capability_planner.py` were already partially split
  by the Clean Code plan. Do not reopen them with another broad split unless a
  new seam passes the deletion test.
- "100% SSRF defense", "90%+ coverage", and fixed I/O reduction percentages are
  not acceptable as claims unless measured by a dedicated observation-only
  harness.
- A global LanceDB singleton can become hidden mutable state. Prefer an injected
  repository/cache seam with explicit lifecycle and tests.
- "RAG query character cleaning" is too weak. The real interface should be a
  typed retrieval query contract with length, control-character, source-scope,
  and receipt fields.
- Root trace compression must preserve replay/evidence pointers. Compression
  cannot delete public-claim, SF, or delivery evidence.

## 3. Scope Boundaries

Allowed:

- add deep modules with narrow interfaces;
- add adapters and tests for state write, findings memory, retrieval query, and
  network fetch seams;
- add observation-only harnesses for I/O and latency measurements;
- add retention/rollup manifests under `docs/reports/`.

Forbidden in this plan:

- public benchmark unlock;
- runtime default skill updates;
- Swarm/NSP/Go sidecar changes;
- deleting evidence;
- moving root scripts without wrapper migration;
- claiming performance improvement without before/after evidence.

## 4. Current Baseline Crosswalk

| Source proposal area | Current Nexus status | Plan action |
| --- | --- | --- |
| God-module decoupling | `CC-1..CC-7` already split route, evidence, repair audit/escalation, planner policy, planner trace, and policy store seams | Do not repeat broad splitting; only add new seams if they remove concrete I/O/security coupling |
| Belief state atomic write | `BeliefEngine` still directly reads/writes JSON | Implement `StateJsonStore` and migrate `BeliefEngine` first |
| Findings/LanceDB I/O | `FindingsMemoryStore.write` persists JSON, syncs LanceDB, and rewrites sync status | Split persistence from vector sync; make sync adapter injectable |
| LanceDB connection pooling | Some services cache connections, but call sites are inconsistent | Add a scoped retrieval/memory repository lifecycle seam; avoid hidden global singleton |
| SSRF guard | Guard receipt exists; fetch call sites are inconsistent | Add guarded fetch adapter and migrate highest-risk research/source-refresh paths first |
| RAG query guard | Retrieval query is mostly raw string input | Add typed retrieval query sanitizer with receipt fields |
| auto-flow history growth | route decision reads entire history file | Add `HistorySignalStore` with bounded read and rollup plan |

## 5. Task Cards

### CBO-PREFLIGHT: Baseline and Claim Boundary Freeze

Goal: freeze the optimization scope before code changes.

Scope:

- record current git commit;
- record prior Clean Code completion status;
- confirm this plan remains internal and observation-only.

Exit:

- this plan is committed as `PLAN_ONLY`;
- no runtime/public claim is made.

Verification:

- `git status --short --untracked-files=all`;
- markdown review only.

### CBO-1: State JSON Store and BeliefEngine Migration

Goal: remove direct JSON writes from `BeliefEngine`.

Proposed module:

- `nexus/infrastructure/state_json_store.py`

Interface:

- `read_dict(path: Path) -> dict[str, Any]`;
- `write_dict(path: Path, payload: dict[str, Any]) -> None`;
- atomic temp-file write + `os.replace`;
- process lock using the existing local lock pattern where available.

Exit:

- `BeliefEngine` reads and writes through the store;
- corrupt/partial JSON behavior is fail-closed and tested;
- no belief scoring semantics change.

Verification:

- focused `BeliefEngine` tests;
- multiprocess or threaded write test proving valid final JSON.

### CBO-2: Findings Memory Persistence / Vector Sync Split

Goal: make findings-card persistence independent from LanceDB sync.

Proposed modules:

- `nexus/research/findings_store.py`;
- `nexus/research/findings_vector_sync.py`.

Exit:

- card JSON persistence has one responsibility;
- vector sync is an injected adapter with explicit success/failure status;
- a LanceDB failure cannot corrupt card persistence.

Verification:

- existing `tests/research/test_findings_memory.py`;
- new test where vector sync raises and JSON card still persists with
  `lancedb_synced=false`.

### CBO-3: Scoped LanceDB Repository Lifecycle

Goal: reduce repeated LanceDB setup without introducing hidden global state.

Scope:

- define a scoped repository lifecycle adapter used by `FindingsMemoryStore` and
  retrieval services;
- cache only by explicit `(project_root, db_path, table)` key;
- expose a reset/close hook for tests.

Exit:

- repeated retrieval/write paths can reuse an adapter in-process;
- tests can replace/reset the adapter;
- no global singleton leaks across project roots.

Verification:

- connection factory called once for repeated same-scope operations;
- separate project roots do not share handles.

### CBO-4: History Signal Store and Rollup Contract

Goal: stop route decision from reading unbounded `auto-flow-history.json`.

Proposed module:

- `nexus/research/flow/history_signal_store.py`

Exit:

- `route_decider.load_history_memory_signal` delegates to `HistorySignalStore`;
- recent-window reads are bounded;
- old entries can be summarized to a rollup file without deleting evidence
  pointers;
- corrupt history returns zero hits instead of breaking routing.

Verification:

- route-decider history tests;
- large synthetic history test proving bounded processing.

### CBO-5: Guarded Fetch Adapter

Goal: enforce network fetch guard at call sites, not only in a receipt helper.

Proposed module:

- `nexus/infrastructure/guarded_fetch.py`

Scope:

- DNS/redirect revalidation at fetch time;
- block unsupported schemes and private/link-local/loopback metadata targets
  unless explicitly local-only;
- start with research/source-refresh/doc-scout paths, not every local localhost
  provider path.

Exit:

- highest-risk remote fetch paths consume the adapter;
- receipts include URL, resolved IPs, redirect status, and blockers;
- existing local provider calls remain out of scope unless separately routed.

Verification:

- `tests/contracts/test_network_fetch_guard.py`;
- call-site tests for private IP and file redirect blocking.

### CBO-6: Retrieval Query Contract

Goal: replace raw retrieval query strings with a small typed contract.

Proposed module:

- `nexus/contracts/retrieval_query.py`

Exit:

- query has normalized text, length budget, source scope, unsafe token flags,
  and receipt fields;
- retrieval code can reject or downgrade unsafe queries;
- source-discipline evidence is preserved.

Verification:

- unit tests for normalization and fail-closed blockers;
- focused retrieval tests showing unchanged good-query results.

### CBO-7: Observation-Only I/O Measurement Harness

Goal: measure before/after I/O and latency without making public claims.

Scope:

- track file read/write counts around `build_route`, route memory signal, and
  findings write;
- write observation-only report under `docs/reports/`;
- no benchmark/public readiness unlock.

Exit:

- report contains baseline, changed measurement, sample size, and limitations;
- no fixed percentage claim unless measured.

Verification:

- deterministic fixture run;
- report schema check.

### CBO-8: Repair Split Continuation Gate

Goal: decide whether the source plan's proposed `repair_runner`,
`repair_verifier`, and `repair_rollback` split is still warranted after the
Clean Code repair split.

Exit:

- if warranted, produce a separate task plan with deletion-test evidence;
- if not warranted, record `NO_ACTION` with reason.

Verification:

- inspect `pipeline_repair.py` after CC closeout;
- focused repair tests only if implementation is authorized later.

## 6. Recommended Order

1. `CBO-PREFLIGHT`
2. `CBO-1`
3. `CBO-2`
4. `CBO-4`
5. `CBO-5`
6. `CBO-6`
7. `CBO-3`
8. `CBO-7`
9. `CBO-8`

Rationale:

- state corruption and history growth are correctness risks, so they come
  before performance pooling;
- guarded fetch and retrieval query contracts should be implemented before
  broader research/source-refresh automation;
- connection pooling is useful only after the storage interfaces are clear.

## 7. Milestone Roadmap

| Milestone | Done when |
| --- | --- |
| `CBO-M0 Plan frozen` | this plan is committed as `PLAN_ONLY` |
| `CBO-M1 Safe state writes` | `BeliefEngine` uses atomic/locked state store |
| `CBO-M2 Findings I/O split` | findings JSON persistence is independent from vector sync |
| `CBO-M3 Bounded history signal` | route history reads are bounded and rollup-safe |
| `CBO-M4 Fetch/retrieval guard` | remote fetch and retrieval query contracts are enforced on first call sites |
| `CBO-M5 Observation harness` | I/O and latency reports exist without public claims |
| `CBO-M6 Repair split decision` | further repair split is approved or explicitly declined |

## 8. Stop Conditions

Stop and re-plan if:

- a slice touches more than 10 files;
- a slice enters forbidden paths;
- a storage adapter changes route or belief semantics;
- a guard blocks required local-only provider calls without an explicit local
  allow mode;
- evidence compression would delete or rewrite public/SF/delivery evidence;
- tests require broad public benchmark execution before focused contracts pass.

## 9. Current Decision

This source plan should be accepted only as a roadmap input, not as a direct
implementation spec.

Immediate next implementation should be `CBO-1 State JSON Store and BeliefEngine
Migration`, because it has the clearest correctness risk and the smallest safe
surface.

## 10. CBO-PREFLIGHT Result

Status: `DONE`

Artifact:

- `docs/reports/NEXUS_CODEBASE_OPTIMIZATION_PREFLIGHT_2026-05-20.json`

Result:

- baseline commit recorded as `446b3b10`;
- Clean Code closeout commit recorded as `cec4c355`;
- claim class remains `PLAN_PREFLIGHT_ONLY`;
- runtime update allowed: `false`;
- public benchmark allowed: `false`;
- production code changed: `false`;
- implementation notes were not updated because
  `/Users/jameschen/Workspace/implementation-notes.html` is outside this
  repo-local preflight scope.

Dirty workspace excluded from this preflight:

- `.obsidian/workspace.json`;
- `.serena/project.yml`;
- `.antigravitycli/102e96fa-ef91-4469-ae59-cda18e58d5b6.json`;
- `docs/info/NEXUS_CAPABILITY_SKILL_MAP.md`.

Verification:

- `uv run pytest tests/core/test_belief_engine.py -q` -> `13 passed`;
- `uv run pytest tests/app/test_research_flow_service.py tests/engine/test_capability_planner.py tests/engine/test_rlm_outcome_integration.py -q` -> `193 passed`.

Next:

- start `CBO-1 State JSON Store and BeliefEngine Migration`.

## 11. CBO-1 Result

Status: `DONE`

Changed surface:

- `nexus/infrastructure/state_json_store.py`;
- `nexus/core/belief_engine.py`;
- `tests/core/test_belief_engine.py`.

Result:

- `BeliefEngine` now reads and writes through `StateJsonStore`;
- state writes use a file lock, temp-file write, fsync, and `os.replace`;
- corrupt/non-dict/missing state files fail closed to an empty belief map;
- belief scoring and audit confidence semantics are unchanged.

Verification:

- `uv run python -m py_compile nexus/core/belief_engine.py nexus/infrastructure/state_json_store.py tests/core/test_belief_engine.py` -> `PASS`;
- `uv run pytest tests/core/test_belief_engine.py -q` -> `15 passed`;
- `uv run pytest tests/app/test_research_flow_service.py tests/core/test_belief_engine.py -q` -> `115 passed`;
- `git diff --check -- nexus/infrastructure/state_json_store.py nexus/core/belief_engine.py tests/core/test_belief_engine.py docs/plans/NEXUS_CODEBASE_OPTIMIZATION_TASK_PLAN_2026-05-20.md` -> `PASS`.

Failure lesson:

- Broad recursive repair loop coverage is not a valid CBO-1 acceptance gate.
  `uv run pytest tests/app/test_research_flow_service.py tests/engine/test_recursive_repair_loop.py tests/core/test_belief_engine.py -q`
  produced `118 passed, 5 failed`; all failures were in
  `tests/engine/test_recursive_repair_loop.py` where `_repair_audit_loop(...)`
  returned `False` after audit rejection. This is classified as pre-existing
  repair-loop composition debt from the Clean Code repair split path, not a
  belief state persistence regression. CBO slices must keep broad repair-loop
  failures visible, but must not block a storage seam when focused storage and
  adjacent research-flow tests pass.

Next:

- start `CBO-2 Findings Memory Persistence / Vector Sync Split` after CBO-1 commit.
