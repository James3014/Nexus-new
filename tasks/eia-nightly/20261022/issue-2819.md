# Task Card: EIA nightly eia-nightly-20261022-i2819

## Identity

- task_id: `eia-nightly-20261022-i2819`
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
- capability_ids: `repository_intelligence`

## Objective

Resolve GitHub Issue #2819: codeintel lookup_target: an allowed_files FIFO can block; add O_NONBLOCK and widen test-name exclusion (follow-up 2818). codeintel lookup_target: open with O_NONBLOCK and refuse non-regular files so a FIFO cannot block; test the 4096-entry cap; widen the test-name exclusion to test.py, tests.py and *_tests.py.

The full problem statement is the body of Issue #2819 (difficulty: easy).

## Allowed files

- `nexus/services/codeintel/lookup_target.py`
- `tests/nexus/codeintel/test_lookup_target.py`

## Required implementation

Change only the allowed files so that the behaviour described in Issue #2819 holds. Keep
every existing public name and signature working.

## Forbidden scope

No workflow, configuration, dependency, Task Card or control-plane changes; no deletions;
no files outside the allowed list.

## Verification commands

```bash
python3 -m pytest -q tests/nexus/codeintel/test_lookup_target.py
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants no approval,
merge, integration or release authority.
