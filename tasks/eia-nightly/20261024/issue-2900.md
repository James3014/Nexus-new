# Task Card: EIA nightly eia-nightly-20261024-i2900

## Identity

- task_id: `eia-nightly-20261024-i2900`
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
- capability_ids: `nexus_learning_feedback`

## Objective

Resolve GitHub Issue #2900: eia_scoreboard --since reads a naive date-time as local time, not UTC as documented. eia_scoreboard --since: read a value without a UTC offset as UTC, as the help says, instead of local time.

The full problem statement is the body of Issue #2900 (difficulty: easy).

## Allowed files

- `scripts/ops/eia_scoreboard.py`
- `tests/ops/test_eia_scoreboard.py`

## Required implementation

Change only the allowed files so that the behaviour described in Issue #2900 holds. Keep
every existing public name and signature working.

## Forbidden scope

No workflow, configuration, dependency, Task Card or control-plane changes; no deletions;
no files outside the allowed list.

## Verification commands

```bash
python3 -m pytest -q tests/ops/test_eia_scoreboard.py
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants no approval,
merge, integration or release authority.
