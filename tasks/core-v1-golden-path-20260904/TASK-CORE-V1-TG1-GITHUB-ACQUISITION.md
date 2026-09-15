# TASK-CORE-V1-TG1-GITHUB-ACQUISITION — Authenticated immutable PR acquisition

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#765`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
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
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
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
- **Required initial verification:** verify TG-0 accepted receipt and Candidate source in the exact controller-bound starting HEAD/tree, clean isolated worktree, and read-only GitHub permission; this card's `Parallel safe: false` forbids auto-start but the separate Owner/controller contract permits concurrent TG-1/TG-2 dispatch as distinct Ready Issues
- **Freshness rule:** re-read repository, PR, base/head/tree, pagination, and permissions immediately before acquisition and acceptance

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #765
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** one bounded Luna attempt on an issue-specific isolated worktree; identical acquisition request replays the same snapshot, changed request never reuses it
- **Reconnect reconciliation:** controller re-reads the same worker/session, filesystem, Git, provider, and live-probe state before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller using live read-only probes; worker PASS is not acceptance
- **Receipt authority:** Evidence Trust ingestion and Completion receipt
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/adapters/github.py;product/evidence/__init__.py;product/evidence/ingestion.py;tests/product/test_github_adapter.py;tests/product/test_trusted_evidence_ingestion.py
- **Edit:** none
- **Create:** product/acquisition/__init__.py;product/acquisition/github.py;tests/product/test_github_acquisition.py
- **Delete:** none
- **Maximum touched production files:** 2
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** current adapter accepts pre-materialized snapshots and is not live acquisition.
- **Assumptions requiring verification:** supported GitHub auth/read API, pagination completeness representation, immutable diff retrieval, and permitted credential source.
- **Architecture risks:** acquisition could be placed in the pure pre-materialized adapter, mint trust, or retain credentials.
- **Evidence risks:** a single fetch or caller-provided object is insufficient.
- **Missing owner decision:** none

## Mandatory source audit

Audit adapter contracts, evidence identity fields, current GitHub tests, read-only permission boundaries, pagination and moving-head behavior, and TG-0 contract receipt. Preserve `product/adapters/github.py` as pure pre-materialized mapping; put network acquisition only in the new carrying layer.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Negative probes must show moved head, incomplete pagination, substituted repository/diff/tree/check data, permission denial, forged envelopes, and caller-only snapshots become non-certifiable.

## Implementation constraints

Create a separate injected, credential-safe read port in `product/acquisition/github.py`; persist only credential-free locator and repository/PR/base/head commit and tree/merge-base-policy/diff bytes and hash/changed and deleted path/check/pagination-completeness/observation/freshness-CAS identities. Never modify the pure adapter, persist/log credentials, pass credentials to Luna, mutate GitHub, or call an implementation model. Keep acquisition separate from trust/completion ownership.

## GREEN and regression gates

AC-002 passes only after two independent identity reads agree and all hostile acquisition cases fail closed.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG1-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_github_acquisition.py tests/product/test_github_adapter.py tests/product/test_trusted_evidence_ingestion.py` | acquisition, compatibility, and binding regression | all tests pass |
| TG1-02 | TARGET_ROOT | `uv run pytest --collect-only -q tests/product/test_github_acquisition.py` | prove dedicated hostile tests are discovered | exit 0 with intended tests listed |
| TG1-03 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture attempt, authenticated method, credential-free locator hash, PR/base/head commits and trees, merge-base policy, diff byte/hash, changed/deleted paths, check hashes, pagination completeness, observation time, freshness/CAS, source HEAD/tree, Candidate commit, and independent two-read receipt. Controller live probe uses controlled PR #635; no secret may appear in worker input or persisted evidence.

## Independent review

Fresh reviewer checks live read-only behavior, credential exclusion, identity binding, drift negatives, source diff, tests, and claim ceiling.

## Exit conditions

- **PASS:** Candidate and live receipt support `LIVE_PR_SNAPSHOT_VERIFIED`.
- **BLOCK:** auth/permission failure, moving head, incomplete data, or caller-only truth.
- **Residual debt:** no clean Python runner or product runtime yet.
- **Next gate:** after TG-1 and TG-2 independently pass, the controller binds both exact accepted Candidate commits/trees into TG-3's clean integration base before dispatch.
