# ChatGPT Direct Control Operator Runbook v0

## Purpose

This runbook describes the bounded direct-control path proven by the ChatGPT direct-control canaries tracked in Nexus-new #1154. It is an operational guide only. It does not create a Nexus Router, Planner, verifier, approval source, completion authority, merge authority, release authority, or production authority.

Under `docs/DOC_AUTHORITY_MANIFEST.yaml`, the filename and location of this document do not establish authority. Until separately reviewed and classified, it is tracked/unclassified operational documentation rather than canonical authority.

The intended topology is:

```text
Owner
  -> Main ChatGPT
       |-- Desktop Commander -> bounded physical host/repository effects
       +-- Chat On Steroids -> advisory ChatGPT peer workers
```

Main ChatGPT remains the coordinator for this path. Repository authority remains in the current `AGENTS.md`, operating-mode contract, and applicable task/merge contracts.

## Scope and claim boundary

- Use this runbook only for explicitly Owner-authorized bounded direct work.
- Chat On Steroids workers are advisory unless a later repository contract explicitly grants a different role.
- Desktop Commander is a direct host execution tool, not a substitute for Nexus governed execution, durable replay, restart reconciliation, or effect receipts.
- CoS worker prose and Desktop Commander tool history are evidence inputs, not completion truth.
- Cross-client or cross-conversation worker-family portability is not assumed.
- This path does not require Dev MCP merely to perform the direct-control canary, but that fact does not prove feature or governance equivalence with DevSpace.
## Preconditions

Before the first repository effect:

1. Read the current repository `AGENTS.md` and `docs/governance/current_operating_mode.yaml`.
2. Confirm the work is eligible for the selected direct lane and has not already entered a governed attempt.
3. Record repository root, branch, HEAD, dirty state, remote, and worktree topology.
4. Preserve unrelated dirty state. Use an isolated worktree when overlap or ownership is uncertain.
5. Bind the physical Desktop Commander host and allowed filesystem roots.
6. Confirm CoS Core and companion connectivity when peer workers are required.
7. Clear any per-worker ChatGPT approval prompt before interpreting a worker that remains active without a result as a runtime failure.
8. Keep `AUTO_CHAIN=false`.

## Operating flow

### 1. Advisory fan-out

Use CoS workers for bounded analysis such as architecture review, verifier design, and counterexample search. Give each worker a distinct task and an explicit no-mutation boundary.

Do not treat worker agreement as acceptance. Main ChatGPT must synthesize the returned evidence and decide the exact bounded mutation scope.

### 2. Freeze the mutation contract

Before Desktop Commander writes:

- freeze the exact repository and base revision;
- freeze allowed paths;
- state the intended behavioral or documentation effect;
- state the verifier commands and expected evidence;
- state the claim ceiling.

If the task has moved outside bounded direct work, stop and use the repository's governed path instead of widening this runbook.
### 3. Physical mutation

Perform repository mutation only through the selected direct host path. Prefer a clean isolated worktree based on the freshly observed remote default branch.

After the write, use a separate physical readback to confirm:

- current branch and HEAD;
- exact changed paths;
- `git status --short --branch`;
- `git diff --check`;
- the actual diff content;
- no unrelated dirty state was absorbed.

A transport success response is not sufficient by itself.

### 4. Verification

Run the smallest verifier set that meaningfully proves the change. For documentation-only changes, at minimum:

```bash
git diff --check
git status --short --branch
git diff --stat
git diff -- <expected-paths>
```

Also run repository-required CI for the exact PR head. If a dedicated semantic or documentation verifier exists for the affected path, run it as well.

Nexus Core evidence/completion machinery is used only when the task's active contract requires or meaningfully consumes it. Do not manufacture a Core completion receipt for a documentation-only direct Candidate merely to make the transport canary look stronger.

### 5. Candidate publication

Commit and push only the scoped issue/canary branch. Open a PR to `main` with the required merge-lane binding and an evidence-bounded body.

A PR Candidate is not a merge, release, deployment, production activation, or Nexus lifecycle completion.
## Chat On Steroids operational notes

- New worker chats may present a ChatGPT approval dialog for the custom `cos` app.
- An active worker with no terminal result is not enough to diagnose a model/runtime defect until approval state is checked.
- Reuse sleeping workers when appropriate; sleeping workers preserve their chat context and do not occupy active worker slots.
- Targeted follow-up must address the exact worker identity in the owning Prime family.
- Do not infer that a family created in one ChatGPT conversation can be controlled from another client or conversation.

## Failure handling

- **Dirty overlap:** create or select an isolated worktree; never reset, clean, stash, or absorb unrelated changes.
- **Possible host effect with uncertain transport result:** inspect physical Git/filesystem state before any retry.
- **CoS worker stuck active:** check custom-app approval and browser/companion state before classifying a worker-completion defect.
- **Worker family not owned by the current Prime:** do not guess a run or inject messages into another family's workers.
- **Main moved:** apply the repository's main-movement requalification rules; do not rebuild an unchanged Candidate solely because the base advanced.
- **Governed authority missing or failed:** never silently downgrade the same governed attempt into this direct path.

## Evidence handoff

Record the bounded evidence needed for review:

- repository and base revision;
- isolated worktree/branch identity;
- changed paths and Candidate head;
- verifier commands and terminal results;
- physical Git diff/readback;
- CoS run/worker identities when peer analysis was used;
- Desktop Commander host identity;
- Issue/PR identities;
- unresolved gaps and claim ceiling.
## Canary exit criteria

The combined direct-control canary is complete only when:

1. CoS advisory workers returned the requested bounded analysis or an explicitly documented worker gap was excluded from the claim.
2. Main ChatGPT remained the sole coordinator of repository mutation.
3. Desktop Commander produced only the frozen physical change.
4. Independent physical Git readback matched the intended scope.
5. Relevant verifiers and exact-head PR checks passed.
6. A scoped PR Candidate exists.
7. No Dev MCP was required for the canary path.
8. No worker, host tool, test result, or PR was promoted into merge, release, production, or completion authority.

This runbook itself is not an authority source.
