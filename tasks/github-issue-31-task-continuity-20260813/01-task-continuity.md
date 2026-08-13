# Bounded implementation

Baseline: `a74d838cc6bb14af47ce79207181c12a1aed1d35`.

Allowed files: `nexus/core/task_continuity.py`, `nexus/events/contracts.py`, `nexus/orchestrator/self_hosted_task_service.py`, `tests/core/test_task_continuity.py`, `tests/core/test_event_bus.py`, `tests/nexus/orchestrator/test_self_hosted_task_service.py`, and this campaign card plus `INDEX.md`.

Maximum changed files: 8; zero deletions.

Acceptance: typed privacy-safe events, deterministic projection, hash/identity/sequence fail-closed validation, and snapshot-tail resume preserving rejected strategies, evidence, next action, and claim ceiling.

The implementation must consume the existing `NexusEventBus`/`JsonlEventLogStore` durable append/read seam, including restart tail recovery, interleaved attempts, malformed/missing continuity fields, source/contract drift, snapshot/tail and sequence/parent/record-digest tamper rejection. Runtime reads the canonical log only; no second authority is introduced.

Forbidden: raw chain-of-thought, second state machine, route/workforce/lifecycle/verifier/approval/merge authority, production/corpus/workflow changes, #76 coupling, and any files outside the eight-file ceiling.

Verification: focused and relevant suites, Ruff on changed Python files, compileall with an explicit writable cache, `git diff --check`, staged scope/deletion audit, and exact-head CI. Do not self-accept or merge.
