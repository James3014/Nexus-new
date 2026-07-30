# Task Card 00a: Self-hosted Verification Entrypoint Final Amendment

## Identity
- task_id: `self-hosted-verification-entrypoint-final-amendment`
- campaign_id: `self-hosted-operator-workflow`
- artifact_authority: current
- status: RECOVERABLE_BLOCK
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective
Close the two remaining fail-open defects in the rejected Candidate `a2d8e764464a2a0bf3b1fac21f612cc9998a9354` by creating a fresh governed Candidate from the current integration HEAD.

## Required behavior
1. Durable state disappearance or unreadability after verifier execution must be detected physically and force `state_mutated=true` and `overall_passed=false`; it must never reuse the before-state or before-hash.
2. Integrated-task verification must accept only the original exact lowercase SHA format `^[0-9a-f]{40}$`; uppercase and mixed-case SHAs must fail closed before any verifier command runs.
3. Preserve the previously corrected requirements: no candidate SHA fallback, exact integration-result ancestry binding, canonical verifier environment, zero provider calls during verify, and read-only lifecycle semantics.

## Starting evidence
- Controller/integration base: `6833cb91354d65435a982590240b7fd7f5479118`
- Rejected Candidate: `a2d8e764464a2a0bf3b1fac21f612cc9998a9354`
- Rejected Candidate tree: `e4e1158f73215f61b212923452d212a08352531c`
- Rejected Candidate is evidence/reference only and must not be merged or amended in place.

## Allowed files
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Forbidden scope
- No changes to CLI, MCP, CandidateVerifier, WorktreeManager, governed integration, Task Cards, Campaign Index, model workforce policy, or provider routing.
- No approve, integrate, push, reset, stash, cleanup, or deletion.
- No fallback to `candidate_commit_sha`, `HEAD`, `controller_revision`, or `target_base_revision` for integrated authority.
- No auto-repair or restoration of missing/corrupt durable state.

## Implementation contract
- Read post-verification durable state without `or state_before` fallback.
- Missing state must return a machine-readable integrity reason and blank after-hash/status values, with `state_mutated=true` and `overall_passed=false`.
- Unreadable JSON must fail closed with a distinct machine-readable integrity reason.
- SHA format validation must occur before normalization and must not lowercase the value before regex validation.
- Normal read-only verification must keep before/after hashes equal and report no mutation.

## RED witnesses
- deleted durable state is detected even when verifier command exits 0;
- corrupt durable state is detected and fails closed;
- deleted/corrupt state cannot reuse before hash;
- uppercase and mixed-case integration SHAs are rejected before verifier invocation;
- lowercase exact SHA remains accepted;
- normal state remains unchanged.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/engine/test_self_hosted_cli.py`
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_mcp.py tests/nexus/orchestrator/test_self_hosted_mcp_http.py tests/nexus/orchestrator/test_workflow_repair.py`
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_governed_integration.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_worktree_manager.py`
- `python3 -m compileall -q nexus/orchestrator/self_hosted_task_service.py`
- `git diff --check`

## Required evidence
- exact Candidate SHA/tree/ref/parent;
- changed files limited to the two allowed files;
- deleted-state and corrupt-state command exit/result evidence;
- uppercase/mixed-case verifier invocation count zero;
- normal-state before/after hash equality;
- all verification commands green;
- zero tracked deletions;
- Controller unchanged and Target clean.

## Exit criteria
- A fresh scoped Candidate commit exists on `refs/heads/nexus/task/self-hosted-verification-entrypoint-final-amendment`.
- Candidate parent is exactly the governance commit that tracks this card.
- All required tests pass with no unexpected skips.
- Candidate is ready only for independent review; no downstream authority is granted.

## Block classification
- Provider quota/transport unavailable: `RECOVERABLE_BLOCK`, preserve the same card and Target.
- Scope, authority, or architecture conflict: `HARD_BLOCK`, stop mutation.

## Execution disposition
- Codex provider execution used physical model `gpt-5.5`, exited 1 after 650833 ms, and formed no Candidate.
- The two-file working result is preserved only as non-candidate salvage `29b9b0d40eb29e0ea590d4cbf05118c7ba3ae43d`.
- Clean recovery is delegated to `self-hosted-verification-entrypoint-opencode-recovery`; this card grants no promotion authority.

## Maximum claim
SELF_HOSTED_VERIFICATION_ENTRYPOINT_FINAL_AMENDMENT_RECOVERABLE_BLOCK
