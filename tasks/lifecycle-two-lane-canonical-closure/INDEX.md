# Campaign Index: Lifecycle Two-Lane Canonical Closure

artifact_authority: current
owner: James Chen
status: active
campaign_id: lifecycle-two-lane-canonical-closure
source_specification: owner-authorized lifecycle diagnosis and two-lane canonical closure plan from 2026-08-01
AUTO_CHAIN: false

## Authority

- Daily source checkout: `/Users/jameschen/Workspace/nexus`
- Daily branch: `nexus/integration/main`
- Canonical lifecycle state: `/Users/jameschen/Workspace/nexus-self-hosted-state`
- Disabled daily-worktree path: `/Users/jameschen/Workspace/nexus-worktrees`
- Isolated Target root after P5: `/Users/jameschen/Workspace/nexus-runtime-targets`

## Objective

Ordinary read, diagnosis, and bounded primary-agent edits use the canonical checkout without a worktree. High-risk, delegated, parallel, dirty, or authority-sensitive work uses one governed isolated Target. Every task reaches an explicit terminal disposition without duplicates, abandoned Targets, stale authority, or hidden read-only mutations.

## Ordered Cards

1. `00-p0-authority-convergence.md` - `lifecycle-two-lane-p0-authority-convergence`
2. `01-p1-read-only-zero-side-effects.md` - `lifecycle-two-lane-p1-read-only-zero-side-effects`
3. `02-p2-direct-canonical-lane.md` - `lifecycle-two-lane-p2-direct-canonical-lane`
4. `03-p3-owner-finish.md` - `lifecycle-two-lane-p3-owner-finish`
5. `04-p4-same-task-retry.md` - `lifecycle-two-lane-p4-same-task-retry`
6. `05-p5-target-root-and-telemetry.md` - `lifecycle-two-lane-p5-target-root-and-telemetry`
7. `06-p6-cutover-gate.md` - `lifecycle-two-lane-p6-cutover-gate`

## Current Frontier

`lifecycle-two-lane-p6-cutover-gate`

## Completed Cards

- `lifecycle-two-lane-p0-authority-convergence`: committed `dc0292b12`
- `lifecycle-two-lane-p1-read-only-zero-side-effects`: committed `3cc8249c3`
- `lifecycle-two-lane-p2-direct-canonical-lane`: committed `aeb2e6426`
- `lifecycle-two-lane-p3-owner-finish`: committed `55e31423b`
- `lifecycle-two-lane-p4-same-task-retry`: committed `b752fc72e`
- `lifecycle-two-lane-p5-target-root-and-telemetry`: committed `23db1ad53`

## Current Gate

`lifecycle-two-lane-p6-cutover-gate` is the only current frontier. `AUTO_CHAIN=false`; owner review remains required for any promotion, integration, push, branch/ref cleanup, or external workspace cleanup.

## Dependencies

P1 depends on P0. P2 depends on P1. P3/P4 depend on P2. P5 depends on P1-P4. P6 depends on all implementation cards and fresh inventory.

## Global forbidden scope

No direct lifecycle JSON edits; no push, protected rewrite, automatic approval, worker integration, or GitNexus forced directives; no branch/ref/salvage/external workspace deletion without owner decision.

## Completion ceiling

Complete only when the P6 30-task matrix proves zero unwanted worktree creation, zero duplicate logical tasks, zero abandoned active Targets, zero stale current authority, and a clean canonical checkout.
