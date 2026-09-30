# Task Card: issue-1209-grok-host-affinity

artifact_authority: current
task_id: `issue-1209-grok-host-affinity`
owner: James Chen
status: ACTIVE
execution_lane: GOVERNED
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Implement Issue #1209: make the existing Grok credential pool host-affine with a stable non-secret host binding, expose host ownership readback, fail closed on wrong-host use before provider execution, preserve host-sync exclusion of credentials/leases, document supported multi-host behavior, and verify both wrong-host negative and owner-host positive paths without creating a second router/account authority or distributed lease service.

## Allowed files

- `nexus/services/grok_account_pool.py`
- `scripts/ops/nexus-grok-accounts`
- `tests/services/test_grok_account_pool.py`
- `tests/ops/test_nexus_grok_accounts.py`
- `docs/integrations/CHATGPT_DIRECT_CONTROL_PROFILE.md`

## Verification commands

```bash
python3 -m pytest -q tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py
uv run ruff check nexus/services/grok_account_pool.py scripts/ops/nexus-grok-accounts tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
