# Task Card 05: Workforce Compact Surface

## Identity

- task_id: `workforce-compact-surface`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `startup-freshness-gate` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Expose one compact, read-only workforce admission surface backed by the existing `CapabilityPlanner` and `HybridRouteDecision` authority. The surface must answer which workers are eligible, why a route was selected, what fallback is allowed, and which model-policy hash was used—without creating a second router or opening extra worktrees.

## Allowed files

- `nexus/config/model_workforce.yaml`
- `nexus/services/unified_runtime.py`
- `scripts/engine/nexus_cli.py`
- `tests/ops/test_model_workforce_policy.py`
- `tests/ops/test_unified_runtime.py`
- `tests/ops/test_nexus_cli.py`

## Forbidden scope

No new route authority; no provider/model roster invention; no direct model self-selection; no task launch or worktree creation; no canonical-root cutover; no cleanup of unrelated lifecycle receipts.

## Required behavior

1. A read-only CLI/query returns policy version/hash, eligible workforce entries, route authority, and denial reasons.
2. Every returned worker is checked against `docs/arch/MODEL_WORKFORCE_POLICY.md` and `nexus/config/model_workforce.yaml`.
3. Local model output remains Candidate-only and cannot grant approval, integration, push, or cleanup authority.
4. Query latency and output size are bounded so briefing generation does not become a second long-running task.
5. Tests prove no parallel router is introduced and policy/hash drift fails closed.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_model_workforce_policy.py tests/ops/test_unified_runtime.py tests/ops/test_nexus_cli.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
```

## Exit criteria

One compact read-only workforce query is wired to existing route authority, has bounded tests and evidence, and is committed as a separate Candidate. Briefing reduction remains downstream.

## Residual debt

Task-aware briefing overlays and automatic stale-worktree cleanup still require a separate card and explicit cleanup authority.

## Block classification

- `RECOVERABLE_BLOCK`: policy discovery/test environment failure with no route mutation.
- `HARD_BLOCK`: proposed query would become a second router or grant a worker downstream authority.
