# Task Card P10: Compatibility Adapter Lane Correction

## Identity

- task_id: `single-mcp-three-lane-p10-compatibility-adapter-cutover`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- objective: Remove the stale ChatGPT delivery adapter assumptions that force every request into an isolated Target, while preserving governed lifecycle handling for explicitly delegated workers.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Allowed Files

- `scripts/ops/nexus_chatgpt_delivery.py`
- `tests/ops/test_nexus_chatgpt_delivery.py`

## Required Behavior

1. Default `auto`/`codex` delivery must attest `DIRECT_CANONICAL` and never fall back to isolation because `primary_agent` is absent.
2. The adapter must not emit `direct_delivery_allowed: false` or the retired `self-hosted-lifecycle-targets` default.
3. Target roots for explicitly isolated delivery resolve to `/Users/jameschen/Workspace/nexus-runtime-targets`.
4. Direct handoff returns one explicit `nexus_task_finish` action and does not call lifecycle wait on a task with no durable state.
5. Explicit delegated workers remain governed isolated submissions and retain actionable/owner gates.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/ops/test_nexus_chatgpt_delivery.py
```

## Exit Criteria

- Regression tests prove small adapter requests are Direct and legacy target naming is absent.
- Explicit delegated requests remain isolated and governed.
- Scoped commit and Direct receipt exist.
- No external DevSpace or connector files are modified.

## Completion Evidence

- Runtime commit: `4c86049283c7b5d6b213e1507befd088c95bc0d0`
- Direct receipt: `3ef82182e7dd13dec3470594f2c08d1bbbe863c7a26ddf1519f8455d7209ef7c`
- Verification: 11 adapter tests passed; `git diff --check` passed.
- An accidental pre-fix lifecycle misroute was cancelled and archived through the formal archive surface; no Target or Candidate remained.
