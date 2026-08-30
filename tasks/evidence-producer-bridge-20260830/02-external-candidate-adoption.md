# TASK-EPB-002 — Core External Candidate Adoption Service

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
- **Supersedes:** none

## Goal

Add the core lifecycle service and distinct action contract needed to physically re-verify an exact immutable precommitted external-bootstrap Candidate and atomically create ordinary pending-approval Candidate state, without adding the public Gateway/CLI action yet.

## Observable outcome

Core service physically verifies an immutable precommitted Candidate and atomically forms pending-approval state

Against a clean exact-base/exact-Candidate snapshot, the real Gateway/service action validates every physical and authority binding, runs the existing lifecycle-native CandidateVerifier without invoking an implementation worker, and persists exactly one `PENDING_HUMAN_APPROVAL` Candidate packet; hostile substitutions and replay drift leave no promotable state.

## Non-goals

- No arbitrary trust-this-SHA import API.
- No EPB Candidate rewrite, worker rerun, patch copy, rebase, squash, cherry-pick, or replacement commit.
- No Candidate approval or integration inside adoption.
- No Task4, signing, issuer, trust-root, Product semantics, remote push/default merge, release, deployment, production, or public protocol work.
- No lifecycle JSON hand edit or second approval/integration authority.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| `DEC-001` | immutable subject authority | Preserve exact EPB Candidate without rewrite or substitution |
| `DEC-002` | lifecycle separation | Approval and integration remain unchanged downstream gates |
| `DEC-003` | claim and scope ceiling | No Task4, trust-root, Product semantic, release, production, or public-stability expansion |
| `CUR-001` | reproduced defect | R1 lifecycle state is absent |
| `CUR-003` | reproduced defect | External Candidate adoption surface is absent |
| `CUR-002` | physical evidence baseline | Candidate bindings are exact |
| `CUR-004` | physical evidence baseline | Historical validation receipt is not a lifecycle-native VerifiedCandidateReceipt |
| `CON-001` | canonical lifecycle contract | Exact commit/tree/state/receipt binding |
| `CON-002` | canonical lifecycle contract | No state hand editing; approval/integration remain separate |
| `REJ-001` | prohibited shortcut | Do not reuse failed task state or caller-mint lifecycle truth |
| `REQ-002` | implementation requirement | Exact immutable subject validation |
| `REQ-003` | implementation requirement | No worker and no Candidate mutation |
| `REQ-004` | implementation requirement | Lifecycle-native verification |
| `REQ-005` | implementation requirement | Atomic durable adoption |
| `REQ-006` | implementation requirement | Idempotency and reconciliation |
| `AC-002` | acceptance witness | No worker or rewrite |
| `AC-003` | acceptance witness | Replay and concurrency |
| `AC-005` | acceptance witness | Physical subject binding |
| `AC-006` | acceptance witness | Lifecycle-native verifier receipt |
| `AC-007` | acceptance witness | Atomic pending state |

## Owner decisions

- Owner master authorization SHA-256 `1adad9c3cc0356c6bd7d7babf41bf980664c3ed38253909642b78e4992572133` approves this exact spec and same-mission repair execution.
- The original EPB Candidate remains `b3343c95479f03857af7761381a1b839ac049e24` / tree `42a11a5f973e2ee46145d33ae48e339d564bd53c`.
- The repair Candidate is a different subject and may not replace the EPB Candidate.

## Source and start state

- **Workspace/root:** isolated worktree from `/Users/jameschen/Workspace/Nexus-new`
- **Branch:** `codex/epb-external-candidate-adoption`
- **Starting HEAD:** `a33fbd65b21ddf67085be9fa4ea245f59626ddd8`
- **Dirty baseline:** clean before Task Card compilation; only the committed Task Card/INDEX delta may precede implementation
- **Required initial verification:** re-read root, branch, HEAD, dirty state, Task Card path/hash, Gateway identity/action snapshot, Candidate/base object identity, and exact immutable receipt/acceptance artifacts
- **Freshness rule:** re-read after any reconnect, HEAD/dirty change, Gateway reload, lifecycle schema/manifest/permission movement, Candidate/artifact movement, or failed attempt

## MCP execution profile

- **App/server and action snapshot:** Nexus Gateway instance must be freshly rebound; loaded source at card compilation exposed lifecycle v2 and current candidate actions but not adoption
- **Exact required actions:** `nexus_task_run; nexus_task_wait; nexus_task_status; nexus_task_reconcile; nexus_task_finish`
- **Confirmation-required actions:** implementation Candidate creation only; adoption action requires a fresh one-shot Owner-bound action envelope
- **Idempotency and attempt rule:** one stable task ID; each repair attempt has a fresh attempt/action/idempotency identity; exact adoption replay returns the original receipt, while any input drift fails closed
- **Reconnect reconciliation:** re-read Gateway identity, lifecycle task state, Candidate ref/object, request hash, attempt/action/idempotency identities, and physical filesystem/Git effects before resume or retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** CapabilityPlanner plus current Workforce Admission
- **Execution authority:** Owner-authorized Primary Controller dispatching one eligible bounded implementation worker
- **Verification authority:** existing CandidateVerifier plus exact hostile tests and independent primary-controller rerun
- **Receipt authority:** existing lifecycle verifier/committer/state service; adoption receipt is a new typed evidence artifact, not approval authority
- **Approval/integration authority:** Primary Controller only under Owner master authorization after independent acceptance; worker has none

## Allowed scope

- **Read:** `AGENTS.md; tasks/evidence-producer-bridge-20260830/INDEX.md; tasks/evidence-producer-bridge-20260830/02-external-candidate-adoption.md; docs/specs/SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001.md; docs/agents/TASK_EXECUTION_CONTRACT.md; docs/governance/rollback_runbook.md; nexus/contracts/lifecycle_action.py; nexus/orchestrator/candidate_verifier.py; nexus/orchestrator/candidate_commit.py; nexus/orchestrator/self_hosted_task_service.py; nexus/orchestrator/unified_mcp_gateway.py; scripts/engine/nexus_cli.py`
- **Edit:** `nexus/contracts/lifecycle_action.py`; `nexus/orchestrator/self_hosted_task_service.py`; `tests/contracts/test_lifecycle_action.py`; `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- **Create:** `none`
- **Delete:** `none`
- **Maximum touched production files:** 2
- **Maximum touched test files:** 2

Governance files `tasks/evidence-producer-bridge-20260830/INDEX.md` and `tasks/evidence-producer-bridge-20260830/02-external-candidate-adoption.md` are compiled and committed by the Primary Controller before worker dispatch; the worker must not modify them.

## Unknown scan

- **Known facts:** Current public lifecycle cannot adopt an absent external Candidate task; existing approval requires persisted promotion bindings; Gateway transport is available; exact EPB Candidate and evidence exist.
- **Assumptions requiring verification:** Existing CandidateVerifier can validate a precommitted clean Target from exact base without creating a wrapper commit; the state service can atomically create absent-state adoption without weakening collision fencing.
- **Architecture risks:** accidental second approval authority; generic SHA import; mixing historical validation with lifecycle verifier truth; worker execution; Candidate rewrite; partial state; wrong canonical root; replay drift.
- **Evidence risks:** acceptance artifact not contained in the canonical evidence root; custom receipt missing lifecycle-native fields; verifier environment variance; caller-supplied state hash.
- **Missing owner decision:** none

## Mandatory source audit

- Inspect all `LifecycleActionType` consumers and approval/action guards before adding the new action.
- Trace Candidate state formation through CandidateVerifier, CandidateCommitter, promotion packet, durable state creation, status/action projection, approval, and integration.
- Verify no existing recovery/adoption seam already satisfies the contract.
- Inspect Gateway tool schema/handler and CLI compatibility tests.
- Run blast-radius analysis for `LifecycleActionType`, `SelfHostedTaskService`, and `UnifiedMCPGateway`; if unavailable, perform a bounded caller/test search and record the limitation.
- Preserve unrelated dirty state by working only in this isolated branch/worktree.

## Start-state classification

`DEFECT_REPRODUCED`

## RED or existing-guard proof

Before implementation, behavioral tests must demonstrate:

1. no public adoption action exists;
2. exact absent-state adoption cannot reach pending approval;
3. arbitrary SHA or Owner prose alone cannot create lifecycle state;
4. wrong task/card/attempt/repository/base/tree/diff/receipt/acceptance/runtime identity fails;
5. validation receipt cannot masquerade as VerifiedCandidateReceipt;
6. no worker/provider invocation is permitted;
7. Candidate mutation or wrapper commit fails;
8. partial/concurrent/replayed drift creates no split state;
9. adoption cannot approve, integrate, push, release, or activate;
10. old `TASK-EPB-001` negative evidence cannot be reused.

RED must fail because the required public behavior is absent, not because of import, fixture, or harness failure.

## Implementation constraints

- Add a distinct action type and typed closed schema; do not overload `CANDIDATE_APPROVE`.
- Derive volatile and physical values inside trusted code; caller values are assertions only.
- Use the existing CandidateVerifier and CandidateCommitter semantics; a clean precommitted Target must reuse the exact Candidate commit without a wrapper.
- Cross-check historical validation and independent acceptance artifacts, then derive lifecycle-native receipt/state from physical verification.
- Persist state atomically only after every gate passes; exact retry is idempotent and drift is rejected.
- End at `PENDING_HUMAN_APPROVAL`; unchanged approval/integration surfaces remain mandatory.
- Preserve public and production claim flags as false.

## GREEN and regression gates

- `AC-002`: Git SHA/tree are unchanged and implementation worker/provider invocation count for adoption is zero.
- `AC-003`: exact replay is idempotent; mismatched replay/concurrency fails closed without duplicate state.
- `AC-005`: every immutable Git/artifact binding is independently recomputed.
- `AC-006`: the existing CandidateVerifier produces lifecycle-native state and receipt evidence.
- `AC-007`: exactly one complete pending-approval state is atomically committed.
- Existing approval, integration, recovery, cancellation, status/action, Gateway freshness, and CLI tests remain green.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| `CMD-001` | TARGET_ROOT | `uv run pytest -q tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_self_hosted_task_service.py` | Focused behavior and regression verification | PASS |
| `CMD-002` | TARGET_ROOT | `uv run ruff check nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_self_hosted_task_service.py` | Static lint | PASS |
| `CMD-003` | TARGET_ROOT | `uv run pyright nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py` | Type verification | 0 errors |
| `CMD-004` | Task worktree root | `git diff --check` | Patch integrity | PASS |

## Physical evidence

- Exact worktree root, branch, starting HEAD/tree, dirty baseline, task-card path/hash, attempt/action/idempotency identities, worker/provider/model identity, and dispatch/admission receipt.
- RED and GREEN command evidence with exit codes and failing/passing nodes.
- Full changed-path/deletion/mode audit, diff SHA-256, Candidate commit/tree, candidate-state hash, lifecycle-native verified-receipt hash, adoption-receipt hash, and no-worker/no-downstream-effect evidence.
- Exact hostile-control results for all ten RED classes.
- Separate implementation-worker report and independent acceptance receipt; worker PASS is never acceptance.

## Independent review

A fresh reviewer distinct from the implementer must inspect the approved spec/card, complete physical diff, real positive adoption witness, all hostile controls, action/authority boundaries, exact Candidate preservation, lifecycle receipt derivation, idempotency/concurrency behavior, and unchanged downstream approval/integration semantics. Required disposition: `ACCEPT_CANDIDATE` or exact bounded rejection evidence.

## Exit conditions

- **PASS:** Exact repair Candidate is committed, all mandatory commands and hostile controls pass, no forbidden path/effect occurs, independent reviewer returns `ACCEPT_CANDIDATE`, and the active canonical integration/activation gate is freshly identified.
- **BLOCK:** Any authority ambiguity, Candidate rewrite, arbitrary trust import, caller-minted lifecycle truth, worker execution during adoption, partial state, receipt mismatch, unbounded path, weakened gate, or unresolved independent rejection.
- **Residual debt:** Original EPB Candidate still requires actual lifecycle adoption, approval, governed integration, remote/default merge, and post-merge verification after this repair is accepted and activated.
- **Next gate:** After independent acceptance/integration of this core service Candidate, rebind and activate `TASK-EPB-003` for the public Gateway/CLI action and final adoption witness.
