---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-53-delete-unreachable-blocks
campaign_id: github-issue-53-unreachable-blocks-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/53
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Delete Two Proven Unreachable Engine Blocks

## Objective

Delete the second unconditional return in `RepairPhase.subagent_return` and the
literal `if False` legacy inline executor body immediately after the canonical
`_run_formulation_plugin` call. Make no reachable behavior change.

## Baseline and re-anchor

- GitHub main: `023f6a239871fb3a55ec9b012c67a6e31cb8b45a`
- Issue #53 fresh-main reconciliation:
  `https://github.com/James3014/Nexus-new/issues/53#issuecomment-5234633579`
- both source files are unchanged from the Issue evidence baseline

Before editing, verify the first `subagent_return` return still dominates the
second and the pipeline guard is still the literal constant `False`.

## Allowed source files

- `nexus/engine/phases/repair.py`
- `nexus/engine/pipeline.py`

Maximum source files changed: 2. The Task Card files are authorization
artifacts and must not be edited by the worker.

## Required change

- deletion only inside the two exact unreachable blocks;
- retain `_run_formulation_plugin(plugin, ctx)` and every reachable statement;
- no formatting sweep, refactor, movement, helper extraction, renaming, or
  compatibility behavior.

## Verification

- AST/source assertion that the second return and literal-false block are gone;
- focused repair-phase, pipeline, phase-hook, formulation-plugin,
  state-transition, and coordinator tests selected from current source;
- Ruff and Pyright on the two source files;
- `git diff --check`;
- exact deletion-only and changed-file audit.

## Exit

Exact commit, independent exact-commit review, no new regression, and proof the
diff contains deletions only in the two authorized blocks.

## Forbidden scope

No pipeline redesign, exception cleanup, phase/order/state changes, plugin API
change, dependency/feature change, test rewrite, direct main push, merge, or
public production claim.

## Block classification

`RECOVERABLE_BLOCK` for bounded verifier or deletion defects; `HARD_BLOCK` if
either block has become reachable or a caller contract depends on it.
