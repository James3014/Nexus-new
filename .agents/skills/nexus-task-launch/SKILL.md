---
name: nexus-task-launch
description: Governed Nexus self-hosted task launch policy. Use only after root AGENTS.md classifies work as governed because it needs delegation, an isolated Target, lifecycle orchestration, a Candidate handoff, or another governed condition. Do not use for eligible Owner-authorized DIRECT_CANONICAL changes.
---

# Nexus governed task launch

## Entry gate

Use only after work is classified as governed under the root `AGENTS.md`. If an
explicit current Owner request is eligible for `DIRECT_CANONICAL`, stop this
skill and return execution to the primary agent in the canonical checkout.
`DIRECT_CANONICAL` does not require a Task Card or lifecycle state.

Read-only inspection may use the current checkout. This skill governs only the
local Nexus self-hosted lifecycle. Use it when the Owner selects that domain or
the intended result is a local governed Target, lifecycle Candidate, runtime
integration, or another explicitly local lifecycle outcome. Ordinary GitHub
Ready-Issue branch work does not enter this skill merely because it is
delegated or will produce a PR Candidate.

After local-lifecycle classification, mutation must use the self-hosted
lifecycle tools; do not create an unmanaged worktree, manually create a branch,
or use a direct connector edit/write operation. Missing-card bootstrap is not a
lifecycle implementation task: only the primary coordinator under the current
standing grant creates the minimum card once and binds its hash. Never launch a
recursive card-only Candidate or let a worker create its own authority card.

## Required sequence

For governed work only:

1. Call `nexus_self_hosted_list_actionable_tasks` (or `nexus.bash` running `python3 -m scripts.engine.nexus_cli self-hosted list-actionable` / `python -m scripts.ops.nexus_chatgpt_delivery actionable`) before governed mutation. Record the returned task action and the current controller revision.
2. Call `nexus_self_hosted_submit_task` (or `nexus.bash` running `python3 -m scripts.engine.nexus_cli self-hosted submit` / `python -m scripts.ops.nexus_chatgpt_delivery launch`) with one stable `task_id`, the exact bounded `allowed_files`, the immutable controller revision, and the selected target base. Do not create a `-v2` or `-v3` task ID; retries add only an `attempt_id`.
3. Call `nexus_self_hosted_wait_task` (or `nexus.bash` running `python3 -m scripts.engine.nexus_cli self-hosted wait`) and follow its action envelope until `ACTION_REQUIRED`, `FINAL_BLOCK`, or `TERMINAL`. A worker may edit only the declared target files and must return a candidate commit plus verifier evidence.

When `nexus.bash` plus the repo-owned wrapper (`python -m scripts.ops.nexus_chatgpt_delivery`) or official self-hosted CLI (`python3 -m scripts.engine.nexus_cli self-hosted`) is available, `nexus.bash` must be used for governed lifecycle operations. `REPO_READY_CONNECTOR_BLOCKED` applies only when neither native lifecycle tools nor `nexus.bash` with repo-owned CLI wrappers are available. Never fall back to `open_workspace(mode=worktree)`, direct file mutation through the connector (`edit`/`write`/`nexus.edit`/`nexus.write`), stash/reset/clean of a dirty checkout, or an unmanaged worktree.

## Acceptance handoff

The task is not complete when a worker merely reports success. Check the
candidate commit, tree, state hash, receipt hash, changed-file scope, deletion
audit, and controller immutability. Preserve candidate and salvage refs. Hand
the verified candidate to `nexus-merge-gate`; approval and integration remain
separate human-gated actions.

That handoff applies only to a local lifecycle Candidate. A GitHub PR Candidate
uses fresh PR/base/head/diff, required CI, independent acceptance, and
expected-head/CAS merge gates instead.

## Forbidden actions

- Do not mutate the main checkout or protected main.
- Do not delete branches, tags, candidate refs, or salvage refs.
- Do not publish to a remote or rewrite existing history.
- Do not create a second Controller.
