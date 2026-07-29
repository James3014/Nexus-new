# G0 — Controller Governance Bootstrap

**task_id:** `model-workforce-v21-runtime-closure-g0-governance`
**artifact_authority:** current
**owner:** James Chen
**status:** IN_PROGRESS
**read_only:** false
**audit_only:** false
**commit_forbidden:** false
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Bring the exact Task Card Authority, block semantics, and Commit/Candidate Policy hunks from governance commits `7208407dff34a97ceb057508aae90b9927cf2d20` and `efa3a7cb7bc2ea1423bf035dd93c001559959287` into the clean isolated Target, then establish this campaign's Git-tracked index and current-frontier card.

This card does not modify runtime code and does not authorize any T3/T4/T5/T6 work.

## Authority and inputs

- Controller: `/Users/jameschen/Workspace/nexus-worktrees/self-hosted-lifecycle-closure-controller`
- Controller branch: `nexus/integration/self-hosted-lifecycle-closure`
- Controller base: `a421af9c0dc779f3104bfe0204bf33f5278808bb`
- Source governance commits: `7208407dff34a97ceb057508aae90b9927cf2d20`, `efa3a7cb7bc2ea1423bf035dd93c001559959287`
- Campaign specification: `/Users/jameschen/.codex/attachments/5f5de7e2-191d-453a-b12e-f4f5b9538a85/pasted-text-1.txt`

## Dependencies

None. The controller must be clean and no unrelated actionable self-hosted task may be active.

## Allowed files

- `AGENTS.md`
- `tasks/model-workforce-v21-runtime-closure/INDEX.md`
- `tasks/model-workforce-v21-runtime-closure/00-g0-controller-governance-bootstrap.md`

## Forbidden scope

- Any runtime, test, config, policy, receipt, learning, provider, planner, router, topology, or benchmark file.
- Any file outside the Allowed files list.
- Controller mutation, approval, integration, merge, push, cleanup, or deletion.
- Starting successor cards or changing `AUTO_CHAIN=false`.

## Verification commands

```text
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --cached --stat
grep -n "Task Card Authority" AGENTS.md
grep -n "Commit and Candidate Policy" AGENTS.md
```

Also verify the AGENTS change contains only the exact rules from the two source commits and the Target remains isolated from the clean Controller.

## Evidence required

- clean Controller branch and immutable base SHA;
- source commit availability;
- exact AGENTS governance hunks;
- index/card paths and task ID;
- allowed-file and tracked-deletion checks;
- scoped commit SHA;
- Candidate record bound to commit SHA and task-card hash;
- independent verification and owner approval before integration.

## Exit criteria

`CONTROLLER_TASK_CARD_GOVERNANCE_INTEGRATED` is not claimable here. This card may claim only `CONTROLLER_TASK_CARD_GOVERNANCE_CANDIDATE_READY` after the scoped commit, candidate formation, independent verification, and owner approval. Runtime closure remains unstarted until the next card is explicitly activated.

## Residual debt and block classification

- `RECOVERABLE_BLOCK`: temporary lifecycle/API or environment failure; preserve Target and evidence, then resume this card.
- `HARD_BLOCK`: controller drift, governance hunk conflict, task-card authority conflict, deletion outside scope, or inability to form the required scoped commit safely.
- Any block prevents Candidate promotion, integration, and successor activation.
