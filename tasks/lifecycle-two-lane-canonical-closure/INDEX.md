# Campaign Index: Lifecycle Two-Lane Canonical Closure

artifact_authority: current
owner: James Chen
status: completed_revalidation
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
8. `07-lifecycle-two-lane-gate-revalidation.md` - `lifecycle-two-lane-gate-revalidation`

## Current Frontier

`none` (P7 revalidation complete; owner review remains explicit for retained canonical state)

## Completed Cards

- `lifecycle-two-lane-p0-authority-convergence`: committed `dc0292b12`
- `lifecycle-two-lane-p1-read-only-zero-side-effects`: committed `3cc8249c3`
- `lifecycle-two-lane-p2-direct-canonical-lane`: committed `aeb2e6426`
- `lifecycle-two-lane-p3-owner-finish`: committed `55e31423b`
- `lifecycle-two-lane-p4-same-task-retry`: committed `b752fc72e`
- `lifecycle-two-lane-p5-target-root-and-telemetry`: committed `23db1ad53`
- `lifecycle-two-lane-p6-cutover-gate`: committed `190955e2d`
- `lifecycle-two-lane-gate-revalidation`: committed `48dbab1fa`, `957bc41f0`, `68b85f49c`, `bf57dcb54`, `816aa5874`, `5d98bffeb`, `c41bcb00f`, `11c07b897`, `44439c614`

## Current Gate

The P7 revalidation gate is complete. `AUTO_CHAIN=false`; owner review remains required for any future promotion, integration, push, branch/ref cleanup, or external workspace cleanup.

P6 gate evidence: 30-task matrix passed; combined lifecycle regression passed `213/213`; canonical checkout is clean with one registered worktree.

P7 revalidation evidence is recorded in card 07. The remaining canonical retained task is visible, terminally retained, and exposes one same-task retry surface; no state mutation is authorized without the owner decision represented by that surface.

P0 authority reclassification is committed at `534e72bb4`; active lifecycle indexes no longer point to the retired Controller path.

## Dependencies

P1 depends on P0. P2 depends on P1. P3/P4 depend on P2. P5 depends on P1-P4. P6 depends on all implementation cards and fresh inventory.

## Global forbidden scope

No direct lifecycle JSON edits; no push, protected rewrite, automatic approval, worker integration, or GitNexus forced directives; no branch/ref/salvage/external workspace deletion without owner decision.

## Completion ceiling

P7 closes the lifecycle implementation/revalidation objective: zero unwanted worktree creation in the physical matrix, zero duplicate logical task creation for duplicate card hashes, zero abandoned active Targets after the isolated cycles, explicit fault recovery surfaces, and a clean canonical checkout. Retained canonical state remains evidence/owner review, not an automatic cleanup target.
