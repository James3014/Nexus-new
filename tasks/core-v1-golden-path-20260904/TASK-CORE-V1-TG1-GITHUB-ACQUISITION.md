# TASK-CORE-V1-TG1-GITHUB-ACQUISITION — Authenticated immutable PR acquisition

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
- **Source groups:** TG-1 Live GitHub acquisition
- **Requirements:** REQ-004
- **Acceptance:** AC-002
- **Auto-chain:** `false`
- **Maximum claim:** `LIVE_PR_SNAPSHOT_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG0-FREEZE-RECONCILE
- **Dependency unlock evidence:** TG-0 accepted receipt
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Implement a read-only authenticated GitHub PR acquisition seam that produces an immutable, credential-free, provenance-bound snapshot.

## Observable outcome

authenticated immutable PR snapshot

## Non-goals

No PR mutation, approval, merge, deployment, implementation-model call, or completion claim; no caller-only structural snapshot is trusted.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-003 | journey contribution | real PR remains read-only through exact snapshot |
| REQ-004 | acquisition behavior | authenticate when required and bind PR/base/head/tree/diff/check identities |
| AC-002 | live witness | independent identity re-read rejects drift, truncation, substitution, and caller-only objects |

## Owner decisions

DEC-002; DEC-007. Acquisition remains read-only and stores credential-free locator identity.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-0 accepted receipt, exact fresh source, clean isolated worktree, and read-only GitHub permission
- **Freshness rule:** re-read repository, PR, base/head/tree, pagination, and permissions immediately before acquisition and acceptance

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** stable Task ID with unique attempt; identical acquisition request replays same snapshot, changed request never reuses it
- **Reconnect reconciliation:** status/reconcile the same attempt before any retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker
- **Verification authority:** independent controller using live read-only probes
- **Receipt authority:** Evidence Trust ingestion and Completion receipt
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/adapters/github.py;product/evidence/__init__.py;product/evidence/ingestion.py;tests/product/test_github_adapter.py;tests/product/test_trusted_evidence_ingestion.py
- **Edit:** product/adapters/github.py;product/evidence/__init__.py
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 2
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** current adapter accepts pre-materialized snapshots and is not live acquisition.
- **Assumptions requiring verification:** supported GitHub auth/read API, pagination completeness representation, immutable diff retrieval, and permitted credential source.
- **Architecture risks:** adapter could mint trust or retain credentials.
- **Evidence risks:** a single fetch or caller-provided object is insufficient.
- **Missing owner decision:** none

## Mandatory source audit

Audit adapter contracts, evidence identity fields, current GitHub tests, read-only permission boundaries, pagination and moving-head behavior, and TG-0 contract receipt.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Negative probes must show moved head, incomplete pagination, substituted repository/diff, permission denial, and caller-only snapshots become non-certifiable.

## Implementation constraints

Persist only credential-free locator and revision/diff/check identities; never mutate GitHub or call an implementation model; keep acquisition separate from trust/completion ownership.

## GREEN and regression gates

AC-002 passes only after two independent identity reads agree and all hostile acquisition cases fail closed.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG1-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_github_adapter.py tests/product/test_trusted_evidence_ingestion.py` | acquisition and binding regression | all tests pass |
| TG1-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture attempt, authenticated method, credential-free locator hash, PR/base/head/tree/diff/check hashes, pagination completeness, observation time, source HEAD/tree, Candidate commit, and independent re-read receipt.

## Independent review

Fresh reviewer checks live read-only behavior, credential exclusion, identity binding, drift negatives, source diff, tests, and claim ceiling.

## Exit conditions

- **PASS:** Candidate and live receipt support `LIVE_PR_SNAPSHOT_VERIFIED`.
- **BLOCK:** auth/permission failure, moving head, incomplete data, or caller-only truth.
- **Residual debt:** no clean Python runner or product runtime yet.
- **Next gate:** TG-3 may consume the accepted acquisition contract after TG-2 also passes.
