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
2. [02-bootstrap-path-convergence.md](02-bootstrap-path-convergence.md) - `bootstrap-path-convergence`
3. [03-machine-policy-contract.md](03-machine-policy-contract.md) - `machine-policy-contract`
4. `startup-freshness-gate` - planned after P0-C
5. `workforce-compact-surface` - planned after P0-D
6. `briefing-overlay-reduction` - planned after P1 workforce surface

## Current Frontier

`machine-policy-contract`

## Ready Cards

- `machine-policy-contract`: READY; P0-B bootstrap authority files integrated at `70945794c` and focused tests passed.

## Completed Cards

- `task-authority-freshness`: INTEGRATED_WITH_OWNER_REVIEW at `e7d4b876b`; 7 focused tests passed and live validator returned `PASS` with `dirty=false`.
- `bootstrap-path-convergence`: INTEGRATED_WITH_OWNER_REVIEW at `70945794c`; 2 focused tests passed and no forbidden bootstrap tokens remain in the scoped file set.

## Blocked Cards

- P6 canonical root cutover remains a separate owner gate in `tasks/workspace-control-convergence/INDEX.md`.

## Campaign Boundaries

- Do not mutate `/Users/jameschen/Workspace/nexus`.
- Do not rewrite or delete historical task receipts.
- Do not create a second route authority; workforce work must consume existing Runtime Admission.
- Do not weaken Candidate, approval, integration, push, or cleanup authority.

## Downstream Gate

P0-C may start only after P0-A and P0-B have deterministic tests and clean scoped commits. `AUTO_CHAIN=false`; completion never self-authorizes the next card.
