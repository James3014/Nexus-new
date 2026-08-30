# TASK-EPB-002-R1 — Scoped Core External Candidate Adoption Successor

- **Campaign:** `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- **Source spec SHA-256:** `9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1`
- **Source groups:** Core external Candidate adoption service
- **Requirements:** `REQ-002; REQ-003; REQ-004; REQ-005; REQ-006`
- **Acceptance:** `AC-002; AC-003; AC-005; AC-006; AC-007`
- **Auto-chain:** `false`
- **Maximum claim:** Core lifecycle adoption service independently verified; no public Gateway action, EPB adoption, approval, integration, or remote claim.
- **Depends on:** none
- **Dependency unlock evidence:** none
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `TASK-EPB-002`

## Goal

Recompose the settled core adoption implementation as an exact eight-path successor that includes only the lifecycle contract/service, immutable precommitted CandidateCommitter and WorktreeManager support, and their focused tests.

## Observable outcome

Core service physically verifies an immutable precommitted Candidate and atomically forms pending-approval state

## Non-goals

No public Gateway/CLI action, Agy probe change, Product Candidate modification, approval, integration, merge, push, reload, release, production, Task4, signing, trust root, or public claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| `REQ-002` | physical binding | Exact base/commit/tree/diff/task/card/evidence |
| `REQ-003` | immutability | Zero worker execution during adoption; zero rewrite |
| `REQ-004` | native verification | Existing CandidateVerifier/Committer semantics |
| `REQ-005` | atomic lifecycle | Complete pending state only after all gates |
| `REQ-006` | recovery | Idempotent replay; drift/concurrency fail closed |
| `AC-002` | witness | Exact Candidate preserved |
| `AC-003` | witness | Replay/concurrency/crash controls |
| `AC-005` | witness | Physical evidence recomputed |
| `AC-006` | witness | Lifecycle-native receipt/state hash |
| `AC-007` | witness | One complete pending state |

## Owner decisions

Owner master authorization allows same-mission corrected Task Cards and repair Candidates. Owner decision SHA-256 `18d0dcaa4e9fc80c984f0daa42bb67359eba9c0dc66f23902c1051757bd6ef1c` preserves `b3343c95479f03857af7761381a1b839ac049e24` as historical `REJECTED/SUPERSEDED` evidence and makes `d70cdce975ca8394606d54d1492506cf5e392e4d` the later Product adoption subject.

## Source and start state

- **Workspace/root:** `/private/tmp/nexus-epb-core-r1`
- **Branch:** `codex/epb-core-adoption-r1`
- **Starting HEAD:** `ee3558a65a416f55ac59e9060496c00df642d16a`
- **Dirty baseline:** clean before controller-authored recomposition bundle
- **Required initial verification:** root/branch/HEAD/tree/status, spec/card hashes, historical exact eight-file projection
- **Freshness rule:** re-read after HEAD/status/toolchain/card/evidence movement

## MCP execution profile

- **App/server and action snapshot:** implementation only; no live lifecycle mutation
- **Exact required actions:** `nexus_task_run; nexus_task_wait; nexus_task_status; nexus_task_reconcile; nexus_task_finish`
- **Confirmation-required actions:** Candidate commit only
- **Idempotency and attempt rule:** fresh successor attempt; failed Candidate retained, never amended
- **Reconnect reconciliation:** re-read exact Git/files/test state before resume
- **Transport blocker:** none

## Authority map

- **Selection authority:** Primary Controller under Owner mission authority
- **Execution authority:** one bounded Luna implementation worker
- **Verification authority:** physical tests and independent reviewer
- **Receipt authority:** validation and independent Candidate acceptance receipts
- **Approval/integration authority:** none in this card

## Allowed scope

- **Read:** approved spec; this bundle; historical `a33fbd65..a20712a5` source; affected tests
- **Edit:** `nexus/contracts/lifecycle_action.py`; `nexus/orchestrator/candidate_commit.py`; `nexus/orchestrator/self_hosted_task_service.py`; `nexus/orchestrator/worktree_manager.py`; `tests/contracts/test_lifecycle_action.py`; `tests/nexus/orchestrator/test_candidate_commit.py`; `tests/nexus/orchestrator/test_self_hosted_task_service.py`; `tests/nexus/orchestrator/test_worktree_manager.py`
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 4
- **Maximum touched test files:** 4

## Unknown scan

- **Known facts:** cumulative `a20712a5` was freshly rejected as a core Candidate; forensic decomposition proves eight necessary implementation/test paths.
- **Assumptions requiring verification:** exact a207 path projection preserves core behavior without excluded Agy/Gateway probe changes.
- **Architecture risks:** missing prerequisite, arbitrary trust import, caller-minted state, Candidate rewrite, partial state, replay drift.
- **Evidence risks:** baseline diagnostics misclassified as regressions.
- **Missing owner decision:** none

## Mandatory source audit

Trace precommitted Candidate commit reuse, post-verification drift protection, lease/CAS/rollback, physical verifier inputs, artifact storage, state reservation/finalization, replay, and retained negative evidence. Confirm no public action/probe delta enters the Candidate.

## Start-state classification

`DEFECT_REPRODUCED`

## RED or existing-guard proof

Fresh rejection of the mixed-scope `a20712a5` tip proves the scoped Candidate contract is not satisfied. The successor must retain the same behavior with exactly eight implementation/test paths.

## Implementation constraints

Apply only the exact semantic projection of the identified historical core commits. Preserve exact Candidate identity during adoption, derive truth inside trusted code, and stop at pending approval. Do not modify public Gateway/CLI, route policy, Agy probes, Task4, Product Candidate content, or downstream authority.

## GREEN and regression gates

Exact eight-path diff; no deletion/mode change; positive immutable adoption; replay/concurrency/rollback/forensic hostile controls; zero worker invocation; zero approval/integration/push/reload effect; exact-base diagnostic classification.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| `CMD-001` | TARGET_ROOT | `/Users/jameschen/Workspace/Nexus-new/.venv/bin/pytest -q tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_worktree_manager.py` | Core behavior and hostile regression | PASS or exact-base-identical baseline only |
| `CMD-002` | TARGET_ROOT | `/Users/jameschen/Workspace/Nexus-new/.venv/bin/ruff check nexus/contracts/lifecycle_action.py nexus/orchestrator/candidate_commit.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/worktree_manager.py tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_worktree_manager.py` | Static lint | Zero introduced/touched-line diagnostics; baseline classified |
| `CMD-003` | TARGET_ROOT | `/Users/jameschen/Workspace/Nexus-new/.venv/bin/pyright nexus/contracts/lifecycle_action.py nexus/orchestrator/candidate_commit.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/worktree_manager.py` | Type verification | Zero introduced/touched-line diagnostics; baseline classified |
| `CMD-004` | TARGET_ROOT | `git diff --check` | Patch integrity | PASS |

## Physical evidence

Exact governance base, Candidate commit/tree/diff, paths/deletions/modes, spec/card hashes, test and diagnostic evidence, validation receipt, worker identity, and independent acceptance receipt.

## Independent review

A fresh reviewer must inspect the eight-path diff, positive adoption, hostile controls, CandidateCommitter/WorktreeManager prerequisites, no-worker/no-downstream effects, and exact-base diagnostics. Required disposition: `ACCEPT_CANDIDATE` or exact rejection.

## Exit conditions

- **PASS:** scoped successor committed, mandatory gates pass or are exact-base-only, independent reviewer returns `ACCEPT_CANDIDATE`.
- **BLOCK:** unrelated path, rewrite, generic trust import, caller-minted truth, partial state, weakened guard, or unresolved rejection.
- **Residual debt:** public successor, Product adoption/approval, local integration, GitHub merge, post-merge verification.
- **Next gate:** Activate `TASK-EPB-003-R1` against the accepted core successor.
