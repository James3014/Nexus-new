# Bounded implementation

Baseline (historical): `a74d838cc6bb14af47ce79207181c12a1aed1d35`; prior
reconciled main (historical): `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`;
reconciled/current main: `cdf2570ede5ae218f36f886b696c8da45458043a`.

Rebind: non-destructive `merge --no-ff nexus-new/main` on the same branch;
exact head `c475c401415e42fdce8d24728814e46c1ea8c543` with parents
`dbe1b49d99ae9636cd96870c434aca0b0512f4b2` + `cdf2570ede5ae218f36f886b696c8da45458043a`;
exact 7 changed files / zero deletions; scoped blobs byte-identical to prior
accepted head.

Status: `ACTIVE`; frontier: `IMPLEMENTATION_ACTIVE`; terminal marker: none
(Owner KEEP_OPEN repair gate; VERIFIED/terminal status is not authorized).

Allowed files: `nexus/core/task_continuity.py`, `nexus/events/contracts.py`, `nexus/orchestrator/self_hosted_task_service.py`, `tests/core/test_task_continuity.py`, `tests/core/test_event_bus.py`, `tests/nexus/orchestrator/test_self_hosted_task_service.py`, and this campaign card plus `INDEX.md`.

Maximum changed files: 8; zero deletions.

Acceptance: typed privacy-safe events, deterministic projection, hash/identity/sequence fail-closed validation, and snapshot-tail resume preserving rejected strategies, evidence, next action, claim ceiling, exact continuity event type, strategy delta, risks, unknowns, and source/contract revisions. `ATTEMPT_REJECTED` must never fold into `OBSERVATION_RECORDED`; malformed or tampered continuity input fails closed.

The implementation must consume the existing `NexusEventBus`/`JsonlEventLogStore` durable append/read seam, including restart tail recovery, interleaved attempts, malformed/missing continuity fields, source/contract drift, snapshot/tail and sequence/parent/record-digest tamper rejection. Runtime reads the canonical log only; no second authority is introduced.

Forbidden: raw chain-of-thought, second state machine, route/workforce/lifecycle/verifier/approval/merge authority, production/corpus/workflow changes, #76 coupling, and any files outside the eight-file ceiling.

Verification: focused and relevant suites, Ruff on changed Python files, compileall with an explicit writable cache, `git diff --check`, staged scope/deletion audit, and exact-head CI. Do not self-accept or merge.

Repair lineage: the prior terminal receipt for PR #226 head
`49cba7ccf36daf39bafa6f5100436eac4103106a`, merge `a787e8e7`, exact 8-file
zero-deletion scope and 313 tests/checks. The G5 cross-agent continuity
finding (#117) is excluded. Claim ceiling is metadata/source-and-hostile-tests
only; no runtime, route, Workforce, provider, approval, integration, merge,
release, or production claim is made. Owner KEEP_OPEN repair gate remains
active pending independent re-acceptance; this card does not claim VERIFIED or
terminal status.
