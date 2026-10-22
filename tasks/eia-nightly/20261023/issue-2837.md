# Task Card: EIA nightly eia-nightly-20261023-i2837

## Identity

- task_id: `eia-nightly-20261023-i2837`
- campaign_id: `eia-nightly`
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
- execution_lane: `DIRECT_DELEGATED`
- capability_disposition: `EXTEND_EXISTING`
- capability_ids: `nexus_core_domain_runtime`

## Objective

Resolve GitHub Issue #2837: local_heal: canonical diff keeps the next file's --- / +++ headers as hunk payload (2821 item 4). End each canonicalized local_heal diff hunk by its declared line counts so the next file's --- / +++ headers are not hashed as payload.

The full problem statement is the body of Issue #2837 (difficulty: medium).

## Allowed files

- `nexus/services/local_heal/isolated_workspace_apply.py`
- `tests/unit/local_heal/test_isolated_workspace_apply.py`

## Required implementation

Change only the allowed files so that the behaviour described in Issue #2837 holds. Keep
every existing public name and signature working.

## Forbidden scope

No workflow, configuration, dependency, Task Card or control-plane changes; no deletions;
no files outside the allowed list.

## Verification commands

```bash
python3 -m pytest -q tests/unit/local_heal/test_isolated_workspace_apply.py
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants no approval,
merge, integration or release authority.
