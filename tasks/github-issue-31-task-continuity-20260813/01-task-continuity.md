# Bounded implementation

Baseline (historical): `a74d838cc6bb14af47ce79207181c12a1aed1d35`; prior
reconciled main (historical): `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`;
reconciled/current main: `cdf2570ede5ae218f36f886b696c8da45458043a`.

Prior rebind (historical): non-destructive merge head
`c475c401415e42fdce8d24728814e46c1ea8c543` with parents
`dbe1b49d99ae9636cd96870c434aca0b0512f4b2` + `cdf2570ede5ae218f36f886b696c8da45458043a`;
that head was superseded by the rejected candidate `c603fd8d8fad62523deff74e2d0c47e4e5aa78c1`.

Prior repair candidate `41351277b0c22a1bf890f0f9cf67e9a683cc2668`
(parent `c603fd8d8fad62523deff74e2d0c47e4e5aa78c1`) is retained as rejected
history. The current semantic repair candidate is
`7e14303927be3235ad05493574a46e975bb759c9` (parent
`ee673dc93a6de9505414f23d498637293b306827`); it changes exactly 4 code/test
files, with this card and `INDEX.md` updated afterward to bind that candidate,
and has zero deletions. No terminal acceptance is claimed; the Owner KEEP_OPEN
gate remains active.

Bounded repair deltas:
1. Canonical `failure_reason` persists producer -> payload -> decoder ->
   projection -> replay from the single `reason` field, while `observation`
   remains an independent channel and alone contributes verified facts.
2. Supported `REJECTED` lifecycle state maps to `ATTEMPT_REJECTED`; rejected
   transitions with missing or explicit `OBSERVATION_RECORDED` continuity type
   fail closed at both the producer and the decoder.
3. Scalar strings/bytes, mappings, malformed elements, and collections above
   the shared 64-item ceiling fail closed; exact-boundary canonical string
   sequences remain accepted deterministically.
4. The producer, event contract, decoder, and projection consume one shared
   `MAX_CONTINUITY_COLLECTION_ITEMS` authority; no second schema or state
   machine is introduced.

Hostile regression witnesses in `tests/core/test_task_continuity.py` and
`tests/core/test_event_bus.py` include real JSONL append -> canonical read ->
decode -> project -> resume coverage preserving `ATTEMPT_REJECTED`,
`failure_reason`, `observation`, and `do_not_repeat`, plus scalar/malformed and
64/65 boundary probes. Current semantic repair evidence: 88 focused tests,
compileall, Ruff check, and `git diff --check` pass. Ruff preview-format debt
in the touched files is byte-identical to the repair parent; no added line is
formatter-flagged. The earlier 291 self-hosted and lifecycle evidence remains
historical and is not reasserted as a fresh run for this candidate.

Status: `ACTIVE`; frontier: `ACCEPTED_CANDIDATE_PENDING_OWNER_MERGE_SLOT`;
terminal marker: none (physical merge and post-merge readback are still
required; VERIFIED/terminal status is not authorized).

Allowed files: `nexus/core/task_continuity.py`, `nexus/events/contracts.py`, `nexus/orchestrator/self_hosted_task_service.py`, `tests/core/test_task_continuity.py`, `tests/core/test_event_bus.py`, `tests/nexus/orchestrator/test_self_hosted_task_service.py`, and this campaign card plus `INDEX.md`.

Maximum changed files: 8; zero deletions.

Acceptance: typed privacy-safe events, deterministic projection, hash/identity/sequence fail-closed validation, and snapshot-tail resume preserving rejected strategies, evidence, next action, claim ceiling, exact continuity event type, strategy delta, risks, unknowns, and source/contract revisions. `ATTEMPT_REJECTED` must never fold into `OBSERVATION_RECORDED`; malformed or tampered continuity input fails closed.

The implementation must consume the existing `NexusEventBus`/`JsonlEventLogStore` durable append/read seam, including restart tail recovery, interleaved attempts, malformed/missing continuity fields, source/contract drift, snapshot/tail and sequence/parent/record-digest tamper rejection. Runtime reads the canonical log only; no second authority is introduced.

Forbidden: raw chain-of-thought, second state machine, route/workforce/lifecycle/verifier/approval/merge authority, production/corpus/workflow changes, #76 coupling, and any files outside the eight-file ceiling.

Verification: focused and relevant suites, Ruff on changed Python files, compileall with an explicit writable cache, `git diff --check`, staged scope/deletion audit, and exact-head CI. Do not self-accept or merge.

Independent acceptance evidence: DeepSeek hostile re-acceptance at exact head
`bec5dff16d5e424231a45ff29e6dbb9c436eb521` recomputed semantic repair diff
SHA-256 `1278df8dc1b2b9b9c2ca91a5683192b4ed33235479098dba57277503b0674a8a`,
verified the observation/failure-reason separation, the shared 64-item ceiling,
and `ATTEMPT_REJECTED` fail-closed behavior; 88 focused tests and exact-head CI
passed.

Distinct-model canary evidence: fresh Workforce Admission returned `ALLOW` for
`codex_luna` / `gpt-5.6-luna` with policy hash
`8bc154848ac95b2478045c0d4568fcbb208263d4f46232d8b671a88b4a13bdca`.
A read-only producer canary generated a current-code artifact (SHA-256
`1af901590d92337db153a679207dd8343efd9a54e2e9974e846c0ebc8709fa2f`)
through `SelfHostedTaskService`, `JsonlEventLogStore`, decode, projection,
resume, restart/tail recovery, and hostile tamper probes. A separate fresh Luna
consumer received only that artifact, preserved rejected `strategy-a`, risks,
unknowns, next action, and claim ceiling, selected `strategy-b`, and reported
`repeats_rejected_strategy=false`. This satisfies the Owner's distinct-agent
artifact-consumption gate but does not claim merge or terminal state.

Repair lineage: the prior terminal receipt for PR #226 head
`49cba7ccf36daf39bafa6f5100436eac4103106a`, merge `a787e8e7`, exact 8-file
zero-deletion scope and 313 tests/checks. The G5 cross-agent continuity
finding (#117) is excluded. Claim ceiling is metadata/source-and-hostile-tests
only; no runtime, route, Workforce, provider, approval, integration, merge,
release, or production claim is made. Owner KEEP_OPEN repair gate remains
active only as a physical-merge fence: Candidate re-acceptance and the fresh
distinct-model artifact canary passed, while Owner merge slot and post-merge
readback remain pending. This card does not claim VERIFIED or terminal status.
