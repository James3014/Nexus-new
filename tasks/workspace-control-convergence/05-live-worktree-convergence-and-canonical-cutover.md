# Task Card: Live Worktree Convergence and Canonical Cutover

## Identity
- artifact_authority: current
- owner: James Chen
- status: APPROVED_IN_PROGRESS
- task_id: `live-worktree-convergence-and-canonical-cutover`
- source_specification: owner instruction on 2026-08-01 to merge valuable work, remove redundant worktrees, and make `/Users/jameschen/Workspace/nexus` the sole daily entrypoint
- read_only: false
- audit_only: false
- commit_forbidden: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Reconcile every registered Nexus worktree without content loss, preserve dirty or unique states behind durable salvage refs and an external archive, integrate only validated source changes, remove redundant worktrees, and cut the canonical root over to the controlled integration history.

## Inputs

- Controlled integration ref: `nexus/integration/main`.
- Clean controller: `/Users/jameschen/Workspace/nexus-worktrees/integration-main`.
- Legacy canonical root: `/Users/jameschen/Workspace/nexus` at `feature/full-capability-closure-20260718`.
- Verified external archive: `/Users/jameschen/Workspace/nexus-salvage/20260801-root-convergence/`.
- Owner approval and cleanup requirement recorded in the conversation on 2026-08-01.

## Dependencies

- Cards 02, 03, and 04 are integrated.
- P7 cleanup/soak and terminal receipt archival are complete.
- Root dirty-state archive, staged patch, unstaged patch, hashes, and archive listing exist before root mutation.

## Allowed Files and State

- `tasks/workspace-control-convergence/INDEX.md`
- `tasks/workspace-control-convergence/05-live-worktree-convergence-and-canonical-cutover.md`
- Git worktree registration under the repository common Git directory.
- The exact registered worktree paths enumerated by `git worktree list --porcelain` at execution time.
- `refs/nexus-salvage/worktree/*` and `refs/nexus-salvage/canonical-root/*` created to preserve pre-removal states.
- Source and test files from the legacy root only through separately scoped reconciliation commits of at most ten touched files each.

## Forbidden Scope

- No remote push or remote branch mutation.
- No protected-history rewrite, rebase, or `git reset --hard`.
- No deletion of salvage refs.
- No manual edit of lifecycle JSON or receipt stores.
- No blind merge of generated reports, runtime state, GitNexus artifacts, nested repositories, caches, or benchmark output.
- No deletion of a dirty or unique worktree until its exact state is protected by a verified salvage ref or the verified root archive.
- No promotion, disposal, or mutation of `exact-authorized-deletion-contract-bootstrap`.

## Execution Contract

1. Re-enumerate worktrees, branches, HEADs, dirty paths, unique commits, patch equivalence, and active processes.
2. For each non-root dirty worktree, form a scoped salvage commit, bind a unique `refs/nexus-salvage/worktree/*` ref to it, and verify the worktree is clean.
3. Preserve clean but unique committed histories by existing branch/ref or an added salvage ref. Treat patch-equivalent histories as integrated evidence, not new merge work.
4. Reconcile legacy-root source/test changes in bounded packets. Each packet must pass its targeted tests and be committed independently; generated or historical artifacts stay in the verified archive unless an authoritative consumer requires them.
5. Run the full merge gate on the final integration commit.
6. Recheck processes and ref bindings, then remove redundant non-root worktrees using normal `git worktree remove` after they are clean.
7. Preserve the legacy canonical HEAD and dirty archive, clean only exact archived paths without `reset --hard`, switch `/Users/jameschen/Workspace/nexus` to `nexus/integration/main`, and verify it is the only daily entrypoint.
8. Prune only stale worktree metadata after physical removal. Retain branches and salvage refs unless separately authorized.

## Verification Commands

- `git worktree list --porcelain`
- `git status --short --branch`
- `git merge-base --is-ancestor <head> nexus/integration/main`
- `git cherry nexus/integration/main <head>`
- `git show-ref --verify <salvage-ref>`
- `git diff --check`
- `uv run pytest -q`
- `uv run python scripts/ops/acceptance_suite.py`
- `uv run python scripts/ops/contract_test.py`

If either named script is absent, record that physical mismatch and use the repository's current authoritative acceptance/contract entrypoints discovered from tracked operator documentation; do not invent a passing substitute.

## Evidence Required

- Before/after worktree counts and exact remaining paths.
- Archive and patch SHA-256 hashes.
- Salvage ref to commit mapping for every removed dirty/unique state.
- Reconciliation commit SHAs and changed-file lists.
- Exact test commands and results.
- Final canonical root branch, HEAD, dirty state, and worktree inventory.

## Exit Criteria

- Every removed worktree is clean and merged, patch-equivalent, or protected by a verified salvage ref.
- Valuable legacy-root source/test changes are either integrated with passing evidence or explicitly preserved as residual archive debt with a concrete reason.
- `/Users/jameschen/Workspace/nexus` is on the controlled integration history and is the documented daily entrypoint.
- No redundant registered worktrees remain except an explicitly active isolated Target.
- No lifecycle JSON, remote ref, protected history, or salvage ref was mutated outside this card.

## Residual Debt and Blocks

- `RECOVERABLE_BLOCK`: transient test/runtime failure with intact worktrees and refs.
- `HARD_BLOCK`: archive hash mismatch, unprotected unique state, process ownership conflict, or a source change that cannot be safely classified within the ten-file limit.
- Residual artifacts may remain only in the external salvage archive; they must not keep the canonical root dirty.
