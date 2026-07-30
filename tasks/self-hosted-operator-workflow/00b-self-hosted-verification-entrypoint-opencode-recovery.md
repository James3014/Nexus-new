# Task Card 00b: Self-hosted Verification Entrypoint OpenCode Recovery

## Identity
- task_id: `self-hosted-verification-entrypoint-opencode-recovery`
- campaign_id: `self-hosted-operator-workflow`
- artifact_authority: current
- status: READY
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective
Reconstruct the complete task-bound, read-only `nexus self-hosted verify --task-id <TASK_ID>` vertical slice from a clean integration base, including all independently identified fail-closed corrections.

## Read-only evidence
- Original rejected Candidate: `a2d8e764464a2a0bf3b1fac21f612cc9998a9354`
- Original tree: `e4e1158f73215f61b212923452d212a08352531c`
- Failed Codex salvage: `29b9b0d40eb29e0ea590d4cbf05118c7ba3ae43d`
- Both objects are reference evidence only. Do not merge, cherry-pick, amend, or promote them.

## Required observable behavior
1. CLI command: `nexus self-hosted verify --task-id <TASK_ID>` with optional existing `--state-dir` convention.
2. Commands come only from durable `state.contract.verifier_commands`; no arbitrary command input.
3. Canonical verifier environment: `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `PYTHONDONTWRITEBYTECODE=1`.
4. Target workspace is used only when it is a registered worktree with no active process.
5. Integrated workspace requires exact integration branch and an existing original lowercase `integration_result_sha` matching `^[0-9a-f]{40}$` that is an ancestor of Controller HEAD. No fallback to Candidate SHA, HEAD, controller revision, or target base.
6. Missing, deleted, or unreadable durable state after verification must be physically detected; `state_mutated=true`, `overall_passed=false`, blank after-hash/status, and a stable machine-readable integrity reason.
7. Any ordinary state mutation forces overall failure. Normal read-only execution keeps before/after hashes equal.
8. Receipt includes task/workspace identity, lifecycle and promotion status before/after, state hashes, mutation result, provider_calls=0, overall result, and per-command execution evidence.
9. CLI exits 0 only when all commands pass and state is unchanged; otherwise exits 1 while preserving the receipt where execution occurred.
10. Verify never invokes a model, commits, approves, integrates, pushes, recovers, or changes campaign state.

## Allowed files
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/engine/test_self_hosted_cli.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Forbidden scope
- No MCP surface.
- No changes to CandidateCommitter, WorktreeManager, governed integration, provider routing, workforce policy, Task Cards, or Campaign Index.
- No new module, router, verifier framework, receipt builder, or durable receipt file.
- No deletion, migration, approval, integration, push, reset, stash, cleanup, or arbitrary shell command option.
- Do not duplicate an existing method or append a second implementation of the same public behavior.

## Implementation discipline for OpenCode
- Use `opencode/mimo-v2.5-free` in a bounded isolated context.
- Read the Task Card first, then inspect only the seven allowed files and the two Git evidence objects.
- Prefer the smallest coherent reconstruction; reuse existing CandidateVerifier and CLI worker patterns.
- RED first for missing surfaces and every fail-closed boundary.
- One Target, one scoped commit, one Candidate. Stop on scope expansion.

## Mandatory tests
- direct service success and command failure receipts;
- unknown task and empty verifier commands fail before execution;
- hostile outer environment cannot override canonical verifier environment;
- retained Target selection and active-process rejection;
- integrated Controller branch and exact ancestor binding;
- absent Candidate fallback;
- uppercase and mixed-case SHA rejected before command invocation;
- lowercase SHA accepted;
- ordinary state mutation, deleted state, and corrupt state force failure;
- no provider/worker invocation;
- CLI exit 0/1 and no arbitrary command option;
- existing self-hosted MCP/recovery and governed integration regressions remain green.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/engine/test_self_hosted_cli.py`
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_mcp.py tests/nexus/orchestrator/test_self_hosted_mcp_http.py tests/nexus/orchestrator/test_workflow_repair.py`
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_governed_integration.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_worktree_manager.py`
- `python3 -m compileall -q nexus/orchestrator/candidate_verifier.py nexus/orchestrator/self_hosted_task_service.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py`
- `git diff --check`

## Exit criteria
- Candidate parent is the exact governance commit tracking this card.
- Candidate branch/ref is `refs/heads/nexus/task/self-hosted-verification-entrypoint-opencode-recovery`.
- Changed files are a subset of the seven allowed files; zero deletions and zero unexpected skips.
- Controller remains unchanged and clean; Target is clean after Candidate formation.
- Candidate stops at independent review; no downstream task starts.

## Block classification
- OpenCode transport/quota failure: `RECOVERABLE_BLOCK`; preserve evidence and retry the same card with an approved bounded OpenCode model.
- Scope, authority, or architecture conflict: `HARD_BLOCK`.

## Maximum claim
SELF_HOSTED_VERIFICATION_ENTRYPOINT_OPENCODE_RECOVERY_CANDIDATE_READY
