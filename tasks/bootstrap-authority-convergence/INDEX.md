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
4. [04-startup-freshness-gate.md](04-startup-freshness-gate.md) - `startup-freshness-gate`
5. [05-workforce-compact-surface.md](05-workforce-compact-surface.md) - `workforce-compact-surface`
6. [06-briefing-overlay-reduction.md](06-briefing-overlay-reduction.md) - `briefing-overlay-reduction`
7. [07-workspace-retry-and-permission-gate.md](07-workspace-retry-and-permission-gate.md) - `workspace-retry-and-permission-gate`
8. [08-orphan-workspace-reconciliation.md](08-orphan-workspace-reconciliation.md) - `orphan-workspace-reconciliation`

## Current Frontier

`orphan-workspace-reconciliation`

## Ready Cards

- `orphan-workspace-reconciliation`: planned; current live inventory shows dirty/unmapped worktrees that must remain protected until exact owner-approved plan/hash cleanup.

## Completed Cards

- `task-authority-freshness`: INTEGRATED_WITH_OWNER_REVIEW at `e7d4b876b`; 7 focused tests passed and live validator returned `PASS` with `dirty=false`.
- `bootstrap-path-convergence`: INTEGRATED_WITH_OWNER_REVIEW at `70945794c`; 2 focused tests passed and no forbidden bootstrap tokens remain in the scoped file set.
- `machine-policy-contract`: INTEGRATED_WITH_OWNER_REVIEW at `09af43a78`; 13 focused tests passed, missing/malformed baseline fails closed, and overlay narrowing passed.
- `startup-freshness-gate`: INTEGRATED_WITH_OWNER_REVIEW at `f62b4da21`; 4 focused tests passed and live ACK bound worktree/HEAD/index/card/policy hashes.
- `workforce-compact-surface`: INTEGRATED_WITH_OWNER_REVIEW at `cd9894707`; 2 focused tests passed, policy hash and route authority are exposed, and mutation authority is explicitly false.
- `briefing-overlay-reduction`: INTEGRATED_WITH_OWNER_REVIEW at `e25902e30`; 10 focused tests passed, compact output is task-aware, and legacy output requires explicit opt-in.
- `workspace-retry-and-permission-gate`: INTEGRATED_WITH_OWNER_REVIEW at `86c197690`; 27 focused lifecycle/CLI tests passed and live retry returned a structured retained-review block without state mutation.

## Blocked Cards

- P6 canonical root cutover remains a separate owner gate in `tasks/workspace-control-convergence/INDEX.md`.

## Campaign Boundaries

- Do not mutate `/Users/jameschen/Workspace/nexus`.
- Do not rewrite or delete historical task receipts.
- Do not create a second route authority; workforce work must consume existing Runtime Admission.
- Do not weaken Candidate, approval, integration, push, or cleanup authority.

## Downstream Gate

Orphan reconciliation remains owner-gated and must use an exact read-only plan hash before any apply. `AUTO_CHAIN=false`; completion never self-authorizes the next card.
