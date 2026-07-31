# Task Card 06: Briefing Overlay Reduction

## Identity

- task_id: `briefing-overlay-reduction`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `workforce-compact-surface` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Replace the always-long static startup briefing with a compact, current-worktree/task-aware overlay. The overlay must carry only the authority and evidence needed for the active Task Card, expose the compact workforce query, and make the historical protocol explicitly opt-in reference material.

## Allowed files

- `scripts/ops/_nexus_enforced_briefing.sh`
- `tests/ops/test_nexus_enforced_briefing.py`
- `tests/ops/test_local_assist_agent_workflow.py`

## Forbidden scope

No model/provider changes; no runtime router changes; no canonical-root mutation; no deletion of legacy protocol documents; no P6 cutover; no removal of safety gates or receipt requirements.

## Required behavior

1. Default output is compact and includes worktree root, branch, HEAD, dirty state, active INDEX/card references, startup freshness command, and workforce status command.
2. The active Task Card and policy hashes remain authoritative; the briefing does not invent task scope or worker selection.
3. Legacy protocol content is available only through explicit `NEXUS_BRIEFING_MODE=legacy` and is labeled non-normative.
4. Compact output retains fail-closed, workspace safety, receipt, and Local Assist closeout rules.
5. Tests prove compact output is materially smaller than the legacy reference and contains current-task/workforce hooks.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_nexus_enforced_briefing.py tests/ops/test_local_assist_agent_workflow.py
bash -n scripts/ops/_nexus_enforced_briefing.sh
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
```

## Exit criteria

Default briefing is compact, task-aware, policy-bound, legacy mode is explicit, focused tests pass, and a scoped commit is created.

## Residual debt

Workspace lease reuse, orphan detection, retry idempotency, and canonical root cutover remain separate owner-gated work.

## Block classification

- `RECOVERABLE_BLOCK`: shell/test environment failure with output preserved.
- `HARD_BLOCK`: reducing the briefing would remove a required safety/receipt gate or silently promote legacy protocol text.
