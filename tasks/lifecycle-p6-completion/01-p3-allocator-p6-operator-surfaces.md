# Task Card 01: P3 Allocator and P6 Operator Surfaces

## Identity

- task_id: `lifecycle-p3-allocator-p6-operator-surfaces`
- campaign_id: `lifecycle-p6-completion`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- depends_on: `retained-clean-target-closure` candidate stack plus P0/P1 authority evidence
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Make the legacy allocator and operator surfaces deterministic and fail-closed: disable legacy swarm reuse and harvest by default, retain branches unless explicitly authorized, make wait/verify read-only paths avoid state-lock acquisition, and ensure every existing-task verification result exposes a unique next action. Preserve durable evidence and never mutate the canonical root or live lifecycle JSON in this card.

## Inputs and dependencies

- P2 candidate stack commits already cherry-picked into the isolated controller branch.
- P4 inventory and P5 rehearsal evidence recorded in the campaign index.
- Current card hash must be recorded in the campaign index before commit/candidate formation.

## Allowed files

- `tasks/lifecycle-p6-completion/INDEX.md`
- `tasks/lifecycle-p6-completion/01-p3-allocator-p6-operator-surfaces.md`
- `nexus/services/workspace.py`
- `tests/services/test_workspace_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `nexus/executors/cli_worker.py`
- `tests/nexus/executors/test_cli_worker.py`

## Forbidden scope

No canonical-root mutation, direct lifecycle JSON edits, live worktree/branch/ref deletion, approval, integration, push, GitNexus instruction changes, or broad router redesign. Tests must use temporary repositories and state directories only.

## Required verification

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/services/test_workspace_manager.py tests/nexus/orchestrator/test_self_hosted_task_service.py
PYTHONDONTWRITEBYTECODE=1 /Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_task_contract.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_mcp.py tests/ops/test_nexus_startup_contract_check.py tests/ops/test_start_codex_nexus_enforced.py tests/ops/test_start_gemini_nexus_enforced.py tests/ops/test_nexus_enforced_briefing.py
git diff --check
git diff --name-status --diff-filter=D
npx --yes gitnexus detect-changes --repo Nexus --scope unstaged
```

## Evidence required

- P3 targeted regression proves legacy reuse/harvest/cleanup are opt-in and fail-closed by default.
- P6 wait and verify execute without `.state.lock` acquisition and return `task_action`/`next_action` for an existing task.
- CLI verifier execution preserves explicit virtualenv interpreter symlinks so installed verifier dependencies remain available.
- Full lifecycle regression remains green; semantic missing-candidate verification remains `FAILED` with `state_intact=true`.
- Exact scoped commit and Candidate binding are reported; no approval/integration claim.

## Captured evidence before commit

- Combined P3/P6 targeted suite: `99 passed in 42.27s`.
- Full lifecycle regression: `244 passed in 154.26s`; the required elevated permission was needed only for the dirty-target sentinel test.
- Live verify: `FAILED`, `durable_candidate_binding_missing`, `state_intact=true`, `next_action=inspect_blocker_and_retry_or_dispose`.
- Live wait: `timed_out=false`; cleanup dry-run: `dry_run=true`, `ALREADY_REMOVED`.
- Three-run CLI wall-time samples: verify `0.69/0.58/0.50s`, wait `0.48/0.55/0.57s`, cleanup `0.61/0.61/0.62s`.

## Exit criteria

All required tests pass, direct CLI wait/verify/cleanup probes complete without lock permission failures, action envelopes contain a unique next action, performance measurements are recorded in the final response, and the staged diff contains only allowed files.

## Residual debt

Owner-only candidate approval/integration and live P4 cleanup remain outside worker authority. No automatic cleanup is permitted.

## Block classification

- `RECOVERABLE_BLOCK`: isolated test/provider/environment failure.
- `HARD_BLOCK`: safe operator behavior cannot be expressed without broadening scope or mutating protected state.
