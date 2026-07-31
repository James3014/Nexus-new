# Campaign Index: Bootstrap Authority Convergence

artifact_authority: current
owner: James Chen
status: active
source_specification: owner-authorized continuation of the 2026-07-31 bootstrap audit
AUTO_CHAIN: false

## Campaign Overview

Make Agent bootstrap stateful, worktree-local, and machine-verifiable after Workspace Convergence. The campaign separates task-authority freshness, cross-agent bootstrap cleanup, machine policy enforcement, startup gating, workforce query surfaces, and briefing reduction. It must not mutate the dirty canonical root or perform P6 cutover.

## Ordered Cards

1. [01-task-authority-freshness.md](01-task-authority-freshness.md) - `task-authority-freshness`
2. `bootstrap-path-convergence` - planned after P0-A
3. `machine-policy-contract` - planned after P0-A
4. `startup-freshness-gate` - planned after P0-A and P0-C
5. `workforce-compact-surface` - planned after P0-D
6. `briefing-overlay-reduction` - planned after P1 workforce surface

## Current Frontier

`task-authority-freshness`

## Ready Cards

- `task-authority-freshness`: READY; isolated implementation on clean `nexus/integration/main`.

## Completed Cards

- None.

## Blocked Cards

- P6 canonical root cutover remains a separate owner gate in `tasks/workspace-control-convergence/INDEX.md`.

## Campaign Boundaries

- Do not mutate `/Users/jameschen/Workspace/nexus`.
- Do not rewrite or delete historical task receipts.
- Do not create a second route authority; workforce work must consume existing Runtime Admission.
- Do not weaken Candidate, approval, integration, push, or cleanup authority.

## Downstream Gate

P0-B/P0-C/P0-D may start only after the P0-A validator has deterministic tests and a clean scoped commit. `AUTO_CHAIN=false`; completion never self-authorizes the next card.
