# Task Card 00: EIA V10 Normal-Operation Canary

## Identity

- task_id: `eia-v10-normal-operation-20260816`
- campaign_id: `external-intelligence-v10-normal-operation-20260816`
- artifact_authority: current
- status: ACTIVE
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false
- allow_deletions: false
- main_sha: `8f9b555739f828ae1c65e3d0c6f11e7755c96068`

## Objective

Add one harmless read-only canary unit test that asserts True, proving the
External Intelligence Automation (EIA) background daemon executes an approved
Task Card unattended from canonical `James3014/Nexus-new` main after PR331
execution-authority hardening. This card exists solely to exercise the daemon
discovery -> remote-main refresh -> card-authority validation -> sidecar A+B
dispatch -> DeepSeek execution -> deterministic verification -> closure
publication chain exactly once.

## Allowed files

- `tests/ops/test_external_intelligence_v10_normal_operation.py`

## Forbidden scope

No canonical-root mutation; no changes to AGENTS/MUSE/GEMINI/CLAUDE/MEMORY/
SOUL/Cursor bootstrap files; no production source, workflow, route, policy,
provider, or credential changes; no second selector/router/planner authority;
no deletions; no release or production claims; no manual run-once substitute.

## Verification commands

```bash
python3 -m pytest -q tests/ops/test_external_intelligence_v10_normal_operation.py
git diff --check
git diff --name-status --diff-filter=D
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card does
not grant merge, approval, integration, release, or production authority.

## Exit criteria

Exactly one completion publication is emitted with
`current_gate=PENDING_INDEPENDENT_ACCEPTANCE`, runtime HEAD remains
`8f9b555739f828ae1c65e3d0c6f11e7755c96068` and clean, and no manual execution
substitute was used.
