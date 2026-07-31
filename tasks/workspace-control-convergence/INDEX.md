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

## Current Frontier
`lifecycle-control-plane-workspace-convergence-recovery`

## Ready Cards
- `lifecycle-control-plane-workspace-convergence-recovery`: READY; the original Agy attempt failed at the credential transport layer, its dirty Target was preserved as salvage commit `3594db42873a0a8248203578372c6ba9410c83db`, and no Candidate was formed.

## Completed Cards
- None.

## Blocked Cards
- None.

## Superseded Cards
- `lifecycle-control-plane-workspace-convergence`: SUPERSEDED_BY `lifecycle-control-plane-workspace-convergence-recovery`; three Agy account-pool subprocesses exited 1 after orphaned `/usr/bin/security -i` credential pipes. Salvage ref `refs/nexus-salvage/worktree/lifecycle-control-plane-workspace-convergence-2e73a792d9144335999fea648e038479` preserves the unverified implementation.

## Task Dependencies
- `lifecycle-control-plane-workspace-convergence`: historical original attempt; no Candidate.
- `lifecycle-control-plane-workspace-convergence-recovery`: depends on the original Task Card, salvage commit `3594db42873a0a8248203578372c6ba9410c83db`, clean `nexus/integration/main`, zero active mutating workers, and independent reconstruction/verification rather than direct salvage promotion.

## Downstream Gate
A verified Candidate may proceed only to independent review. Approval, integration, live convergence apply, push, branch deletion, ref deletion, and historical worktree disposal remain separate owner-controlled gates.
