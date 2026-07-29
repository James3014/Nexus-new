---
name: nexus-task-launch
description: Governed Nexus self-hosted task launch policy. Use for implementation work that must remain bounded, reviewable, and connector-driven.
---

# Nexus governed task launch

Read-only inspection may use the current checkout. Code mutation must use the
self-hosted lifecycle tools; do not create an unmanaged worktree, manually
create a branch, or use a direct connector edit/write operation.

## Required sequence

1. Call `nexus_self_hosted_list_actionable_tasks` (or `nexus.bash` running `nexus self-hosted actionable` / `python -m scripts.ops.nexus_chatgpt_delivery actionable`) before any mutation. Record the returned task action and the current controller revision.
2. Call `nexus_self_hosted_submit_task` (or `nexus.bash` running `nexus self-hosted submit` / `python -m scripts.ops.nexus_chatgpt_delivery launch`) with one stable `task_id`, the exact bounded `allowed_files`, the immutable controller revision, and the selected target base. Do not create a `-v2` or `-v3` task ID; retries add only an `attempt_id`.
3. Call `nexus_self_hosted_wait_task` (or `nexus.bash` running `nexus self-hosted wait`) and follow its action envelope until `ACTION_REQUIRED`, `FINAL_BLOCK`, or `TERMINAL`. A worker may edit only the declared target files and must return a candidate commit plus verifier evidence.

If the lifecycle tools are not visible or the existing connector cannot expose them, stop fail-closed with `REPO_READY_CONNECTOR_BLOCKED`. Never fall back to `open_workspace(mode=worktree)`, direct file mutation through the connector (`edit`/`write`/`nexus.edit`/`nexus.write`), stash/reset/clean of a dirty checkout, or an unmanaged worktree.

## Acceptance handoff

The task is not complete when a worker merely reports success. Check the
candidate commit, tree, state hash, receipt hash, changed-file scope, deletion
audit, and controller immutability. Preserve candidate and salvage refs. Hand
the verified candidate to `nexus-merge-gate`; approval and integration remain
separate human-gated actions.

## Forbidden actions

- Do not mutate the main checkout or protected main.
- Do not delete branches, tags, candidate refs, or salvage refs.
- Do not publish to a remote or rewrite existing history.
- Do not create a second Controller.
