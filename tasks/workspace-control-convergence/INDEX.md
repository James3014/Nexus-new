# Campaign Index: Workspace Control Convergence

artifact_authority: current
owner: James Chen
status: active_p6_owner_approved
source_specification: owner-authorized conversation on 2026-07-31
AUTO_CHAIN: false

## Campaign Overview
Converge Nexus workspace authority onto the clean integration controller and add one reusable, fail-closed execution slot without deleting evidence, rewriting history, or granting workers integration authority. P1-P5 and P7 implementation evidence is on `nexus/integration/main`; terminal lifecycle receipts are now archived through the formal archive API. On 2026-08-01 the owner explicitly approved worktree reconciliation, required valuable changes to be integrated, required redundant worktrees to be removed, and required `/Users/jameschen/Workspace/nexus` to become the sole daily entrypoint.

## Live Authority Reconciliation (2026-07-31)

- Controller: `/Users/jameschen/Workspace/nexus-worktrees/integration-main`, branch `nexus/integration/main`, HEAD `ba1fe9b6d59d9e47600d9a06babdd2f5a06a9fad`.
- Canonical root: `/Users/jameschen/Workspace/nexus`, branch `feature/full-capability-closure-20260718`, HEAD `a2185edb0e67e3fc9d6ed7169593d9d80bb1c03a`; it remains protected and is not a mutation Target.
- Current workspace inventory hash: `795ad3bd4832e4592e899888ef316419106879882f3ccf35765756b16259ec48`.
- Current convergence plan hash: `a285fd2045b352162d903ab1d73f4e2a7d2c3783a5cc9c546b811425bcf2e646`; `deletion_count: 0`; `AUTO_CHAIN: false`.
- Controller versus canonical divergence is 266 controller-only commits and 4 canonical-only commits; P6 remains a separate owner gate.
- `workspace-convergence-core-primitives` is formally `SUPERSEDED`; its salvage ref remains evidence-only and it is no longer an actionable retained receipt.
- `exact-authorized-deletion-contract-bootstrap` remains the only actionable owner decision: `RETAINED_FOR_REVIEW` / `FINAL_BLOCK`, with cleanup `REMOVED`; no candidate, close, or disposal is authorized by this index.

## Final Physical Cutover Verification (2026-08-01)

- Canonical daily entrypoint: `/Users/jameschen/Workspace/nexus`.
- Canonical branch: `nexus/integration/main`; cutover base commit: `33e925795b7be0205c750481365e63cd935e2a20` (`fix(tasks): bind convergence authority metadata`). The current evidence update is the next commit on this branch.
- Registered worktrees: `1`; exact path is the canonical root; `git worktree prune --dry-run` reports no stale metadata.
- Canonical dirty state: clean (`git status --short --branch` reports only `## nexus/integration/main`).
- Unregistered worktree root: `/Users/jameschen/Workspace/nexus-worktrees` is absent.
- Process/launcher state: no `devspace`, `nexus-worktrees`, or `nexus-8a1be3f4` process; `com.waishnav.devspace` is disabled in `gui/501`, and its plist is preserved at `/Users/jameschen/Workspace/nexus-salvage/20260801-root-convergence/com.waishnav.devspace.plist.disabled_20260801`.
- Retained refs: `70` `refs/nexus-salvage/*`, `33` `refs/heads/codex/*`, and `12` `refs/codex/turn-diffs/*`; salvage and branch deletion remain forbidden by this card.
- External preservation: root dirty archive, staged/unstaged patches, ignored residue archives, SymPy archive, and unregistered-worktree residue remain under `/Users/jameschen/Workspace/nexus-salvage/20260801-root-convergence/`.
- Gate evidence: bounded lifecycle suite `223 passed`; CI dry-run passed; startup contract passed with token `68c289a9474b3892`.
- Gate hardening commits `c6a6ffc6b` and `89379333f` make Ultra Review and route smoke use the active interpreter, ignore dangling runtime links, and avoid the restricted uv cache; focused suites are `18 passed` and `36 passed`, and CI strict reached a passing Ultra Review lane.
- Gate residuals: full pytest now collects cleanly (`11484 collected` after adding `jsonschema` to the local `.venv`), but the prior full execution reached `1806 passed / 29 failed` before hanging and interruption; acceptance is `UNVERIFIED_COLD_START` with zero samples; route smoke now produces evidence but P30 still fails capability receipt/public-safe gates; CI strict reaches Wiki Governance and reports `226 passed / 55 failed` legacy documentation contracts. These remain evidence blockers, not workspace residue.

## Ordered Cards
1. [00-lifecycle-control-plane-workspace-convergence.md](00-lifecycle-control-plane-workspace-convergence.md) - `lifecycle-control-plane-workspace-convergence`
2. [01-lifecycle-control-plane-workspace-convergence-recovery.md](01-lifecycle-control-plane-workspace-convergence-recovery.md) - `lifecycle-control-plane-workspace-convergence-recovery`
3. [02-workspace-convergence-core-primitives.md](02-workspace-convergence-core-primitives.md) - `workspace-convergence-core-primitives`
4. [03-workspace-convergence-service-orchestration.md](03-workspace-convergence-service-orchestration.md) - `workspace-convergence-service-orchestration`
5. [04-workspace-convergence-cli-surface.md](04-workspace-convergence-cli-surface.md) - `workspace-convergence-cli-surface`
6. [05-live-worktree-convergence-and-canonical-cutover.md](05-live-worktree-convergence-and-canonical-cutover.md) - `live-worktree-convergence-and-canonical-cutover`

## Current Frontier
`live-worktree-convergence-and-canonical-cutover`

## Ready Cards
- `live-worktree-convergence-and-canonical-cutover`: owner approved on 2026-08-01.

## Completed Cards
- `workspace-convergence-core-primitives`: historical owner-integrated evidence at `74808adb6`; the corresponding lifecycle receipt is now formally `SUPERSEDED`, with salvage preserved and no Candidate promotion.
- `workspace-convergence-service-orchestration`: owner-integrated at `eece9edd9`; service/workflow suite 109 passed; compact list and exact-bound dry-run/apply surfaces added.
- `workspace-convergence-cli-surface`: owner-integrated at `72dee3d5d`; CLI suite 28 passed; inventory/plan/slot/converge commands are dry-run-first.
- `commit-aware-candidate-capture`: `9afd8f0a2`; commit/verifier/worktree suites 120 passed; scoped Worker commits are now reusable without wrapper commits.
- `workspace-cleanup-and-soak`: evidence commit `0bf523260`; cleanup removed 13 clean redundant worktrees without deleting branches/refs; registered worktrees reduced from 29 to 16; P7 combined lifecycle suite 230 passed; ten sequential slot cycles passed.
- `terminal-receipt-archive-and-ghost-task-disposal`: evidence commit `61b571189`; formal archive API preserved 68 terminal receipts with 68/68 hash checks; `python-verification-isolation-guard` and `self-hosted-verification-entrypoint-final-amendment` were formally superseded by their documented successors; actionable tasks reduced from 10 to 2. Two retained records remain for evidence review.
- `read-only-status-lock-free-hardening`: `b975957dc` switched actionable/inventory state reads to atomic snapshots without creating or acquiring `.state.lock`; service/workflow and full P7 regression remained green at 109 and 230 passed.

## Blocked Cards
- Retained evidence requiring explicit owner decision: `exact-authorized-deletion-contract-bootstrap`. `workspace-convergence-core-primitives` is superseded and closed; its salvage ref remains evidence-only. No lifecycle JSON was edited manually.

## Superseded Cards
- `lifecycle-control-plane-workspace-convergence`: SUPERSEDED_BY `lifecycle-control-plane-workspace-convergence-recovery`; three Agy account-pool subprocesses exited 1 after orphaned `/usr/bin/security -i` credential pipes. Salvage ref `refs/nexus-salvage/worktree/lifecycle-control-plane-workspace-convergence-2e73a792d9144335999fea648e038479` preserves the unverified implementation.
- `lifecycle-control-plane-workspace-convergence-recovery`: SUPERSEDED_BY the bounded 02/03/04 card sequence; Codex `gpt-5.6-luna` was provider-blocked by usage quota before mutation, and OpenCode L1 may not receive the original unbounded eight-file task.

## Task Dependencies
- `lifecycle-control-plane-workspace-convergence`: historical original attempt; no Candidate.
- `lifecycle-control-plane-workspace-convergence-recovery`: historical Codex recovery attempt; no Candidate.
- `workspace-convergence-core-primitives`: historical owner-integrated commit `74808adb6`; formal lifecycle receipt `SUPERSEDED`, no Candidate record, salvage-only evidence retained.
- `workspace-convergence-service-orchestration`: owner-integrated commit `eece9edd9`; no auto-chain.
- `workspace-convergence-cli-surface`: owner-integrated commit `72dee3d5d`; no auto-chain.

## Downstream Gate
The 2026-08-01 owner approval authorizes the exact worktree cleanup and canonical-root cutover in card 05. It does not authorize push, remote mutation, protected-history rewrite, deletion of salvage refs, or disposal of `exact-authorized-deletion-contract-bootstrap`.
