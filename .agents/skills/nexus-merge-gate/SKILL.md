---
name: nexus-merge-gate
description: Hash-bound approval, integration, verification, and cleanup for the governed Nexus self-hosted lifecycle.
---

# Nexus governed merge gate

This gate is connector-driven and fail-closed. A green test subset is not a
promotion decision, and a candidate is not integrated until its exact receipt
binding is approved.

This skill applies exclusively to a local Nexus lifecycle Candidate and local
integration. It is not the merge procedure for a GitHub PR Candidate. GitHub
protected-merge semantics follow the already-selected execution lane, not the
repository name.

For `DIRECT_CANONICAL` and `DIRECT_DELEGATED`, require fresh exact
repository/PR/base/head/diff, intended scope, deletion audit, relevant tests,
terminal-success required checks, readable branch protection, mergeability,
current Owner confirmation, and expected-head/CAS. `DIRECT_DELEGATED` also
requires the primary coordinator, distinct from the worker, to inspect the
physical diff and rerun the applicable verifier. That coordinator verification
is sufficient; no third reviewer is required. The direct merge sink is the
server-bound `git_merge_pull_request`. Direct merge does not require a Task
Card, GitHub `APPROVED` review, independent acceptance receipt/hash, standing
grant, `GITHUB_MERGE`, or `github_complete_pull_request`.

For `GOVERNED`, keep the existing independent acceptance,
machine-verifiable provenance, `MERGE_INTENT`, standing-grant `GITHUB_MERGE`,
and `github_complete_pull_request` completion-loop rules. A valid current
standing grant explicitly covering the exact repository, Goal, coordinator,
and normal GitHub action remains valid across ordinary phase transitions; do
not request redundant Owner reauthorization. Reauthorize only for a real
authority boundary or genuine external-platform approval. No lane may bypass
verification, branch protection, or CAS. Local lifecycle approval cannot
bootstrap a Task Card or manufacture GitHub merge authority.

## Gate sequence

1. Call `nexus_self_hosted_list_actionable_tasks` (or `nexus.bash` running `python3 -m scripts.engine.nexus_cli self-hosted list-actionable` / `python -m scripts.ops.nexus_chatgpt_delivery actionable`). Treat `PENDING_HUMAN_APPROVAL` and `APPROVED` as `ACTION_REQUIRED`; never infer that a worker completion is approval.
2. Verify candidate commit, candidate tree, candidate state hash, verified receipt hash, controller revision, allowed-file scope, and all verifier results. Confirm the controller checkout is unchanged.
   `REVISE`, card clarification, or reviewer `HARD_BLOCK` stops approval but is
   not automatically terminal `REJECTED`. Repair within existing Owner scope
   when possible; only an authorized decision-maker may reject the Candidate.
3. With the recorded hashes, call `nexus_self_hosted_approve_promotion` (or `nexus.bash` running `python3 -m scripts.engine.nexus_cli self-hosted approve`). Approval must bind the exact candidate; do not substitute a newer commit or recompute a receipt after approval.
4. Call `nexus_self_hosted_integrate_approved` (or `nexus.bash` running `python3 -m scripts.engine.nexus_cli self-hosted integrate`) targeting exactly `nexus/integration/self-hosted-lifecycle-closure`. The operation must create a normal merge preserving candidate and integration ancestry. Verify the implementation, live-canary, and docs commits are ancestors afterward.
5. Run the focused and full repository gates, `git diff --check`, and both
   staged/unstaged deletion audits. Record the post-integration HEAD, protected
   main SHA, branch/ref counts, and `push=false`.
6. Confirm terminal Target cleanup from its receipt. Retain durable candidate
   and salvage refs and record any `RETAINED_FOR_REVIEW` item as a bounded human
   action; never silently discard unique modifications.

## Safety boundaries

`REPO_READY_CONNECTOR_BLOCKED` is the terminal result only when neither native connector tools nor `nexus.bash` with the repo-owned self-hosted CLI is available. When `nexus.bash` plus the repo-owned wrapper or official self-hosted CLI is available, `nexus.bash` must be used for governed lifecycle operations instead of blocking. Do not use direct worktree delivery, manual branch creation, a protected-main merge, remote publication, history rewrite, or ref/branch/tag deletion as a workaround. Never delete candidate or salvage
refs. Rollback, if explicitly required, must restore the recorded integration
SHA without rewriting existing commits.

## Evidence required for handoff

Return the task action envelope, approved binding, merge commit and parents,
test commands/results, ancestry checks, cleanup receipt, controller status hash
before/after, protected-main comparison, `branches deleted = 0`, `refs deleted
= 0`, and `push = false`. If any binding or verifier is inconsistent, stop that
item fail-closed and continue only with independently authorized items.
