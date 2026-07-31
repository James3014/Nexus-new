# Task Card 04: Startup Freshness Gate

## Identity

- task_id: `startup-freshness-gate`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `machine-policy-contract` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Bind startup ACK to the actual current worktree root, branch, HEAD, clean state, active campaign INDEX/card freshness, machine policy contract hash, required files, and CLI surfaces. A stale or missing authority source must block startup and no ACK may be issued.

## Allowed files

- `scripts/ops/nexus_startup_contract_check.py`
- `tests/ops/test_nexus_startup_contract_check.py`

## Forbidden scope

No launcher/provider/model changes; no canonical-root mutation; no receipt deletion; no weakening of task authority or policy fail-closed behavior; no new parallel startup checker.

## Required behavior

1. Startup derives the worktree identity from Git and records root, branch, HEAD, and dirty state.
2. Startup validates the configured Task Card campaign INDEX through `task_authority_freshness_check.py`; any `BLOCK` decision prevents ACK.
3. Startup verifies the policy contract exists and records its SHA-256; missing/unreadable contract prevents ACK.
4. ACK contains the exact HEAD, index path/commit, current frontier/card hash, policy hash, and runner identity.
5. Report/ACK output path is configurable for tests and operators, while default behavior remains the existing startup hardening directory.
6. Existing required-file and CLI-surface checks remain intact.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_nexus_startup_contract_check.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --stat
git diff --cached --stat
```

## Evidence required

- Tests prove stale/missing INDEX and policy contract block without ACK.
- Success receipt binds worktree, HEAD, index/card, and policy hashes.
- No files outside the two allowed paths are changed.

## Exit criteria

The startup checker emits a freshness-bound ACK only on a clean, current, policy-valid worktree and passes focused tests in a scoped commit.

## Residual debt

Launcher briefing still contains more context than necessary; workforce compact surface and task-aware briefing overlays remain downstream.

## Block classification

- `RECOVERABLE_BLOCK`: test or local report-path failure with artifacts preserved.
- `HARD_BLOCK`: startup cannot identify the current worktree or authoritative Task Card/policy source.
