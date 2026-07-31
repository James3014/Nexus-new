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

## Current Frontier
`lifecycle-control-plane-workspace-convergence`

## Ready Cards
- `lifecycle-control-plane-workspace-convergence`: READY; controller is clean, no nonterminal lifecycle task exists, and the former OpenCode process holding the dirty canonical root was terminated normally on 2026-07-31.

## Completed Cards
- None.

## Blocked Cards
- None.

## Superseded Cards
- None.

## Task Dependencies
- `lifecycle-control-plane-workspace-convergence`: depends on clean `nexus/integration/main`, zero active mutating workers, preserved dirty-root baseline, and current self-hosted lifecycle controls.

## Downstream Gate
A verified Candidate may proceed only to independent review. Approval, integration, live convergence apply, push, branch deletion, ref deletion, and historical worktree disposal remain separate owner-controlled gates.
