# Campaign Index: Workspace Control Convergence

artifact_authority: current
owner: James Chen
status: active
source_specification: owner-authorized conversation on 2026-07-31
AUTO_CHAIN: false

## Campaign Overview
Converge Nexus workspace authority onto the clean integration controller and add one reusable, fail-closed execution slot without deleting evidence, rewriting history, or granting workers integration authority.

## Ordered Cards
1. [00-lifecycle-control-plane-workspace-convergence.md](00-lifecycle-control-plane-workspace-convergence.md) - `lifecycle-control-plane-workspace-convergence`
2. [01-lifecycle-control-plane-workspace-convergence-recovery.md](01-lifecycle-control-plane-workspace-convergence-recovery.md) - `lifecycle-control-plane-workspace-convergence-recovery`
3. [02-workspace-convergence-core-primitives.md](02-workspace-convergence-core-primitives.md) - `workspace-convergence-core-primitives`
4. [03-workspace-convergence-service-orchestration.md](03-workspace-convergence-service-orchestration.md) - `workspace-convergence-service-orchestration`
5. [04-workspace-convergence-cli-surface.md](04-workspace-convergence-cli-surface.md) - `workspace-convergence-cli-surface`

## Current Frontier
`workspace-convergence-core-primitives`

## Ready Cards
- `workspace-convergence-core-primitives`: READY; bounded two-file L1 implementation slice. OpenCode MiMo `opencode/mimo-v2.5-free` passed a live read-only smoke on 2026-07-31.

## Completed Cards
- None.

## Blocked Cards
- `workspace-convergence-service-orchestration`: BLOCKED_ON_DEPENDENCY until `workspace-convergence-core-primitives` is independently reviewed and integrated.
- `workspace-convergence-cli-surface`: BLOCKED_ON_DEPENDENCY until `workspace-convergence-service-orchestration` is independently reviewed and integrated.

## Superseded Cards
- `lifecycle-control-plane-workspace-convergence`: SUPERSEDED_BY `lifecycle-control-plane-workspace-convergence-recovery`; three Agy account-pool subprocesses exited 1 after orphaned `/usr/bin/security -i` credential pipes. Salvage ref `refs/nexus-salvage/worktree/lifecycle-control-plane-workspace-convergence-2e73a792d9144335999fea648e038479` preserves the unverified implementation.
- `lifecycle-control-plane-workspace-convergence-recovery`: SUPERSEDED_BY the bounded 02/03/04 card sequence; Codex `gpt-5.6-luna` was provider-blocked by usage quota before mutation, and OpenCode L1 may not receive the original unbounded eight-file task.

## Task Dependencies
- `lifecycle-control-plane-workspace-convergence`: historical original attempt; no Candidate.
- `lifecycle-control-plane-workspace-convergence-recovery`: historical Codex recovery attempt; no Candidate.
- `workspace-convergence-core-primitives`: clean Controller plus read-only salvage evidence.
- `workspace-convergence-service-orchestration`: integrated core-primitives Candidate.
- `workspace-convergence-cli-surface`: integrated service-orchestration Candidate.

## Downstream Gate
A verified Candidate may proceed only to independent review. Approval, integration, live convergence apply, push, branch deletion, ref deletion, and historical worktree disposal remain separate owner-controlled gates.
