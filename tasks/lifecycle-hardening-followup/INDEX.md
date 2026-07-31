# Campaign Index: Lifecycle Hardening Follow-up

artifact_authority: current
owner: James Chen
status: active
source_specification: owner-authorized continuation of the lifecycle/workspace cleanup decision
AUTO_CHAIN: false

## Campaign Overview

Close the two verified lifecycle gaps before applying workspace cleanup: startup must operate from a writable machine-state/report location even when the source worktree is read-only, and read-only task verification must fail closed when verifier commands mutate the Target. The campaign also prepares a current authorized-deletion contract successor. It must not mutate the dirty canonical root, approve or integrate Candidates, or perform P6 cutover.

## Ordered Cards

1. [01-startup-report-portability.md](01-startup-report-portability.md) - `startup-report-path-portability`
2. [02-verify-task-target-integrity.md](02-verify-task-target-integrity.md) - `verify-task-target-integrity`
3. [03-authorized-deletion-contract.md](03-authorized-deletion-contract.md) - `authorized-deletion-contract`

## Current Frontier

`verify-task-target-integrity`

## Ready Cards

- `verify-task-target-integrity`: ready on clean Target at `41b55bf31`.

## Completed Cards

- `startup-report-path-portability`: INTEGRATED_WITH_OWNER_REVIEW at `41b55bf31`; 8 focused tests passed and live external-state startup returned `ENFORCED`.

## Blocked Cards

- None.

## Campaign Boundaries

- Do not mutate `/Users/jameschen/Workspace/nexus`.
- Do not delete worktrees, branches, refs, or receipts.
- Do not approve, integrate, push, or promote a Candidate.
- Do not alter GitNexus instructions or add GitNexus as an execution requirement.
- Do not mix startup, verifier, authorized-deletion, workspace cleanup, or P6 changes in one implementation card.

## Downstream Gate

The workspace cleanup apply packet remains separate and must bind to a newly generated inventory and plan hash after these cards' evidence is accepted.
