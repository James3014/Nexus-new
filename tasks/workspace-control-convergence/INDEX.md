# Campaign Index: Workspace Control Convergence

artifact_authority: current
owner: James Chen
status: active_p6_owner_gate
source_specification: owner-authorized conversation on 2026-07-31
AUTO_CHAIN: false

## Campaign Overview
Converge Nexus workspace authority onto the clean integration controller and add one reusable, fail-closed execution slot without deleting evidence, rewriting history, or granting workers integration authority. P1-P5 and P7 implementation evidence is on `nexus/integration/main`; terminal lifecycle receipts are now archived through the formal archive API; P6 canonical-root cutover remains an owner gate because the legacy root is dirty and the histories diverge.

## Ordered Cards
1. [00-lifecycle-control-plane-workspace-convergence.md](00-lifecycle-control-plane-workspace-convergence.md) - `lifecycle-control-plane-workspace-convergence`
2. [01-lifecycle-control-plane-workspace-convergence-recovery.md](01-lifecycle-control-plane-workspace-convergence-recovery.md) - `lifecycle-control-plane-workspace-convergence-recovery`
3. [02-workspace-convergence-core-primitives.md](02-workspace-convergence-core-primitives.md) - `workspace-convergence-core-primitives`
4. [03-workspace-convergence-service-orchestration.md](03-workspace-convergence-service-orchestration.md) - `workspace-convergence-service-orchestration`
5. [04-workspace-convergence-cli-surface.md](04-workspace-convergence-cli-surface.md) - `workspace-convergence-cli-surface`

## Current Frontier
`P6-canonical-root-cutover-readiness`

## Ready Cards
- None; P6 requires owner cutover decision after readiness evidence.

## Completed Cards
- `workspace-convergence-core-primitives`: owner-integrated at `74808adb6`; core manager suite 66 passed; worker lifecycle state remains retained for review because the original capture contract rejected worker commits.
- `workspace-convergence-service-orchestration`: owner-integrated at `eece9edd9`; service/workflow suite 109 passed; compact list and exact-bound dry-run/apply surfaces added.
- `workspace-convergence-cli-surface`: owner-integrated at `72dee3d5d`; CLI suite 28 passed; inventory/plan/slot/converge commands are dry-run-first.
- `commit-aware-candidate-capture`: `9afd8f0a2`; commit/verifier/worktree suites 120 passed; scoped Worker commits are now reusable without wrapper commits.
- `workspace-cleanup-and-soak`: cleanup removed 13 clean redundant worktrees without deleting branches/refs; registered worktrees reduced from 29 to 16; P7 combined lifecycle suite 230 passed; ten sequential slot cycles passed.
- `terminal-receipt-archive-and-ghost-task-disposal`: formal archive API preserved 68 terminal receipts with 68/68 hash checks; `python-verification-isolation-guard` and `self-hosted-verification-entrypoint-final-amendment` were formally superseded by their documented successors; actionable tasks reduced from 10 to 2. Two retained records remain for evidence review.
- `read-only-status-lock-free-hardening`: `b975957dc` switched actionable/inventory state reads to atomic snapshots without creating or acquiring `.state.lock`; service/workflow and full P7 regression remained green at 109 and 230 passed.

## Blocked Cards
- `P6-canonical-root-cutover-readiness`: HARD_BLOCK_OWNER_GATE; root `feature/full-capability-closure-20260718` remains dirty (117 porcelain entries), differs from integration by 4 root-only vs 245 integration-only commits / 178 files, and remote `HEAD` does not point to this controller. No reset, stash, clean, merge, or cutover was performed.
- Retained evidence requiring explicit successor/owner decision: `exact-authorized-deletion-contract-bootstrap` and `workspace-convergence-core-primitives`. They remain visible through the formal actionable surface; no JSON was edited manually.

## Superseded Cards
- `lifecycle-control-plane-workspace-convergence`: SUPERSEDED_BY `lifecycle-control-plane-workspace-convergence-recovery`; three Agy account-pool subprocesses exited 1 after orphaned `/usr/bin/security -i` credential pipes. Salvage ref `refs/nexus-salvage/worktree/lifecycle-control-plane-workspace-convergence-2e73a792d9144335999fea648e038479` preserves the unverified implementation.
- `lifecycle-control-plane-workspace-convergence-recovery`: SUPERSEDED_BY the bounded 02/03/04 card sequence; Codex `gpt-5.6-luna` was provider-blocked by usage quota before mutation, and OpenCode L1 may not receive the original unbounded eight-file task.

## Task Dependencies
- `lifecycle-control-plane-workspace-convergence`: historical original attempt; no Candidate.
- `lifecycle-control-plane-workspace-convergence-recovery`: historical Codex recovery attempt; no Candidate.
- `workspace-convergence-core-primitives`: owner-integrated commit `74808adb6`; no formal Candidate record was created from the historical retained task.
- `workspace-convergence-service-orchestration`: owner-integrated commit `eece9edd9`; no auto-chain.
- `workspace-convergence-cli-surface`: owner-integrated commit `72dee3d5d`; no auto-chain.

## Downstream Gate
P6 owner decision is required before any canonical-root mutation. Approval, push, branch deletion, ref deletion, remaining retained-evidence disposal, and dirty/unique worktree disposal remain separate owner-controlled gates.
