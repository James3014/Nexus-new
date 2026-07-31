# Campaign Index: Lifecycle P6 Completion

artifact_authority: current
owner: James Chen
status: active
source_specification: owner-authorized execution of the P0-P6 lifecycle and workspace improvement plan; explicit request to complete through P6
AUTO_CHAIN: false

## Campaign Overview

Close the remaining lifecycle friction without mutating the dirty canonical root: legacy allocator mutation is fail-closed by default, wait/verify/cleanup are operator-safe and lock-aware, orphan workspaces remain evidence-bound and owner-reviewed, and P5/P6 evidence is recorded without claiming integration or promotion authority.

## Ordered Cards

1. [01-p3-allocator-p6-operator-surfaces.md](01-p3-allocator-p6-operator-surfaces.md) - `lifecycle-p3-allocator-p6-operator-surfaces`
2. [02-p4-orphan-reconciliation.md](02-p4-orphan-reconciliation.md) - `orphan-workspace-reconciliation` (linked audit authority)
3. [03-p5-cutover-rehearsal.md](03-p5-cutover-rehearsal.md) - `lifecycle-p5-cutover-rehearsal` (rehearsal evidence)
4. [04-p6-final-gate.md](04-p6-final-gate.md) - `lifecycle-p6-final-gate`

## Current Frontier

`lifecycle-p3-allocator-p6-operator-surfaces`

Current frontier card hash (sha256): `35c4acc5e945b17c996372116c5f047b2ac4bea66e0bcd84f0d520a544037849`

## Completed Evidence

- P0/P1 authority baseline is recorded in `tasks/workspace-control-convergence/INDEX.md` at candidate commit `8653d497542af6c8c8dc541f295835692bff893a`.
- P2 hardening candidate is present on the isolated stack and its fresh lifecycle regression suite passed `242 passed`.
- P3 allocator quarantine targeted suite passed `6 passed`.
- P4 orphan inventory is audit-only: `deletion_count=0`, blocker codes `legacy_root_protected`, `unmapped_dirty_worktree`, `unmapped_unique_commit`; no automatic cleanup is authorized.
- P5 temporary controller cutover/rollback rehearsal returned `Nexus Startup Contract PASSED` and removed its temporary worktree.

## Boundaries

- Do not mutate `/Users/jameschen/Workspace/nexus`.
- Do not edit lifecycle JSON directly, delete live worktrees/branches/refs, approve/integrate/push a Candidate, or promote production claims.
- Do not reintroduce GitNexus directives into `AGENTS.md` or `CLAUDE.md`.
- P4 cleanup remains owner-only and is not implied by audit completion.

## Downstream Gate

P6 is complete only after operator action envelopes, lock-free read paths, timeout/heartbeat behavior, deterministic cleanup dry-run, and bounded performance evidence pass on the isolated stack. The stack remains a Candidate until owner approval and integration.
